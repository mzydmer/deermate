#!/usr/bin/env python3
"""Opt-in real chat/model-selected MCP acceptance; never replays an attempted run."""

import argparse
import asyncio
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import stat
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from deermate.bridge import BridgeError, TaskBridge, read_token
from deermate.config import load_settings
from deermate.store import digest

if __package__:
    from .local_docker import PROMPT
else:
    from local_docker import PROMPT


class AcceptanceError(RuntimeError):
    pass


def origin(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (parsed.port is not None and not 1 <= parsed.port <= 65535)
        or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise AcceptanceError("Use an HTTPS origin or a loopback-only HTTP origin.")
    return value.rstrip("/")


def private_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise AcceptanceError("Account/state must be a private regular file.")
        raw = source.read(16_385)
        if len(raw) > 16_384:
            raise AcceptanceError("Account/state exceeded its limit.")
        return json.loads(raw)


def save_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=path.name + ".", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle as target:
            json.dump(data, target, indent=2)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def state_lock(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(
        directory / "verifier.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
    )
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise AcceptanceError("Verifier lock must be a private regular file.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AcceptanceError(
                "Another verifier owns this state; no concurrent run permitted."
            ) from None
        yield
    finally:
        os.close(fd)


def intent(path, *, url, mode, model, project):
    scope = {"origin": url, "mode": mode, "model": model, "project": project}
    if path.exists():
        value = private_json(path)
        if not isinstance(value, dict) or any(
            value.get(key) != item for key, item in scope.items()
        ):
            raise AcceptanceError("Saved intent has a different scope; refusing to replace it.")
        for key in ("thread_id", "key"):
            if not re.fullmatch(r"[0-9a-f]{32}", value.get(key, "")):
                raise AcceptanceError("Saved intent has an invalid stable ID.")
        return value
    value = {
        **scope,
        "thread_id": uuid.uuid4().hex,
        "key": uuid.uuid4().hex,
        "run_attempted": False,
    }
    save_private(path, value)
    return value


def request(client, method, path, **kwargs):
    # No transport retry and no raw response/error body in a receipt or exception.
    with client.stream(method, path, **kwargs) as response:
        if response.status_code >= 300:
            raise AcceptanceError(
                f"Acceptance API rejected a request (HTTP {response.status_code})."
            )
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > 2_000_000:
                raise AcceptanceError("Acceptance API response exceeded its limit.")
            chunks.append(chunk)
        return json.loads(b"".join(chunks))


def run_body(value):
    if value["mode"] == "chat":
        prompt = "Reply exactly DEERMATE_CHAT_OK. Do not call tools or delegate any work."
    else:
        prompt = (
            "This is an authorized acceptance task on a registered disposable test project. "
            "First call deermate_check_worker_connection. Stop if blocked. Then submit exactly "
            "one background task with deermate_submit_task. Do not perform the work yourself, "
            "use other tools, or create another task. Return the task ID after submission; "
            "the runtime tracks completion. Use these exact submission arguments: "
            + json.dumps(
                {"project_id": value["project"], "prompt": PROMPT, "idempotency_key": value["key"]}
            )
        )
    return {
        "input": {"messages": [{"role": "user", "content": prompt}]},
        "context": {
            "model_name": value["model"],
            "thinking_enabled": False,
            "subagent_enabled": False,
        },
        # Middleware consumes graph steps too; this is not an LLM-call quota.
        "config": {"recursion_limit": 128},
        "metadata": {"deermate_acceptance": value["key"]},
    }


def ensure_run(client, path, value):
    thread = "/api/threads/" + value["thread_id"]
    if value["run_attempted"]:
        records = request(client, "GET", thread + "/runs")
        matches = [
            r for r in records if r.get("metadata", {}).get("deermate_acceptance") == value["key"]
        ]
        if len(matches) != 1:
            raise AcceptanceError("Attempted model run cannot be uniquely reconciled; no replay.")
        return matches[0]["run_id"]
    response = client.get(thread)
    if response.status_code == 404:
        request(client, "POST", "/api/threads", json={"thread_id": value["thread_id"]})
    elif response.status_code != 200:
        raise AcceptanceError("Verification thread could not be inspected.")
    value["run_attempted"] = True
    save_private(path, value)
    # Mark intent first. Even if this response is lost, subsequent calls only reconcile.
    result = request(
        client,
        "POST",
        thread + "/runs",
        json=run_body(value),
        headers={"Idempotency-Key": value["key"]},
    )
    return result["run_id"]


def evidence_messages(state):
    messages = state.get("values", {}).get("messages", [])
    calls, texts = [], []
    for message in messages:
        data = message.get("data", message)
        if data.get("type", data.get("role")) not in {"ai", "assistant"}:
            continue
        calls.extend(c.get("name", "") for c in data.get("tool_calls", []))
        content = data.get("content", "")
        if isinstance(content, str):
            texts.append(content)
    return calls, texts


def wait_read(operation, condition, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = operation()
        if condition(value):
            return value
        time.sleep(1)
    raise AcceptanceError("Acceptance deadline exceeded; task outcome is not confirmed stopped.")


async def worker_check(settings, port):
    bridge = TaskBridge(settings.state_dir / "api.token", port)
    try:
        return await bridge.check_connection()
    finally:
        await bridge.close()


async def remote_route_check(config, worker_id, url, instance_id):
    """Prove a pinned public SSH round trip to the independently checked local Worker."""
    from deermate.remote_config import enrolled_worker
    from deermate.ssh import RemoteTaskBridge

    target = enrolled_worker(config, worker_id)
    host = urlsplit(url).hostname
    try:
        public = ipaddress.ip_address(host).is_global
    except ValueError:
        public = False
    if urlsplit(url).scheme != "https" or not public or target.host != host:
        raise AcceptanceError("Remote route must use the control origin's exact public HTTPS host.")
    if target.expected_instance_id != instance_id:
        raise AcceptanceError("SSH enrollment does not match the local Worker instance.")
    bridge = RemoteTaskBridge(config, worker_id)
    try:
        result = await bridge.check_connection()
    finally:
        await bridge.close()
    if result["status"] != "reachable" or result["capabilities"]["instance_id"] != instance_id:
        raise AcceptanceError("Public SSH route to the local Worker was not confirmed.")
    return {
        "kind": "public_control_to_local_worker",
        "checked_at": result["checked_at"],
        "ssh_host_key_pinned": True,
        "worker_instance_matches_local": True,
    }


def native_reference(settings, value, instance_id):
    # Public task views intentionally omit the remote handle and request key.
    # The operator's local verifier may inspect its registered Worker DB read-only.
    uri = (settings.state_dir / "tasks.sqlite3").as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        instance = db.execute("SELECT value FROM metadata WHERE key='instance_id'").fetchone()
        row = db.execute(
            "SELECT task_id, fingerprint FROM requests WHERE key=?", (value["key"],)
        ).fetchone()
    expected = digest(
        {
            "operation": "submit",
            "project_id": value["project"],
            "prompt": PROMPT,
            "idempotency_key": value["key"],
        }
    )
    if (
        not instance
        or instance[0] != instance_id
        or not row
        or row[1] != expected
        or not re.fullmatch(r"[0-9a-f]{32}", row[0])
    ):
        raise AcceptanceError(
            "Local Worker instance/request mapping did not match the saved intent."
        )
    return row[0]


def verify(args):
    with state_lock(args.state_dir):
        return _verify(args)


def _verify(args):
    url = origin(args.url)
    account = private_json(args.account_file)
    if (
        not isinstance(account, dict)
        or set(account) != {"email", "password"}
        or not all(isinstance(x, str) and x for x in account.values())
    ):
        raise AcceptanceError("Account file must contain only email and password.")
    settings = None
    route = None
    controller = getattr(args, "ssh_controller_config", None)
    if controller and args.mode != "dispatch":
        raise AcceptanceError("SSH route evidence requires dispatch mode and a local Worker check.")
    if args.mode == "dispatch":
        if not args.worker_config:
            raise AcceptanceError("Dispatch requires an explicitly registered local Worker config.")
        settings = load_settings(args.worker_config)
        project = settings.projects.get(args.project)
        if not project or not project.allow_write or not project.test_command:
            raise AcceptanceError(
                "Dispatch requires a registered writable project with validation."
            )
        if "return a - b" not in (project.root / "answer.py").read_text():
            raise AcceptanceError("Dispatch only supports the disposable addition-test project.")
        preflight = asyncio.run(worker_check(settings, args.worker_port))
        if preflight["status"] != "reachable":
            raise AcceptanceError("Local Worker preflight failed; no model run attempted.")
        if controller:
            route = asyncio.run(
                remote_route_check(
                    controller, args.ssh_worker, url, preflight["capabilities"]["instance_id"]
                )
            )
    path = args.state_dir / "intent.json"
    value = intent(path, url=url, mode=args.mode, model=args.model, project=args.project)
    with httpx.Client(
        base_url=url, trust_env=False, follow_redirects=False, timeout=30, headers={"Origin": url}
    ) as client:
        response = client.post(
            "/api/v1/auth/login/local",
            data={"username": account["email"], "password": account["password"]},
        )
        if response.status_code != 200:
            raise AcceptanceError("Owner login failed; credentials withheld.")
        client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token", "")
        me = request(client, "GET", "/api/v1/auth/me")
        if me.get("system_role") != "admin":
            raise AcceptanceError("Acceptance requires an existing administrator.")
        if value.get("owner_id", me["id"]) != me["id"]:
            raise AcceptanceError("Saved intent belongs to another owner.")
        value["owner_id"] = me["id"]
        save_private(path, value)
        models = request(client, "GET", "/api/models")["models"]
        if not any(m["name"] == args.model for m in models):
            raise AcceptanceError("Requested model is not configured; no run attempted.")
        run_id = ensure_run(client, path, value)
        run_path = f"/api/threads/{value['thread_id']}/runs/{run_id}"
        run = wait_read(
            lambda: request(client, "GET", run_path),
            lambda r: r["status"] not in {"pending", "running"},
        )
        if run["status"] != "success":
            raise AcceptanceError(
                "Real model run failed; admitted tasks may continue. "
                "Inspect saved thread; no replay."
            )
        thread = "/api/threads/" + value["thread_id"]
        calls, texts = evidence_messages(request(client, "GET", thread + "/state"))
        tasks = request(client, "GET", thread + "/mcp-tasks")
        receipt = {
            "schema_version": 1,
            "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "checked_at": datetime.now(UTC).isoformat(),
            "mode": args.mode,
            "normal_run_api": True,
            "submit_shim_used": False,
            "run_status": run["status"],
            "llm_call_count": run["llm_call_count"],
            "tool_names": sorted(set(calls)),
            "mcp_tasks": len(tasks),
            "cloud_to_home_verified": route is not None,
        }
        if route:
            receipt["network_evidence"] = route
        if args.mode == "chat":
            if calls or tasks or not any("DEERMATE_CHAT_OK" in text for text in texts):
                raise AcceptanceError("Chat response or no-task boundary was not confirmed.")
        else:
            if (
                set(calls) != {"deermate_submit_task", "deermate_check_worker_connection"}
                or calls.count("deermate_submit_task") != 1
                or calls.index("deermate_check_worker_connection")
                > calls.index("deermate_submit_task")
                or len(tasks) != 1
            ):
                raise AcceptanceError(
                    "Expected model tool selection and single task were not confirmed."
                )
            task_path = thread + "/mcp-tasks/" + tasks[0]["task_id"]
            task = wait_read(
                lambda: request(client, "GET", task_path),
                lambda t: t["status"] in {"completed", "failed", "input_required"},
                240,
            )
            if task["status"] != "completed" or task["result"]["validation"]["exit_code"] != 0:
                raise AcceptanceError("Worker completion/independent validation did not pass.")
            native_id = native_reference(settings, value, preflight["capabilities"]["instance_id"])
            with httpx.Client(
                base_url=f"http://127.0.0.1:{args.worker_port}",
                trust_env=False,
                timeout=15,
                headers={"Authorization": "Bearer " + read_token(settings.state_dir / "api.token")},
            ) as worker:
                native = request(worker, "GET", "/tasks/" + native_id)
                current = request(worker, "GET", "/capabilities")
                patch = worker.get(f"/tasks/{native_id}/diff")
                patch.raise_for_status()
            if not (
                native["project_id"] == args.project
                and native["prompt"] == PROMPT
                and native["session_id"]
                and native["session_id"] == task["result"]["session_id"]
                and native["attempt"] == 1
                and current["instance_id"] == preflight["capabilities"]["instance_id"]
                and "-    return a - b" in patch.text
                and "+    return a + b" in patch.text
                and patch.text.count("diff --git ") == 1
                and "diff --git a/answer.py b/answer.py" in patch.text
            ):
                raise AcceptanceError("Independent native identity/patch evidence did not match.")
            receipt.update(
                native_attempt=1,
                independent_validation_exit_code=0,
                expected_patch_verified=True,
                notification_status=task["notification_status"],
            )
        receipt["passed"] = True
        save_private(args.receipt, receipt)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", required=True, help="uses configured model/native quota"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--account-file", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode", choices=["chat", "dispatch"], default="chat")
    parser.add_argument("--project", default="demo")
    parser.add_argument("--worker-config", type=Path)
    parser.add_argument("--worker-port", type=int, default=18777)
    parser.add_argument(
        "--ssh-controller-config",
        type=Path,
        help="also check a registered public SSH route to this local Worker",
    )
    parser.add_argument("--ssh-worker", default="home")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args)
        print(json.dumps(result, indent=2))
    except (
        AcceptanceError,
        BridgeError,
        OSError,
        ValueError,
        KeyError,
        sqlite3.Error,
        httpx.HTTPError,
    ) as error:
        detail = str(error) if isinstance(error, AcceptanceError) else type(error).__name__
        parser.exit(1, f"Secretary acceptance failed: {detail}; no automatic run replay.\n")


if __name__ == "__main__":
    main()
