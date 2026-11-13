"""Local visual fixture: real Go auth/storage + production React + synthetic runtime."""

import argparse
import base64
import copy
import json
import os
import secrets
import select
import shutil
import signal
import socket
import sqlite3
import subprocess
import threading
import time
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from deerflow_lock import read_revision, verify_checkout

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--frontend", type=Path, required=True)
parser.add_argument("--control", type=Path, required=True)
parser.add_argument("--work-dir", type=Path, required=True)
parser.add_argument("--node", default=shutil.which("node"))
parser.add_argument("--gateway-python", type=Path)
parser.add_argument("--gateway-checkout", type=Path)
parser.add_argument(
    "--dev", action="store_true", help="Use the same fixture with Next dev for local iteration"
)
args = parser.parse_args()
read_revision()
if bool(args.gateway_python) != bool(args.gateway_checkout):
    parser.error("Supply both frozen Gateway Python and checkout for offline capture tests")
capture = bool(args.gateway_python)
if capture:
    pinned = verify_checkout(args.gateway_checkout, paths=("backend",))
    print(f"DeerFlow upstream commit: {pinned}", flush=True)


def request_stop(signum, frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, request_stop)
if not args.node:
    parser.error("Supply Node on PATH or --node")
work = args.work_dir.resolve()
work.mkdir(mode=0o700, parents=True, exist_ok=False)
owner = {
    "email": "visual-fixture@example.com",
    "password": secrets.token_urlsafe(24),
    "synthetic_owner": True,
    "origin": "http://127.0.0.1:3300",
}
(work / "owner.json").write_text(json.dumps(owner))
(work / "owner.json").chmod(0o600)
# Mirror only the runtime tables used by Go's read-only workspace evidence.
# This database belongs to this fresh fixture directory, never a personal runtime.
if not capture:
    with sqlite3.connect(work / "runtime.db") as db:
        db.executescript("""
    CREATE TABLE threads_meta(
    thread_id TEXT PRIMARY KEY,
    user_id TEXT,
    incarnation TEXT,
    project_id TEXT,
    display_name TEXT,
    status TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT);
    CREATE TABLE runs(
    run_id TEXT PRIMARY KEY,
    thread_id TEXT,
    user_id TEXT,
    status TEXT,
    evidence_origin TEXT,
    origin_kind TEXT,
    operation_kind TEXT,
    kwargs_json TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT);
    CREATE TABLE mcp_tasks(
    id TEXT PRIMARY KEY,
    user_id TEXT,
    thread_id TEXT,
    thread_incarnation TEXT,
    status TEXT,
    result TEXT,
    last_polled_at TEXT,
    last_poll_error TEXT,
    cancel_requested_at TEXT,
    created_at TEXT,
    updated_at TEXT);
    """)

now = "2026-11-06T12:00:00+00:00"
thread = {
    "thread_id": "visual-thread",
    "status": "idle",
    "created_at": now,
    "updated_at": now,
    "metadata": {},
    "values": {"title": "合成视觉验收 · 长标题与状态检查", "messages": []},
    "interrupts": {},
}
tasks = [
    {
        "task_id": f"visual-{s}",
        "task_name": "合成验收 · " + s + " · " + ("长文件名_" * 8 if s == "failed" else "页面状态"),
        "status": s,
        "created_at": now,
        "updated_at": now,
        "error": "合成失败说明：请检查输入与连接。" if s == "failed" else None,
        "cancel_requested": False,
        "tracking_degraded": False,
        "result": {
            "summary": "合成界面样本，不是实际任务或验证结果。",
            "validation_status": "passed",
            "validation": {"exit_code": 0, "stdout": "Synthetic long output / path_" * 600},
        }
        if s == "completed"
        else None,
        "last_polled_at": now,
        "last_poll_error": None,
        "notification_status": "none",
        "notification_attempt_count": 0,
        "result_truncated": False,
        "input_required": {"prompt": "合成待输入问题"} if s == "input_required" else None,
    }
    for s in ["completed", "working", "failed", "input_required", "submitted", "cancelled"]
]
threads = {}
memories = {}
logs = []


