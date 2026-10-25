"""Opt-in real Gateway/SQLite/MCP verification with an offline native fixture.

The child loads the unchanged upstream application, adding only a protected
model-free submit shim. This is verification tooling, not a production server.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import platform
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

DEERFLOW_COMMIT = "a1b89d0432de4e45adc59f512cb25bb386ea1e51"
ROOT = Path(__file__).resolve().parents[1]


def gateway_child(port: int):
    """Load the real application without patching its task machinery."""

    def loopback_only(event, arguments):
        if event == "socket.connect":
            address = arguments[1]
            if isinstance(address, tuple) and not ipaddress.ip_address(address[0]).is_loopback:
                raise RuntimeError("Verification Gateway permits only loopback connections")

    sys.addaudithook(loopback_only)
    import uvicorn
    from app.gateway.app import app
    from app.gateway.deps import get_current_user, get_thread_store
    from deerflow.mcp.tools import get_mcp_tools
    from fastapi import HTTPException, Request

    @app.post("/__deermate_verification/submit")
    async def submit(request: Request):
        expected = os.environ["DEERMATE_VERIFICATION_KEY"]
        if not secrets.compare_digest(request.headers.get("X-DeerMate-Verification", ""), expected):
            raise HTTPException(403, "Verification key required")
        body = await request.json()
        if set(body) != {"thread_id", "prompt", "key"}:
            raise HTTPException(422, "Only the fixed verification submission is supported")
        user_id = await get_current_user(request)
        thread = await get_thread_store(request).get(body["thread_id"], user_id=user_id)
        if thread is None:
            raise HTTPException(404, "Thread not found")
        tools = await get_mcp_tools()
        names = [tool.name for tool in tools]
        if names != ["deermate_submit_task"]:
            raise HTTPException(500, "Unexpected discovered task tools")
        runtime = SimpleNamespace(
            context={
                "thread_id": body["thread_id"],
                "thread_incarnation": thread.get("incarnation"),
                "user_id": user_id,
            },
            config={},
            tool_call_id=body["key"],
        )
        result = await tools[0].coroutine(
            runtime=runtime, project_id="demo", prompt=body["prompt"], idempotency_key=body["key"]
        )
        return {"tracking": result, "visible_tools": names}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


class Process:
    def __init__(self, name, command, env, cwd, log_path):
        self.name = name
        self.forced = False
        self.log = log_path.open("wb")
        self.job = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def stop(self):
        if self.job.poll() is None:
            self.job.terminate()
            try:
                self.job.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.forced = True
                os.killpg(self.job.pid, signal.SIGKILL)
                self.job.wait(timeout=10)
        self.log.close()


def wait_for(operation, predicate, *, timeout=90, process=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.job.poll() is not None:
            raise RuntimeError(f"{process.name} exited; inspect its local verification log")
        try:
            value = operation()
            if predicate(value):
                return value
        except (httpx.TransportError, FileNotFoundError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Verification deadline exceeded; inspect local verification logs")


def port_number():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def child_environment():
    allowed = {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SSL_CERT_FILE"}
    return {key: value for key, value in os.environ.items() if key in allowed}


def verify_checkout(checkout):
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True)
    if head.strip() != DEERFLOW_COMMIT:
        raise ValueError("Gateway verification requires the documented pinned DeerFlow commit")
    subprocess.run(
        ["git", "-C", str(checkout), "diff", "--exit-code", DEERFLOW_COMMIT, "--", "backend"],
        check=True,
        capture_output=True,
    )


def prepare(work, checkout, worker_port):
    repo = work / "repo"
    repo.mkdir()
    (repo / "answer.py").write_text("def add(a, b):\n    return a - b\n")
    (repo / "tests").mkdir()
    (repo / "tests/test_answer.py").write_text(
        "import unittest\nfrom answer import add\nclass Addition(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
    )
    (repo / ".gitignore").write_text("__pycache__/\n")
    for args in [
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ]:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    worker_config = work / "worker.toml"
    native_argv = [sys.executable, "-u", str(ROOT / "tests/fake_codex.py"), str(work / "native")]
    validation_argv = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    worker_config.write_text(
        f"state_dir = {json.dumps(str(work / 'worker'))}\n"
        f"codex_command = {json.dumps(native_argv)}\n"
        "task_timeout_seconds = 180\n[projects.demo]\n"
        f"root = {json.dumps(str(repo))}\nallow_write = true\n"
        f"test_command = {json.dumps(validation_argv)}\n"
    )
    (work / "empty.env").touch()
    # JSON is valid YAML; avoiding an extra parser keeps the parent lightweight.
    (work / "config.yaml").write_text(
        json.dumps(
            {
                "config_version": 62,
                "models": [],
                "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
                "database": {"backend": "sqlite", "sqlite_dir": str(work / "sql")},
                "memory": {"enabled": False},
                "title": {"enabled": False},
                "suggestions": {"enabled": False},
                "scheduler": {"enabled": False},
                "mcp_tasks": {
                    "enabled": True,
                    "poll_interval_seconds": 1,
                    "lease_seconds": 10,
                    "max_concurrent_polls": 2,
                    "tracking_degraded_after_errors": 1,
                    "max_poll_backoff_seconds": 2,
                    "input_required_poll_interval_seconds": 5,
                },
            }
        )
    )
    extensions = json.loads((ROOT / "examples/deerflow.extensions.json").read_text())
    server = extensions["mcpServers"]["deermate"]
    server.update(
        {
            "command": sys.executable,
            "cwd": str(ROOT),
            "args": [
                "-m",
                "deermate.cli",
                "--config",
                str(worker_config),
                "--port",
                str(worker_port),
                "mcp",
            ],
        }
    )
    (work / "extensions_config.json").write_text(json.dumps(extensions))
    env = child_environment()
    env.update(
        {
            "DEER_FLOW_PROJECT_ROOT": str(work),
            "DEER_FLOW_HOME": str(work / "home"),
            "DEER_FLOW_CONFIG_PATH": str(work / "config.yaml"),
            "DEER_FLOW_ENV_FILE": str(work / "empty.env"),
            "DEER_FLOW_AUTH_DISABLED": "1",
            "PYTHONPATH": str(checkout / "backend"),
            "GATEWAY_HOST": "127.0.0.1",
            "DEERMATE_VERIFICATION_KEY": secrets.token_urlsafe(32),
            "TIKTOKEN_CACHE_DIR": str(work / "tiktoken"),
        }
    )
    return worker_config, env


def run(checkout, gateway_python, receipt_path, work):
    verify_checkout(checkout)
    worker_port, gateway_port = port_number(), port_number()
    worker_config, env = prepare(work, checkout, worker_port)
    env["GATEWAY_PORT"] = str(gateway_port)
    worker_source = hashlib.sha256()
    for path in sorted((ROOT / "src/deermate").glob("*.py")):
        worker_source.update(path.name.encode() + b"\0" + path.read_bytes())
    runtime_probe = (
        "import importlib.metadata as m,json,platform; "
        "print(json.dumps({'python':platform.python_version(),'packages':"
        "{name:m.version(name) for name in ['deerflow-harness','deerflow-extension-api',"
        "'fastapi','sqlalchemy','mcp','langchain-mcp-adapters','cryptography']}}))"
    )
    gateway_runtime = json.loads(
        subprocess.check_output(
            [str(gateway_python), "-c", runtime_probe], env=child_environment(), text=True
        )
    )
    receipt = {
        "schema_version": 1,
        "started_at": datetime.now(UTC).isoformat(),
        "upstream_commit": DEERFLOW_COMMIT,
        "upstream_lock_sha256": hashlib.sha256(
            (checkout / "backend/uv.lock").read_bytes()
        ).hexdigest(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "deermate_source_sha256": worker_source.hexdigest(),
        "native_fixture_sha256": hashlib.sha256(
            (ROOT / "tests/fake_codex.py").read_bytes()
        ).hexdigest(),
        "parent_python": platform.python_version(),
        "gateway_runtime": gateway_runtime,
        "platform": platform.system(),
        "native_runtime": "offline Codex protocol fixture",
        "configured_cloud_models": 0,
        "gateway": "actual upstream application, lifespan, SQL service, MCP caller and HTTP routes",
        "submit_entry": "verifier-only protected shim invokes actual discovered tool wrapper",
        "limits": [
            "Orderly process restart; no hard-crash or remote network test.",
            "No configured chat model; notification-model runs are not expected to complete.",
            "No browser/UI, real-model task or SSH verification.",
        ],
        "checks": [],
    }

    def check(name, condition, **evidence):
        if not condition:
            raise RuntimeError(f"Acceptance failed: {name}")
        receipt["checks"].append({"name": name, "passed": True, **evidence})
        print(f"PASS {name}", flush=True)

    def start_worker(generation):
        return Process(
            "Worker",
            [
                sys.executable,
                "-m",
                "deermate.cli",
                "--config",
                str(worker_config),
                "--port",
                str(worker_port),
                "serve",
            ],
            child_environment(),
            ROOT,
            work / f"worker-{generation}.log",
        )

    def start_gateway(generation):
        return Process(
            "Gateway",
            [
                str(gateway_python),
                str(Path(__file__).resolve()),
                "--gateway-child",
                str(gateway_port),
            ],
            env,
            checkout / "backend",
            work / f"gateway-{generation}.log",
        )

    def sql_row(tracking_id):
        with sqlite3.connect(f"file:{work / 'sql/deerflow.db'}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM mcp_tasks WHERE id=?", (tracking_id,)).fetchone()
            if row is None:
                raise RuntimeError("Tracking row was not committed")
            return dict(row)

    def request(client, method, path, body=None):
        response = client.request(method, path, json=body)
        if response.status_code >= 300:
            raise RuntimeError(f"Gateway/Worker request failed: HTTP {response.status_code}")
        return response.json()

    with ExitStack() as cleanup:
        worker = start_worker(1)
        cleanup.callback(worker.stop)
        wait_for(lambda: (work / "worker/api.token").read_text(), bool, process=worker)
        token = (work / "worker/api.token").read_text().strip()
        wc = cleanup.enter_context(
            httpx.Client(
                base_url=f"http://127.0.0.1:{worker_port}",
                trust_env=False,
                timeout=10,
                headers={"Authorization": f"Bearer {token}"},
            )
        )
        gateway = start_gateway(1)
        cleanup.callback(gateway.stop)
        gc = cleanup.enter_context(
            httpx.Client(
                base_url=f"http://127.0.0.1:{gateway_port}",
                trust_env=False,
                timeout=30,
                headers={"X-DeerMate-Verification": env["DEERMATE_VERIFICATION_KEY"]},
            )
        )
        wait_for(
            lambda: gc.get("/health"), lambda r: r.status_code == 200, timeout=180, process=gateway
        )
        print("Actual Gateway ready with isolated SQLite.", flush=True)

        def submit(prompt):
            thread = uuid.uuid4().hex
            request(gc, "POST", "/api/threads", {"thread_id": thread})
            payload = request(
                gc,
                "POST",
                "/__deermate_verification/submit",
                {
                    "thread_id": thread,
                    "prompt": prompt,
                    "key": uuid.uuid4().hex,
                },
            )
            tid = payload["tracking"]["task_id"]
            row = sql_row(tid)
            check(
                "sql_submission_and_hidden_control_tools",
                payload["visible_tools"] == ["deermate_submit_task"],
                tracking_id=tid,
                remote_task_id=row["remote_task_id"],
            )
            return thread, tid, row["remote_task_id"]

        def detail(thread, tid):
            return request(gc, "GET", f"/api/threads/{thread}/mcp-tasks/{tid}")

        thread, tid, remote = submit("slow-gateway")
        native = wait_for(
            lambda: request(wc, "GET", f"/tasks/{remote}"), lambda t: t["status"] == "running"
        )["session_id"]
        old_pid = gateway.job.pid
        gateway.stop()
        check(
            "worker_survives_gateway_stop",
            not gateway.forced and request(wc, "GET", f"/tasks/{remote}")["status"] == "running",
        )
        gateway = start_gateway(2)
        cleanup.callback(gateway.stop)
        wait_for(
            lambda: gc.get("/health"), lambda r: r.status_code == 200, timeout=180, process=gateway
        )
        saved = wait_for(lambda: detail(thread, tid), lambda t: t["status"] == "working")
        check(
            "gateway_process_restart_preserves_identity",
            gateway.job.pid != old_pid
            and saved["task_id"] == tid
            and sql_row(tid)["remote_task_id"] == remote
            and request(wc, "GET", f"/tasks/{remote}")["session_id"] == native,
            tracking_id=tid,
            remote_task_id=remote,
            native_session_id=native,
        )
        request(gc, "POST", f"/api/threads/{thread}/mcp-tasks/{tid}/cancel")
        cancelled = wait_for(lambda: detail(thread, tid), lambda t: t["status"] == "cancelled")
        check(
            "http_cancel_confirmed_in_sql_and_worker",
            cancelled["cancel_requested"]
            and sql_row(tid)["status"] == "cancelled"
            and request(wc, "GET", f"/tasks/{remote}")["status"] == "cancelled",
        )

        for prompt, expected in [("fix", "completed"), ("bad-fix", "failed")]:
            thread, tid, remote = submit(prompt)
            data = wait_for(
                lambda thread=thread, tid=tid: detail(thread, tid),
                lambda t, expected=expected: t["status"] == expected,
            )
            check(
                f"background_validation_{expected}",
                data["result"]["validation"]["exit_code"] == (0 if expected == "completed" else 1)
                and sql_row(tid)["status"] == expected,
                tracking_id=tid,
                remote_task_id=remote,
                validation_exit_code=data["result"]["validation"]["exit_code"],
            )

        thread, tid, remote = submit("slow-gateway")
        native = wait_for(
            lambda: request(wc, "GET", f"/tasks/{remote}"), lambda t: t["status"] == "running"
        )["session_id"]
        worker.stop()
        degraded = wait_for(lambda: detail(thread, tid), lambda t: t["tracking_degraded"])
        check(
            "outage_is_retryable_not_terminal",
            not worker.forced and degraded["status"] in {"submitted", "working"},
        )
        worker = start_worker(2)
        cleanup.callback(worker.stop)
        wait_for(lambda: wc.get("/health"), lambda r: r.status_code == 200, process=worker)
        recovered = wait_for(lambda: detail(thread, tid), lambda t: t["status"] == "input_required")
        check(
            "reconnect_requires_explicit_recovery",
            recovered["input_required"]["kind"] == "recovery_required"
            and not recovered["tracking_degraded"]
            and request(wc, "GET", f"/tasks/{remote}")["session_id"] == native,
        )
        trace = [
            json.loads(line) for line in (work / "native/trace.jsonl").read_text().splitlines()
        ]
        check(
            "no_replayed_sessions_or_turns",
            sum(row.get("method") == "thread/start" for row in trace) == 4
            and sum(row.get("method") == "turn/start" for row in trace) == 4,
        )
        check(
            "source_checkout_unchanged",
            subprocess.run(
                ["git", "-C", str(work / "repo"), "diff", "--quiet"], check=False
            ).returncode
            == 0,
        )
        verify_checkout(checkout)
        check("pinned_upstream_unchanged", True)
    receipt["passed"] = True
    receipt["finished_at"] = datetime.now(UTC).isoformat()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Receipt saved: {receipt_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--gateway-python", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--gateway-child", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.gateway_child:
        gateway_child(args.gateway_child)
        return

    def stop_parent(signum, frame):
        raise KeyboardInterrupt("Verification interrupted; stopping owned processes")

    signal.signal(signal.SIGTERM, stop_parent)
    if not (args.checkout and args.gateway_python and args.receipt):
        parser.error("--checkout, --gateway-python and --receipt are required")
    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=False)
        run(
            args.checkout.resolve(),
            args.gateway_python.absolute(),
            args.receipt.resolve(),
            args.work_dir.resolve(),
        )
    else:
        with tempfile.TemporaryDirectory(prefix="deermate-gateway-") as temp:
            run(
                args.checkout.resolve(),
                args.gateway_python.absolute(),
                args.receipt.resolve(),
                Path(temp).resolve(),
            )


if __name__ == "__main__":
    main()
