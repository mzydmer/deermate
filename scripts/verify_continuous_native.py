#!/usr/bin/env python3
"""Exercise the real driver/relay/Worker path with a synthetic Codex protocol process."""

import argparse
import json
import secrets
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOME = "/app/backend/.deer-flow"
FIXTURE = HOME + "/continuous-native-fixture"


def verify(args):
    parsed = urlsplit(args.url)
    assert parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    assert parsed.port != 2026
    info = json.loads((args.bundle / "bundle.json").read_text())
    project = info["project"]
    assert project.startswith("deermate-") and project.endswith(("-check", "-fixture"))
    gateway = project + "-gateway-1"

    def docker_python(code, value=None):
        return subprocess.check_output(
            ["docker", "exec", "-i", gateway, "/app/backend/.venv/bin/python", "-c", code],
            input=json.dumps(value) if value is not None else "",
            text=True,
        ).strip()

    label = subprocess.check_output(
        [
            "docker",
            "inspect",
            "--format",
            '{{ index .Config.Labels "com.docker.compose.project" }}',
            gateway,
        ],
        text=True,
    ).strip()
    assert label == project
    assert docker_python("import shutil;print(bool(shutil.which('git')))") == "True", (
        "The test-only Gateway image needs Git for its embedded toy Worker; "
        "production Worker stays on the device"
    )
    assert (
        docker_python(
            "import sqlite3;d=sqlite3.connect('" + HOME + "/data/deerflow.db');"
            "assert d.execute('select count(*) from mcp_tasks').fetchone()[0]==0;"
            "assert d.execute('select count(*) from deermate_agent_devices').fetchone()[0]==0;"
            "print('fresh')"
        )
        == "fresh"
    ), "Use a fresh fixture; do not replay an interrupted native test"
    owner = json.loads(args.owner_file.read_text())
    with httpx.Client(base_url=args.url, trust_env=False, timeout=20) as client:
        client.post(
            "/api/v1/auth/login/local",
            data={"username": owner["email"], "password": owner["password"]},
        ).raise_for_status()
        identity = client.get("/api/v1/auth/me").json()
        assert [v["name"] for v in client.get("/api/models").json()["models"]] == [
            "continuous-fixture"
        ]
        client.headers.update(
            {"X-CSRF-Token": client.cookies["csrf_token"], "X-Expected-User-Id": identity["id"]}
        )

        def api(method, path, body=None):
            response = client.request(method, "/api/" + path, json=body)
            if response.is_error:
                raise RuntimeError(f"{method} {path}: {response.status_code} {response.text[:300]}")
            return response.json()

        runtime = args.bundle / "runtime"
        for name in ("fake_codex.py", "continuous_native_fixture.py"):
            (runtime / name).write_text((ROOT / "tests" / name).read_text())
        profile = {
            "enabled": True,
            "command": "/app/backend/.venv/bin/python",
            "args": [
                "-m",
                "deermate.cli",
                "--relay-config",
                HOME + "/agent-authorizations/bridge.json",
                "mcp",
            ],
            "task_toolsets": [
                {
                    "name": "coding",
                    "submit_tool": "submit_task",
                    "status_tool": "get_task_status",
                    "cancel_tool": "cancel_task",
                },
                {
                    "name": "followup",
                    "submit_tool": "continue_task",
                    "status_tool": "get_continuation_status",
                    "cancel_tool": "cancel_continuation_task",
                },
            ],
        }
        docker_python(
            "import json,subprocess,sys;p=json.load(sys.stdin);"
            "subprocess.run([p['command'],*p['args'],'--help'],check=True,"
            "stdout=subprocess.DEVNULL);print('entrypoint-ok')",
            profile,
        )
        path = runtime / "config.yaml"
        config = yaml.safe_load(path.read_text())
        config["extensions"]["mcpServers"] = {"deermate": profile}
        path.write_text(yaml.safe_dump(config, sort_keys=False))
        # This fixture has no pre-existing profiles or native tasks.
        docker_python(
            "import json,sys;from pathlib import Path;"
            "p=Path('" + HOME + "/extensions_config.json');"
            "v=json.loads(p.read_text()) if p.exists() else {};"
            "profile=json.load(sys.stdin);"
            "assert v.get('mcpServers',{}) in ({},{'deermate':profile});"
            "v['mcpServers']={'deermate':profile};"
            "p.write_text(json.dumps(v))",
            profile,
        )
        subprocess.run(["sh", "start.sh"], cwd=args.bundle, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["docker", "restart", gateway], check=True, stdout=subprocess.DEVNULL)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if client.get("/api/models").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        subprocess.run(
            [
                "docker",
                "exec",
                "-d",
                gateway,
                "/bin/sh",
                "-c",
                "/app/backend/.venv/bin/python /etc/deermate/continuous_native_fixture.py "
                "> /app/backend/.deer-flow/continuous-native-fixture.log 2>&1",
            ],
            check=True,
        )
        deadline = time.monotonic() + 20
        descriptor = None
        while time.monotonic() < deadline:
            raw = docker_python(
                "from pathlib import Path;p=Path('"
                + FIXTURE
                + "/descriptor.json');print(p.read_text() if p.exists() else '')"
            )
            if raw:
                descriptor = json.loads(raw)
                break
            time.sleep(0.25)
        assert descriptor and descriptor["profile"] == "fake-codex-protocol-only"
        pairing = api("POST", "device-pairings", {})
        token = secrets.token_urlsafe(32)
        device = str(uuid.uuid4())
        api(
            "POST",
            "agent-devices/pair",
            {
                "pairing_id": pairing["pairing_id"],
                "code": pairing["code"],
                "device_token": token,
                "device": {
                    "id": device,
                    "name": "OFFLINE NATIVE PROTOCOL FIXTURE",
                    "instance_id": descriptor["instance_id"],
                    "projects": ["demo"],
                },
            },
        )
        policy = {
            "projects": ["demo"],
            "operations": ["submit", "status", "continue", "cancel"],
            "duration": "fixed",
            "expires_at": int(time.time()) + 900,
            "expiry_policy": "stop",
        }
        grant = api(
            "POST",
            "agent-authorizations",
            {"device_id": device, "name": "Synthetic toy repository only", "policy": policy},
        )
        with httpx.Client(
            base_url=args.url, trust_env=False, headers={"Authorization": "Bearer " + token}
        ) as local_device:
            local_device.post(
                "/api/agent-devices/confirm",
                json={
                    "grant_id": grant["id"],
                    "version": grant["pending_version"],
                    "policy": policy,
                },
            ).raise_for_status()
        docker_python(
            "import json,sys;from pathlib import Path;p=Path('"
            + FIXTURE
            + "/device.json');p.write_text(json.dumps(json.load(sys.stdin)));p.chmod(0o600)",
            {
                "token": token,
                "instance_id": descriptor["instance_id"],
                "approvals": {grant["id"]: {"version": grant["pending_version"], "policy": policy}},
            },
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            devices = api("GET", "agent-authorizations")["devices"]
            if any(
                v.get("continuous_protocol") == "work-orders-v1"
                and v.get("worker_status") == "reachable"
                for v in devices
            ):
                break
            time.sleep(0.25)
        else:
            raise AssertionError("Synthetic connector did not become ready")
        work = api(
            "POST",
            "me/work-orders",
            {
                "operation_id": str(uuid.uuid4()),
                "goal": "Fix the slow-continuous offline fixture",
                "project": "demo",
                "grant_id": grant["id"],
            },
        )
        ids = []
        try:
            for action, message in (
                ("execute", "Fix the slow-continuous offline fixture"),
                ("followup", "Verify the same fixture again"),
            ):
                body = {
                    "operation_id": str(uuid.uuid4()),
                    "expected_revision": work["revision"],
                    "action": action,
                    "text": message,
                }
                args.output.parent.mkdir(parents=True, exist_ok=True)
                state = args.output.with_suffix(".pending.json")
                state.write_text(json.dumps({"work_id": work["id"], "request": body}))
                state.chmod(0o600)
                api("POST", "me/work-orders/" + work["id"] + "/actions", body)
                if action == "execute":
                    deadline = time.monotonic() + 40
                    while time.monotonic() < deadline:
                        started = docker_python(
                            "from pathlib import Path;p=Path('" + FIXTURE + "/native/trace.jsonl');"
                            "print(p.exists() and 'turn/start' in p.read_text())"
                        )
                        if started == "True":
                            break
                        time.sleep(0.25)
                    else:
                        raise AssertionError("The original Native round did not start")
                    inbox = api(
                        "POST",
                        "me/router/messages",
                        {
                            "operation_id": str(uuid.uuid4()),
                            "text": "Synthetic input while the offline Native round is running",
                        },
                    )
                    deadline = time.monotonic() + 14
                    while time.monotonic() < deadline:
                        items = api("GET", "me/router")["items"]
                        current = next(v for v in items if v["id"] == inbox["id"])
                        if current["state"] == "settled":
                            active = api("GET", "me/work-orders/" + work["id"])
                            assert active["data"].get("active_operation"), (
                                "Native must still be in flight"
                            )
                            break
                        time.sleep(0.25)
                    else:
                        raise AssertionError(
                            "Router did not respond during the delayed Native round"
                        )
                deadline = time.monotonic() + 100
                while time.monotonic() < deadline:
                    work = api("GET", "me/work-orders/" + work["id"])
                    if not work["data"].get("active_operation"):
                        assert work["data"].get("stage") == "completed" and work["data"].get(
                            "verified"
                        ), json.dumps(work)
                        ids.append(work["data"]["head"])
                        break
                    time.sleep(0.4)
                else:
                    raise AssertionError(
                        "Original operation unresolved; inspect it, do not submit a replacement"
                    )
            trace = json.loads(
                docker_python(
                    "import json;from pathlib import Path;from collections import Counter;"
                    "p=Path('" + FIXTURE + "/native/trace.jsonl');"
                    "v=[json.loads(l) for l in p.read_text().splitlines()];"
                    "print(json.dumps(dict(Counter(i.get('method','response') for i in v))))"
                )
            )
            assert (
                trace["thread/start"] == 1
                and trace["thread/resume"] == 1
                and trace["turn/start"] == 2
            )
            assert len(set(ids)) == 2
            operations = [
                v
                for v in api("GET", "me/work-orders/" + work["id"] + "/timeline")["items"]
                if v["kind"] == "operation"
            ]
            roots = {v["data"].get("native_session") for v in operations}
            assert (
                len(operations) == 2 and len(roots) == 1 and None not in roots and "" not in roots
            )
            receipt = {
                "schema_version": 1,
                "passed": True,
                "profile": "actual-go-gateway-driver-relay-worker-fake-native",
                "native_roots": 1,
                "native_rounds": 2,
                "distinct_tracking_ids": 2,
                "independent_validation_passed": True,
                "router_responded_during_native_round": True,
                "trace_counts": trace,
                "real_provider_calls": 0,
                "real_codex_turns": 0,
                "limits": (
                    "Synthetic device confirmation and toy project only; "
                    "not live Codex or production enrollment."
                ),
            }
            args.output.write_text(json.dumps(receipt, indent=2) + "\n")
            state.unlink(missing_ok=True)
            print(json.dumps(receipt))
        finally:
            api(
                "POST",
                "agent-authorizations/" + grant["id"] + "/revocations",
                {"expected_version": grant["pending_version"]},
            )
            docker_python("from pathlib import Path;Path('" + FIXTURE + "/stop').touch()")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    verify(parser.parse_args())