def seed_owner():
    with sqlite3.connect(work / "runtime.db") as db:
        row = db.execute("SELECT id FROM users WHERE email=?", (owner["email"],)).fetchone()
        if not row:
            return
        user = row[0]
        stamp = datetime.now(UTC).isoformat()
        threads.setdefault(user, {})[thread["thread_id"]] = copy.deepcopy(thread)
        db.execute(
            """INSERT OR IGNORE INTO threads_meta(thread_id,
user_id,
incarnation,
display_name,
status,
created_at,
updated_at)
VALUES(?,
?,
'fixture-generation',
?,
'idle',
?,
?)""",
            (thread["thread_id"], user, thread["values"]["title"], stamp, stamp),
        )
        db.execute(
            """INSERT OR IGNORE INTO runs(run_id,
thread_id,
user_id,
status,
evidence_origin,
created_at,
updated_at)
VALUES('fixture-run',
?,
?,
 'input_required',
'interactive',
?,
?)""",
            (thread["thread_id"], user, stamp, stamp),
        )
        db.execute(
            """INSERT OR IGNORE INTO mcp_tasks(id,
user_id,
thread_id,
thread_incarnation,
status,
last_polled_at,
created_at,
updated_at)
VALUES('fixture-task',
?,
?,
'fixture-generation',
'input_required',
?,
?,
?)""",
            (user, thread["thread_id"], stamp, stamp, stamp),
        )


def runtime_owner(headers):
    cookie = SimpleCookie(headers.get("Cookie", ""))
    token = cookie.get("access_token")
    if not token:
        return ""
    try:
        encoded = token.value.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))["sub"]
    except (ValueError, KeyError, IndexError):
        return ""


