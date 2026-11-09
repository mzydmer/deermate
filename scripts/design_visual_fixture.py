"""Local visual fixture: real Go auth/storage + production React + synthetic runtime."""

import json
import os
import secrets
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
work = root / ".deermate/design-auth-20261106"
work.mkdir(mode=0o700, exist_ok=False)
owner = {"email": "visual-fixture@example.com", "password": secrets.token_urlsafe(24)}
(work / "owner.json").write_text(json.dumps(owner))
(work / "owner.json").chmod(0o600)
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
            "validation": {"exit_code": 0, "stdout": "Synthetic fixture only"},
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
memories = {}
logs = []


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
            out = [thread]
        elif "/mcp-tasks" in path:
            key = path.split("/mcp-tasks")[-1].strip("/")
            out = next((x for x in tasks if x["task_id"] == key), None) if key else tasks
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
                    "revision": 1,
                    "updated_at": now,
                }
            out = {
                "revision": 1,
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
        if self.path == "/__visual-fixture":
            content = b'{"fixture":"design-auth-v1","models":"disabled","data":"synthetic"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        control = self.path.startswith(("/api/", "/admin", "/health/"))
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
                    f"http://127.0.0.1:{port}" + self.path,
                    headers=headers,
                    content=self.rfile.read(int(self.headers.get("Content-Length", 0))),
                )
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


runtime = ThreadingHTTPServer(("127.0.0.1", 3303), Runtime)
threading.Thread(target=runtime.serve_forever, daemon=True).start()
env = {
    key: value
    for key, value in os.environ.items()
    if key in {"PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT"}
}
env.update(
    NEXT_TELEMETRY_DISABLED="1",
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
jobs = []
try:
    for name, command, cwd in [
        ("control", [str(root / ".deermate/design-system-20261105/control")], root),
        (
            "frontend",
            [
                "/Users/a123/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
                "node_modules/next/dist/bin/next",
                "start",
                "--hostname",
                "127.0.0.1",
                "--port",
                "3301",
            ],
            root / ".deermate/design-system-20261105/frontend",
        ),
    ]:
        jobs.append(
            subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=(work / (name + ".log")).open("w"),
                stderr=subprocess.STDOUT,
            )
        )
    for _ in range(60):
        try:
            if httpx.get("http://127.0.0.1:3302/health/ready").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
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
