#!/usr/bin/env python3
"""Real Go/Gateway API acceptance, only against an explicitly named offline fixture."""

import argparse
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]


def verify(args):
    parsed = urlsplit(args.url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.port == 2026
    ):
        raise ValueError("Only a separate loopback fixture is supported")
    owner = json.loads(args.owner_file.read_text())
    checks = []
    with httpx.Client(
        base_url=args.url, trust_env=False, follow_redirects=False, timeout=20
    ) as client:
        if client.get("/api/v1/auth/setup-status").json()["needs_setup"]:
            client.post("/api/v1/auth/initialize", json=owner).raise_for_status()
        client.post(
            "/api/v1/auth/login/local",
            data={"username": owner["email"], "password": owner["password"]},
        ).raise_for_status()
        identity = client.get("/api/v1/auth/me").json()
        client.headers.update(
            {"X-CSRF-Token": client.cookies["csrf_token"], "X-Expected-User-Id": identity["id"]}
        )
        catalog = client.get("/api/models").json()
        assert [model["name"] for model in catalog["models"]] == ["continuous-fixture"]
        assert client.get("/api/agent-authorizations").json()["devices"] == []
        checks.append("isolated_fake_model_and_no_devices")

        def api(method, path, body=None):
            result = client.request(method, "/api/me/" + path, json=body)
            result.raise_for_status()
            return result.json()

        cfg = api("GET", "continuous-config")
        if not cfg["config"]["data"].get("enabled"):
            api(
                "PATCH",
                "continuous-config",
                {
                    "enabled": True,
                    "expected_revision": cfg["config"]["revision"],
                    "model": "continuous-fixture",
                    "native_budget": 0,
                },
            )
        assert api("GET", "continuous-config")["config"]["data"]["native_budget"] == 0
        checks.append("default_zero_native_quota")
        thread = None
        for index in range(2):
            body = {
                "operation_id": str(uuid.uuid4()),
                "text": "Synthetic secretary input " + str(index),
            }
            inbox = api("POST", "router/messages", body)
            assert api("POST", "router/messages", body)["id"] == inbox["id"]
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                view = api("GET", "router")
                current = next(v for v in view["items"] if v["id"] == inbox["id"])
                if current["state"] == "settled":
                    assert "离线验收" in current["data"]["reply"]
                    current_thread = view["session"]["data"]["thread_id"]
                    assert thread is None or thread == current_thread
                    thread = current_thread
                    break
                time.sleep(0.25)
            else:
                raise AssertionError("The original Router operation did not settle")
        checks.append("two_router_turns_one_persistent_thread_and_idempotent_input")
        assert (
            client.post("/api/plugins/deermate.continuous/actions/perform", json={}).status_code
            == 403
        )
        checks.append("raw_plugin_route_blocked")
        work = api(
            "POST",
            "work-orders",
            {
                "operation_id": str(uuid.uuid4()),
                "goal": "Synthetic API work",
                "project": "demo",
                "grant_id": "not-configured",
            },
        )
        action = {
            "operation_id": str(uuid.uuid4()),
            "expected_revision": work["revision"],
            "action": "execute",
        }
        assert (
            client.post("/api/me/work-orders/" + work["id"] + "/actions", json=action).status_code
            == 409
        )
        assert api("GET", "work-orders/" + work["id"])["data"]["can_execute"] is False
        checks.append("no_grant_no_native_admission")
        for action in ("pause", "resume", "close"):
            current = api("GET", "work-orders/" + work["id"])
            api(
                "POST",
                "work-orders/" + work["id"] + "/actions",
                {
                    "operation_id": str(uuid.uuid4()),
                    "expected_revision": current["revision"],
                    "action": action,
                },
            )
        assert api("GET", "work-orders/" + work["id"])["state"] == "closed"
        checks.append("work_lifecycle_preserves_closed_state")
        if args.restart_project:
            assert args.restart_project.startswith("deermate-") and args.restart_project.endswith(
                ("-check", "-fixture")
            )
            control = args.restart_project + "-control-1"
            gateway = args.restart_project + "-gateway-1"
            label = subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{ index .Config.Labels "com.docker.compose.project" }}',
                    control,
                ],
                text=True,
            ).strip()
            assert label == args.restart_project

            def sql_count(statement, parameters):
                code = (
                    "import sqlite3;db=sqlite3.connect("
                    "'file:/app/backend/.deer-flow/data/deerflow.db?mode=ro',uri=True);"
                    "print(db.execute("
                    + repr(statement)
                    + ","
                    + repr(parameters)
                    + ").fetchone()[0])"
                )
                return int(
                    subprocess.check_output(
                        ["docker", "exec", gateway, "/app/backend/.venv/bin/python", "-c", code],
                        text=True,
                    )
                )

            assert sql_count("SELECT count(*) FROM mcp_tasks", ()) == 0
            inbox = api(
                "POST",
                "router/messages",
                {"operation_id": str(uuid.uuid4()), "text": "fixture-lost-ack"},
            )
            deadline = time.monotonic() + 30
            operation = None
            while time.monotonic() < deadline:
                latest = next(v for v in api("GET", "router")["items"] if v["id"] == inbox["id"])
                operation = latest["data"].get("operation_id")
                if operation:
                    key = (
                        "http-run:"
                        + hashlib.sha256(
                            (
                                identity["id"]
                                + "\0"
                                + thread
                                + "\0extension:deermate.continuous:"
                                + operation
                            ).encode()
                        ).hexdigest()
                    )
                    if (
                        sql_count("SELECT count(*) FROM runs WHERE idempotency_key=?", (key,)) == 1
                        and sql_count(
                            "SELECT count(*) FROM deermate_work_records "
                            "WHERE kind='operation' AND id=? AND state='dispatching'",
                            (operation,),
                        )
                        == 1
                    ):
                        break
                time.sleep(0.2)
            else:
                raise AssertionError("Lost-ack fixture was not durably admitted")
            subprocess.run(["docker", "restart", control], check=True, stdout=subprocess.DEVNULL)
            deadline = time.monotonic() + 50
            while time.monotonic() < deadline:
                try:
                    latest = next(
                        v for v in api("GET", "router")["items"] if v["id"] == inbox["id"]
                    )
                    if latest["state"] == "settled":
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(0.4)
            else:
                raise AssertionError("Restart did not reconcile the original operation")
            assert sql_count("SELECT count(*) FROM runs WHERE idempotency_key=?", (key,)) == 1
            assert sql_count("SELECT count(*) FROM mcp_tasks", ()) == 0
            assert (
                sql_count(
                    "SELECT deliveries FROM continuous_fixture_deliveries WHERE operation=?",
                    (operation,),
                )
                == 1
            )
            checks.append("go_crash_after_admission_reconciles_one_original_run_without_native")
    receipt = {
        "schema_version": 1,
        "profile": "isolated-offline-continuous",
        "checks": checks,
        "passed": True,
        "real_provider_requests": 0,
        "native_processes": 0,
        "scope": "API/Gateway Fake runs; separate real-model/device/cloud acceptance required",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "passed": True,
                "checks": len(checks),
                "real_provider_requests": 0,
                "native_processes": 0,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--restart-project")
    verify(parser.parse_args())
