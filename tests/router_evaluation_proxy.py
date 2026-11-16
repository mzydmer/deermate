"""Fixed internal S2 proxy: lose one ACK only after real durable admission.

This fixture is never packaged in DeerMate. Its observer reads canonical local
records; its proof is collected after recovery and never supplies task handles
to the recovery driver. Upstream is always the same Gateway on loopback:8001.
"""

import gzip
import hashlib
import http.client
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE = Path("/app/backend/.deer-flow")
HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
}


def readonly(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)
    db.row_factory = sqlite3.Row
    return db


class DurabilityObserver:
    def __init__(self, root, mode, logical):
        self.root, self.mode, self.logical = root, mode, logical

    def operation(self, identifier):
        with closing(readonly(self.root / "data/deerflow.db")) as db:
            row = db.execute(
                "SELECT owner,id,parent,state,data FROM deermate_work_records "
                "WHERE kind='operation' AND id=?",
                (identifier,),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["data"] = json.loads(item["data"])
            return item

    def target(self, identifier):
        op = self.operation(identifier)
        return (
            op
            and op["data"].get("kind") == "router"
            and (
                op["data"].get("origin") == "user"
                and op["data"].get("message") == "EVAL_START " + self.logical
            )
        )

    def durable(self, identifier, run_id):
        op = self.operation(identifier)
        if not op or op["state"] != "dispatching" or op["data"].get("run_id"):
            return None
        owner, coordinator = op["owner"], op["data"]["thread_id"]
        native_id, thread, task_run = None, coordinator, run_id
        if self.mode != "A":
            result = op["data"].get("_tool_result") or {}
            native_id = result.get("id")
            if not native_id or not op["data"].get("_tool_done"):
                return None
            native = self.operation(native_id)
            if not native or native["owner"] != owner or native["data"].get("kind") != "execute":
                return None
            if "EVAL_OPERATION=" + self.logical not in native["data"].get("message", ""):
                return None
            thread, task_run = native["data"]["thread_id"], "continuous:" + native_id
        with closing(readonly(self.root / "data/deerflow.db")) as db:
            run = db.execute(
                "SELECT run_id,user_id,thread_id,idempotency_key FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            canonical = (
                "http-run:"
                + hashlib.sha256(
                    (
                        owner + "\0" + coordinator + "\0extension:deermate.continuous:" + identifier
                    ).encode()
                ).hexdigest()
            )
            if not run or (run["user_id"], run["thread_id"], run["idempotency_key"]) != (
                owner,
                coordinator,
                canonical,
            ):
                return None
            tasks = db.execute(
                "SELECT id,user_id,thread_id,thread_incarnation,run_id,status,remote_task_id "
                "FROM mcp_tasks WHERE user_id=? AND thread_id=? AND run_id=?",
                (owner, thread, task_run),
            ).fetchall()
        if len(tasks) != 1 or not tasks[0]["remote_task_id"]:
            return None
        task = dict(tasks[0])
        journal = self.root / "data/deermate-chat-sessions.sqlite3"
        if not journal.exists():
            return None
        with closing(readonly(journal)) as db:
            binding = db.execute(
                "SELECT b.scope,b.head,b.pending,b.round,t.confirmed,t.tracking_id "
                "FROM bindings b JOIN turns t ON b.scope=t.scope "
                "WHERE b.user_id=? AND b.thread_id=? AND coalesce(b.incarnation,'')=? "
                "AND b.head=? AND t.tracking_id=? AND t.confirmed=1 AND b.pending IS NULL",
                (owner, thread, task["thread_incarnation"] or "", task["id"], task["id"]),
            ).fetchone()
        if not binding:
            return None
        return {
            "original_go_operation": identifier,
            "original_go_state": op["state"],
            "original_run_id": run_id,
            "owner_id": owner,
            "coordinator_thread": coordinator,
            "native_operation": native_id,
            "tracking_thread": thread,
            "tracking_id": task["id"],
            "remote_handle_sha256": hashlib.sha256(task["remote_task_id"].encode()).hexdigest(),
            "tracking_status_at_barrier": task["status"],
            "chat_turn_confirmed": bool(binding["confirmed"]),
            "chat_head": binding["head"],
            "chat_round": binding["round"],
            "chat_pending": binding["pending"],
        }


class ProxyState:
    def __init__(self, root, cfg, max_hold_seconds=18):
        self.root = root
        self.observer = DurabilityObserver(root, cfg["mode"], cfg["logical_operation_id"])
        self.lock = threading.Lock()
        self.reserved = False
        self.original = None
        self.stop = threading.Event()
        self.max_hold_seconds = min(18, max_hold_seconds)
        self.domain = (
            "linux-monotonic:" + Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        )
        self.log = root / "evaluation-fault.jsonl"
        if self.log.exists():
            reserved = [
                json.loads(v)
                for v in self.log.read_text().splitlines()
                if json.loads(v).get("kind") == "fault_reserved"
            ]
            self.reserved = bool(reserved)
            self.original = reserved[0]["original_go_operation"] if reserved else None

    def record(self, kind, **fields):
        with self.lock:
            value = {"kind": kind, "ns": time.monotonic_ns(), "clock_domain": self.domain, **fields}
            with self.log.open("a") as out:
                self.log.chmod(0o600)
                out.write(json.dumps(value) + "\n")
                out.flush()
                os.fsync(out.fileno())

    def reserve(self, path, body):
        if path != "/api/plugins/deermate.continuous/actions/perform":
            return None
        try:
            identifier = json.loads(body)["operation_id"]
            if not self.observer.target(identifier):
                return None
        except (sqlite3.Error, OSError, ValueError, KeyError):
            return None
        with self.lock:
            if self.reserved:
                return None
            self.reserved = True
            self.original = identifier
        self.record("fault_reserved", original_go_operation=identifier)
        return identifier


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass  # Do not log JWT cookies, capabilities or request bodies.

    def forward(self):
        state = self.server.fixture_state
        started = time.monotonic()
        size = int(self.headers.get("Content-Length", "0"))
        if size < 0 or size > 2_000_000 or not self.path.startswith("/"):
            self.send_error(400)
            return
        body = self.rfile.read(size)
        identifier = state.reserve(self.path, body) if self.command == "POST" else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
        headers["Connection"] = "close"
        upstream = http.client.HTTPConnection("127.0.0.1", 8001, timeout=20)
        try:
            upstream.request(self.command, self.path, body=body if size else None, headers=headers)
            response = upstream.getresponse()
            payload = response.read()
            response_headers = response.getheaders()
            if self.path == "/api/plugins/deermate.continuous/actions/query":
                queried = json.loads(body).get("operation_id")
                if queried == state.original:
                    decoded = (
                        gzip.decompress(payload)
                        if response.getheader("Content-Encoding") == "gzip"
                        else payload
                    )
                    queried_result = json.loads(decoded)
                    state.record(
                        "original_query",
                        original_go_operation=queried,
                        upstream_status=response.status,
                        known=queried_result.get("known"),
                        run_id=queried_result.get("run_id"),
                        status=queried_result.get("status"),
                    )
            if identifier and response.status != 200:
                state.record(
                    "upstream_not_success",
                    original_go_operation=identifier,
                    upstream_status=response.status,
                )
            if identifier and response.status == 200:
                decoded = (
                    gzip.decompress(payload)
                    if response.getheader("Content-Encoding") == "gzip"
                    else payload
                )
                receipt = json.loads(decoded)
                if receipt.get("accepted") and receipt.get("known") and receipt.get("run_id"):
                    # Stay inside the original Go twenty-second request budget.
                    # An absent barrier is a failed injection, never an early500
                    # or a pre-admission disconnect disguised as lost ACK.
                    while (
                        not state.stop.is_set()
                        and time.monotonic() < started + state.max_hold_seconds
                    ):
                        try:
                            proof = state.observer.durable(identifier, receipt["run_id"])
                        except (sqlite3.Error, OSError, ValueError, KeyError) as error:
                            proof = None
                            state.record("observer_error", error_kind=type(error).__name__)
                        if proof:
                            state.record(
                                "durable_barrier",
                                proof=proof,
                                upstream_status=response.status,
                                upstream_response_bytes=len(payload),
                            )
                            # No headers or response bytes have been sent to Go.
                            self.close_connection = True
                            self.connection.shutdown(socket.SHUT_RDWR)
                            self.connection.close()
                            state.record(
                                "ack_dropped",
                                original_go_operation=identifier,
                                response_bytes_sent_to_go=0,
                            )
                            return
                        time.sleep(0.02)
                    state.record("barrier_not_reached", original_go_operation=identifier)
                else:
                    state.record("upstream_not_admitted", original_go_operation=identifier)
            self.send_response(response.status)
            for key, value in response_headers:
                if key.lower() not in HOP_HEADERS:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
            self.close_connection = True
        except (OSError, ValueError) as error:
            state.record(
                "proxy_request_error",
                error_kind=type(error).__name__,
                original_go_operation=identifier,
            )
            self.close_connection = True
        finally:
            upstream.close()

    do_GET = forward
    do_POST = forward
    do_HEAD = forward
    do_PATCH = forward
    do_DELETE = forward


def main():
    cfg = json.loads(Path(os.environ["DEERMATE_EVALUATION_CONFIG"]).read_text())
    if (
        sys.platform != "linux"
        or os.getuid() != 1000
        or cfg["profile"] != "router-offline-v1"
        or cfg["scenario"] != "S2"
        or cfg["mode"] not in {"A", "B", "C"}
    ):
        raise PermissionError("Explicit isolated S2 Linux fixture required")
    state = ProxyState(STATE, cfg)
    server = ThreadingHTTPServer(("0.0.0.0", 8002), ProxyHandler)
    server.daemon_threads = True
    server.fixture_state = state
    child = subprocess.Popen(
        [
            "/app/backend/.venv/bin/python",
            "-m",
            "uvicorn",
            "deermate.gateway:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8001",
            "--no-access-log",
            "--log-level",
            "warning",
        ]
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: state.stop.set())
    try:
        while not state.stop.wait(0.2) and child.poll() is None:
            pass
    finally:
        server.shutdown()
        server.server_close()
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


if __name__ == "__main__":
    main()
