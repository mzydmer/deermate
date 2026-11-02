"""Opt-in, offline Go/auth/Gateway/DeerMem contract acceptance with synthetic data."""

import argparse
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gateway_child(port):
    def loopback_only(event, args):
        if event == "socket.connect" and isinstance(args[1], tuple):
            if not ipaddress.ip_address(args[1][0]).is_loopback:
                raise RuntimeError("Memory acceptance permits only loopback connections")

    sys.addaudithook(loopback_only)
    import uvicorn

    uvicorn.run("app.gateway.app:app", host="127.0.0.1", port=port, log_level="warning")


def port_number():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(args):
    import httpx
    from verify_deerflow_gateway import Process, child_environment, verify_checkout

    verify_checkout(args.checkout)
    args.work_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    work = args.work_dir.resolve()
    gateway_port, control_port = port_number(), port_number()
    origin = f"http://127.0.0.1:{control_port}"
    config = {
        "config_version": 62,
        "models": [],
        "tools": [],
        "tool_groups": [],
        "plugins": [
            {"name": "deermate-memory", "use": "deermate.memory:install", "required": True}
        ],
        "extensions": {"middlewares": ["deermate.memory_middleware:PersonalMemoryMiddleware"]},
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        "database": {"backend": "sqlite", "sqlite_dir": str(work / "sql")},
        "memory": {"enabled": False},
        "title": {"enabled": False},
        "suggestions": {"enabled": False},
        "scheduler": {"enabled": False},
    }
    (work / "config.yaml").write_text(json.dumps(config))
    (work / "empty.env").touch()
    env = child_environment() | {
        "DEER_FLOW_PROJECT_ROOT": str(work),
        "DEER_FLOW_HOME": str(work / "home"),
        "DEER_FLOW_CONFIG_PATH": str(work / "config.yaml"),
        "DEER_FLOW_ENV_FILE": str(work / "empty.env"),
        "DEER_FLOW_AUTH_DISABLED": "0",
        "AUTH_JWT_SECRET": secrets.token_urlsafe(40),
        "PYTHONPATH": os.pathsep.join([str(args.checkout / "backend"), str(ROOT / "src")]),
        "DEERMATE_RUNTIME_URL": f"http://127.0.0.1:{gateway_port}",
        "DEERMATE_ORIGIN": origin,
        "DEERMATE_ALLOWED_HOSTS": f"127.0.0.1:{control_port}",
        "DEERMATE_LISTEN": f"127.0.0.1:{control_port}",
        "DEERMATE_DATABASE_PATH": str(work / "sql/deerflow.db"),
    }
    processes = []
    checks = []

    def start(generation):
        for name, command in [
            (
                "gateway",
                [
                    str(args.gateway_python),
                    str(Path(__file__).resolve()),
                    "--gateway-child",
                    str(gateway_port),
                ],
            ),
            ("control", [str(args.control_binary.resolve())]),
        ]:
            processes.append(Process(name, command, env, work, work / f"{name}-{generation}.log"))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if any(p.job.poll() is not None for p in processes):
                raise RuntimeError("A local acceptance process exited; inspect private logs")
            try:
                if httpx.get(origin + "/health/ready", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise RuntimeError("Local memory acceptance startup timed out")

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise RuntimeError("Memory acceptance failed: " + name)

    client = httpx.Client(base_url=origin, timeout=30, trust_env=False)

    def request(method, path, body=None, *, status=200, owner=None):
        headers = {"X-CSRF-Token": client.cookies.get("csrf_token", "")}
        if owner:
            headers["X-Expected-User-Id"] = owner
        response = client.request(method, path, json=body, headers=headers)
        if response.status_code != status:
            raise RuntimeError(f"Unexpected {method} {path}: HTTP {response.status_code}")
        return response.json()

    def delivery(method, path, body, owner):
        op = request(method, path, body, status=202, owner=owner)
        # Wait only for the original admitted operation; never submit a new intent.
        deadline = time.monotonic() + 20
        while op["status"] in {"pending", "processing"} and time.monotonic() < deadline:
            time.sleep(0.1)
            op = request("GET", "/api/me/memory-operations/" + op["id"])
        check("delivery_" + body["operation_id"], op["status"] == "completed")
        return op

    def search_memory(query):
        return request(
            "POST", "/api/me/memories/search", {"query": query, "offset": 0}, owner=owner
        )["items"]

    # Reuse the parent dev environment's pure-Python test runner without
    # installing anything into or changing the frozen Gateway environment.
    import pytest

    test_code = (
        "import sys; sys.path.append(sys.argv[1]); import pytest; "
        "sys.exit(pytest.main(['tests/test_personal_memory.py','-q',"
        "'-p','pytest_asyncio.plugin']))"
    )
    subprocess.run(
        [str(args.gateway_python), "-c", test_code, str(Path(pytest.__file__).parent.parent)],
        cwd=ROOT,
        env=env | {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        check=True,
    )

    try:
        start(1)
        user = request(
            "POST",
            "/api/v1/auth/initialize",
            {
                "email": "memory-fixture@example.com",
                "password": secrets.token_urlsafe(24),
            },
            status=201,
        )
        owner = user["id"]
        profile = request("GET", "/api/me/personal-profile")
        check("memory_default_off", not profile["memory_enabled"])
        profile = request(
            "PATCH",
            "/api/me/personal-profile",
            {
                "display_name": "记忆验收",
                "timezone": "Asia/Shanghai",
                "memory_enabled": True,
                "expected_revision": profile["revision"],
            },
            owner=owner,
        )
        check("go_personal_profile", profile["display_name"] == "记忆验收")
        body = {
            "operation_id": "synthetic-create",
            "category": "preference",
            "content": "控制端使用 Python，家庭 Worker 保留 Python",
            "expected_revision": 0,
        }
        first = delivery("POST", "/api/me/memories", body, owner)
        duplicate = delivery("POST", "/api/me/memories", body, owner)
        check("duplicate_intent_one_fact", first["id"] == duplicate["id"])
        found = search_memory("控制端")
        check("chinese_fts5_canonical_read", len(found) == 1 and found[0]["revision"] == 1)
        fact = found[0]
        check(
            "canonical_fact_present",
            len(list((work / "home").glob("personal-memory/users/*/agents/*/facts/*/*.md"))) == 1,
        )
        delivery(
            "PATCH",
            "/api/me/memories/" + fact["id"],
            {
                "operation_id": "synthetic-correct",
                "category": "preference",
                "content": "控制端使用 Go，家庭 Worker 保留 Python",
                "expected_revision": 1,
            },
            owner,
        )
        found = search_memory("控制端")
        check(
            "correction_advances_revision",
            found[0]["revision"] == 2 and "Go" in found[0]["content"],
        )
        for process in reversed(processes):
            process.stop()
        processes.clear()
        start(2)
        retained = search_memory("控制端")
        check(
            "restart_retains_session_profile_and_fact",
            retained == found
            and request("GET", "/api/me/personal-profile")["timezone"] == "Asia/Shanghai",
        )
        request(
            "POST",
            "/api/plugins/deermate.memory/actions/read",
            {"ids": [fact["id"]]},
            status=403,
            owner=owner,
        )
        check("raw_runtime_memory_route_denied", True)
        second_password = secrets.token_urlsafe(24)
        second_user = request(
            "POST",
            "/api/v1/admin/users",
            {
                "email": "memory-second-fixture@example.com",
                "password": second_password,
                "system_role": "user",
            },
            status=201,
        )
        owner_cookies = httpx.Cookies(client.cookies)
        client.cookies.clear()
        login = client.post(
            "/api/v1/auth/login/local",
            data={
                "username": second_user["email"],
                "password": second_password,
            },
        )
        check("ordinary_user_login", login.status_code == 200)
        second_owner = second_user["id"]
        check("other_owner_has_no_facts", request("GET", "/api/me/memories")["items"] == [])
        request("GET", "/api/me/memory-operations/" + first["id"], status=404)
        request("POST", "/api/threads", {}, status=403, owner=second_owner)
        check("ordinary_user_cannot_read_other_job_or_execute", True)
        request(
            "PATCH",
            "/api/me/personal-profile",
            {
                "memory_enabled": True,
                "expected_revision": 0,
            },
            owner=second_owner,
        )
        second_fact = delivery(
            "POST",
            "/api/me/memories",
            {
                "operation_id": "second-owner-create",
                "category": "context",
                "content": "这是第二个合成用户的资料",
                "expected_revision": 0,
            },
            second_owner,
        )
        own = request("GET", "/api/me/memories")["items"]
        check("ordinary_user_memory_is_owner_scoped", len(own) == 1 and own[0]["id"] != fact["id"])
        delivery(
            "DELETE",
            "/api/me/memories/" + second_fact["fact_id"],
            {
                "operation_id": "second-owner-forget",
                "expected_revision": 1,
            },
            second_owner,
        )
        client.cookies = owner_cookies
        profile = request("GET", "/api/me/personal-profile")
        request(
            "PATCH",
            "/api/me/personal-profile",
            {
                "memory_enabled": False,
                "expected_revision": profile["revision"],
            },
            owner=owner,
        )
        check("off_retains_management_read", len(request("GET", "/api/me/memories")["items"]) == 1)
        delivery(
            "DELETE",
            "/api/me/memories/" + fact["id"],
            {
                "operation_id": "synthetic-forget",
                "expected_revision": 2,
            },
            owner,
        )
        check("forgotten_fact_not_returned", request("GET", "/api/me/memories")["items"] == [])
        check(
            "canonical_fact_removed",
            not list((work / "home").glob("personal-memory/users/*/agents/*/facts/*/*.md")),
        )
        receipt = {
            "passed": True,
            "checks": checks,
            "configured_cloud_models": 0,
            "native_tasks": 0,
            "synthetic_data_only": True,
            "pinned_provider_contracts_passed": True,
            "scope": (
                "Go login/API, actual pinned Gateway plugin and DeerMem; "
                "no browser or cloud acceptance"
            ),
            "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in [
                    "src/deermate/memory.py",
                    "src/deermate/memory_middleware.py",
                    "backend/internal/controlplane/memory_store.go",
                    "backend/internal/controlplane/memory.go",
                ]
            },
            "control_binary_sha256": hashlib.sha256(args.control_binary.read_bytes()).hexdigest(),
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps({"passed": True, "checks": len(checks), "configured_cloud_models": 0}))
    finally:
        client.close()
        for process in reversed(processes):
            process.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-child", type=int)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--gateway-python", type=Path)
    parser.add_argument("--control-binary", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.gateway_child:
        gateway_child(args.gateway_child)
    elif all(
        [args.checkout, args.gateway_python, args.control_binary, args.work_dir, args.receipt]
    ):
        args.checkout = args.checkout.resolve()
        # Keep the venv launcher path: resolve() would follow its symlink to the
        # base interpreter and silently discard the frozen Gateway environment.
        args.gateway_python = args.gateway_python.absolute()
        run(args)
    else:
        parser.error("Provide checkout, Gateway Python, control binary, fresh work dir and receipt")


if __name__ == "__main__":
    main()