class Runtime(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.handle_api()

    def do_POST(self):
        self.handle_api()

    def do_PATCH(self):
        self.handle_api()

    def do_DELETE(self):
        self.handle_api()

    def handle_api(self):
        path = self.path.split("?")[0]
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        data = json.loads(body or "{}")
        status = 200
        user = runtime_owner(self.headers)
        owned = threads.setdefault(user, {})
        logs.append({"method": self.command, "path": path})
        (work / "runtime-requests.json").write_text(json.dumps(logs))
        if "/runs" in path and self.command != "GET":
            status = 403
            out = {"detail": "No model or native execution in visual fixture"}
        elif path.startswith("/health"):
            out = {"status": "ready"}
        elif path == "/api/managed-models":
            out = {"models": []}
        elif path == "/api/managed-models/providers":
            out = {"providers": []}
        elif path == "/api/channels/providers":
            out = {"providers": []}
        elif path == "/api/channels/connections":
            out = {"connections": []}
        elif path == "/api/subagents":
            out = {"subagents": []}
        elif path == "/api/features":
            out = {
                "agents_api": {"enabled": False},
                "scheduled_tasks": {"available": False, "running": False},
            }
        elif path == "/api/models":
            out = {"models": [], "token_usage": {"enabled": False}}
        elif path == "/api/mcp/config":
            out = {"mcp_servers": {}}
        elif path.endswith("/threads/search"):
            out = [
                value for value in owned.values() if not value["metadata"].get("deerflow_archived")
            ]
        elif path == "/api/threads" and self.command == "POST":
            key = data.get("thread_id") or secrets.token_hex(16)
            out = owned.setdefault(
                key,
                {
                    **copy.deepcopy(thread),
                    "thread_id": key,
                    "metadata": data.get("metadata", {}),
                    "values": {"title": "Synthetic conversation", "messages": []},
                },
            )
            with sqlite3.connect(work / "runtime.db") as db:
                db.execute(
                    """INSERT OR IGNORE INTO threads_meta(thread_id,
user_id,
incarnation,
display_name,
status,
metadata_json,
created_at,
updated_at)
VALUES(?,
?,
?,
'Synthetic conversation',
'idle',
?,
?,
?)""",
                    (key, user, "fixture-" + key, json.dumps(out["metadata"]), now, now),
                )
        elif path.startswith("/api/threads/") and path.count("/") == 3:
            key = path.rsplit("/", 1)[-1]
            out = owned.get(key)
            if out is None:
                status, out = 404, {"detail": "Synthetic conversation unavailable"}
            elif self.command == "PATCH":
                out["metadata"].update(data.get("metadata", {}))
                with sqlite3.connect(work / "runtime.db") as db:
                    db.execute(
                        "UPDATE threads_meta SET metadata_json=? WHERE thread_id=? AND user_id=?",
                        (json.dumps(out["metadata"]), key, user),
                    )
            elif self.command == "DELETE":
                owned.pop(key, None)
                with sqlite3.connect(work / "runtime.db") as db:
                    db.execute(
                        "DELETE FROM threads_meta WHERE thread_id=? AND user_id=?", (key, user)
                    )
                out = {}
        elif "/mcp-tasks" in path:
            key = path.split("/mcp-tasks")[-1].strip("/")
            available = tasks if "/threads/visual-thread/mcp-tasks" in path else []
            out = next((x for x in available if x["task_id"] == key), None) if key else available
        elif path.endswith("/deermate.memory/actions/apply"):
            with sqlite3.connect(work / "runtime.db") as db:
                op = db.execute(
                    "select fact_id,kind,payload from deermate_memory_operations where id=?",
                    (data["operation_id"],),
                ).fetchone()
            key, kind, payload = op
            if kind == "delete":
                memories.pop(key, None)
            else:
                p = json.loads(payload)
                memories[key] = {
                    "id": key,
                    "content": p["content"],
                    "category": p.get("category", "context"),
                    "confidence": 1,
                    "revision": memories.get(key, {}).get("revision", 0) + 1,
                    "scope": p.get("scope", "personal"),
                    "source_id": key,
                    "updated_at": int(time.time()),
                }
            out = {
                "revision": memories.get(key, {}).get("revision", 1),
                "category": json.loads(payload or "{}").get("category", "context"),
            }
        elif path.endswith("/deermate.memory/actions/read"):
            out = {
                "items": [
                    v
                    for k, v in memories.items()
                    if k in data.get("ids", []) and data.get("query", "") in v["content"]
                ]
            }
        elif path.endswith("/state"):
            out = {"values": thread["values"], "next": [], "tasks": [], "checkpoint": None}
        elif path.endswith("/visual-thread"):
            out = thread
        elif path.endswith("/history") or path.endswith("/runs"):
            out = []
        elif path == "/api/config":
            out = {}
        elif path == "/api/agents":
            out = {"agents": []}
        elif path == "/api/projects":
            out = {"projects": []}
        elif path == "/api/skills":
            out = {"skills": []}
        elif path.startswith("/api/extensions"):
            out = {"extensions": []}
        else:
            out = []
        content = json.dumps(out, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def do_PATCH(self):
        self.forward()

    def do_DELETE(self):
        self.forward()

    def forward(self):
        if args.dev and self.headers.get("Upgrade", "").lower() == "websocket":
            self.forward_websocket()
            return
        if self.path == "/__visual-fixture":
            content = json.dumps(
                {
                    "fixture": "design-auth-v1",
                    "models": "offline-capture" if capture else "disabled",
                    "data": "synthetic",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        # Match the pinned production nginx SDK prefix rewrite before Go admission.
        forwarded_path = (
            "/api/" + self.path.removeprefix("/api/langgraph/")
            if self.path.startswith("/api/langgraph/")
            else self.path
        )
        control = forwarded_path.startswith(("/api/", "/admin", "/health/"))
        port = 3302 if control else 3301
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("connection", "content-length", "accept-encoding")
        }
        headers["Host"] = "127.0.0.1:3300"
        try:
            with httpx.Client(trust_env=False, timeout=45) as client:
                r = client.request(
                    self.command,
                    f"http://127.0.0.1:{port}" + forwarded_path,
                    headers=headers,
                    content=self.rfile.read(int(self.headers.get("Content-Length", 0))),
                )
            if not capture and self.path == "/api/v1/auth/initialize" and r.status_code == 201:
                seed_owner()
            self.send_response(r.status_code)
            for k, v in r.headers.multi_items():
                if k.lower() not in (
                    "transfer-encoding",
                    "connection",
                    "content-encoding",
                    "content-length",
                ):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(r.content)))
            self.end_headers()
            self.wfile.write(r.content)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send_error(502, "Local visual fixture upstream unavailable")

    def forward_websocket(self):
        # Next's development bootstrap waits for its HMR connection. Keep this
        # loopback-only bridge separate from the production HTTP fixture path.
        with socket.create_connection(("127.0.0.1", 3301), timeout=10) as upstream:
            headers = "\r\n".join(f"{key}: {value}" for key, value in self.headers.items())
            upstream.sendall(f"GET {self.path} HTTP/1.1\r\n{headers}\r\n\r\n".encode())
            upstream.settimeout(None)
            while True:
                ready, _, _ = select.select([self.connection, upstream], [], [], 10)
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        self.close_connection = True
                        return
                    (upstream if source is self.connection else self.connection).sendall(data)


if not capture:
    runtime = ThreadingHTTPServer(("127.0.0.1", 3303), Runtime)
    threading.Thread(target=runtime.serve_forever, daemon=True).start()
env = {
    key: value
    for key, value in os.environ.items()
    if key in {"PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT"}
}
env.update(
    NEXT_TELEMETRY_DISABLED="1",
    DEERMATE_DESIGN_GALLERY="1",
    AUTH_JWT_SECRET=secrets.token_urlsafe(40),
    DEERMATE_RUNTIME_URL="http://127.0.0.1:3303",
    DEERMATE_ORIGIN="http://127.0.0.1:3300",
    DEERMATE_ALLOWED_HOSTS="127.0.0.1:3300,127.0.0.1:3302",
    DEERMATE_LISTEN="127.0.0.1:3302",
    DEERMATE_DATABASE_PATH=str(work / "runtime.db"),
    DEERMATE_AUTHORIZATION_HOME=str(work / "grants"),
    DEER_FLOW_INTERNAL_GATEWAY_BASE_URL="http://127.0.0.1:3302",
    DEER_FLOW_TRUSTED_ORIGINS="http://127.0.0.1:3300",
)
if capture:
    config = {
        "config_version": 62,
        "models": [
            {
                "name": "capture-fixture",
                "use": "deermate_memory_fixture:CaptureModel",
                "model": "offline-fixture",
            }
        ],
        "tools": [],
        "tool_groups": [],
        "plugins": [
            {"name": "deermate-memory", "use": "deermate.memory:install", "required": True},
            {"name": "deermate-briefing", "use": "deermate.briefing:install", "required": True},
        ],
        "extensions": {
            "middlewares": [
                "deermate.briefing_middleware:BriefingActionMiddleware",
                "deermate.session_middleware:CodingSessionMiddleware",
                "deermate.memory_middleware:PersonalMemoryMiddleware",
            ]
        },
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        "database": {"backend": "sqlite", "sqlite_dir": str(work / "sql")},
        "memory": {"enabled": False},
        "title": {"enabled": False},
        "suggestions": {"enabled": False},
        "scheduler": {"enabled": False},
    }
    (work / "config.yaml").write_text(json.dumps(config))
    (work / "empty.env").touch()
    env.update(
        DEER_FLOW_PROJECT_ROOT=str(work),
        DEER_FLOW_HOME=str(work / "home"),
        DEER_FLOW_CONFIG_PATH=str(work / "config.yaml"),
        DEER_FLOW_ENV_FILE=str(work / "empty.env"),
        DEER_FLOW_AUTH_DISABLED="0",
        DEERMATE_DATABASE_PATH=str(work / "sql/deerflow.db"),
        PYTHONPATH=os.pathsep.join(
            [str(args.gateway_checkout.resolve() / "backend"), str(root / "src")]
        ),
    )

jobs = []
try:
    commands = [
        ("control", [str(args.control.resolve())], root),
        (
            "frontend",
            [
                args.node,
                "node_modules/next/dist/bin/next",
                "dev" if args.dev else "start",
                *(["--webpack"] if args.dev else []),
                "--hostname",
                "127.0.0.1",
                "--port",
                "3301",
            ],
            args.frontend.resolve(),
        ),
    ]
    if capture:
        commands.insert(
            0,
            (
                "gateway",
                [
                    str(args.gateway_python.absolute()),
                    str(root / "scripts/verify_personal_memory.py"),
                    "--gateway-child",
                    "3303",
                ],
                root,
            ),
        )
    for name, command, cwd in commands:
        jobs.append(
            subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=(work / (name + ".log")).open("w"),
                stderr=subprocess.STDOUT,
            )
        )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if any(job.poll() is not None for job in jobs):
            raise RuntimeError("Fixture process exited; inspect this fixture's private logs")
        try:
            if (
                httpx.get(
                    "http://127.0.0.1:3302/health/ready", trust_env=False, timeout=2
                ).status_code
                == 200
            ):
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError("Fixture readiness timed out")
    proxy = ThreadingHTTPServer(("127.0.0.1", 3300), Proxy)
    print(
        "Visual fixture ready on loopback port 3300; synthetic runtime, real Go authentication.",
        flush=True,
    )
    proxy.serve_forever()
finally:
    for job in jobs:
        job.terminate()
    for job in jobs:
        job.wait(timeout=10)
