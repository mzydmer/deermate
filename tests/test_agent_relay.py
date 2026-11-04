"""Actual Go HTTP + outbound connector + Worker + offline native protocol integration."""

import asyncio
import contextlib
import os
import secrets
import socket
import time
import uuid

import httpx
import pytest

from deermate.authorization import private_json
from deermate.bridge import BridgeError
from deermate.device_connector import install_snapshot, process_request
from deermate.relay import BoundRelayBridge


@pytest.mark.skipif(
    not os.getenv("DEERMATE_GO_BINARY"),
    reason="set compiled Go binary for cross-runtime acceptance",
)
async def test_actual_go_connector_worker_identity_and_idempotency(
    local_server, settings, tmp_path
):
    _, worker_port, worker = local_server

    async def health(reader, writer):
        await reader.read(65536)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
        await writer.drain()
        writer.close()

    upstream = await asyncio.start_server(health, "127.0.0.1", 0)
    runtime_port = upstream.sockets[0].getsockname()[1]
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    origin = f"http://127.0.0.1:{port}"
    auth_home = tmp_path / "cloud" / "agent-authorizations"
    env = dict(
        os.environ,
        AUTH_JWT_SECRET="fixture-bridge-secret-never-production-1234",
        DEERMATE_LISTEN=f"127.0.0.1:{port}",
        DEERMATE_RUNTIME_URL=f"http://127.0.0.1:{runtime_port}",
        DEERMATE_DATABASE_PATH=str(tmp_path / "cloud/data/test.db"),
        DEERMATE_ORIGIN=origin,
        DEERMATE_ALLOWED_HOSTS=f"127.0.0.1:{port}",
        DEERMATE_AUTHORIZATION_HOME=str(auth_home),
    )
    process = await asyncio.create_subprocess_exec(
        os.environ["DEERMATE_GO_BINARY"],
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    pump = None
    bridge = None
    try:
        async with httpx.AsyncClient(base_url=origin, trust_env=False, timeout=20) as browser:
            for _ in range(100):
                try:
                    if (await browser.get("/health/ready")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.05)
            response = await browser.post(
                "/api/v1/auth/initialize",
                json={"email": "relay-fixture@example.com", "password": secrets.token_urlsafe(24)},
            )
            assert response.status_code == 201, response.text
            browser.headers["X-CSRF-Token"] = browser.cookies["csrf_token"]
            response = await browser.post("/api/device-pairings", json={})
            assert response.status_code == 201
            pairing = response.json()
            token = secrets.token_urlsafe(32)
            instance = worker.store.instance_id
            device_id = str(uuid.uuid4())
            response = await browser.post(
                "/api/agent-devices/pair",
                json={
                    "pairing_id": pairing["pairing_id"],
                    "code": pairing["code"],
                    "device_token": token,
                    "device": {
                        "id": device_id,
                        "name": "Fixture Mac",
                        "instance_id": instance,
                        "projects": ["demo"],
                    },
                },
            )
            assert response.status_code == 201
            policy = {
                "projects": ["demo"],
                "operations": ["submit", "status", "continue", "cancel"],
                "duration": "fixed",
                "expires_at": int(time.time()) + 120,
                "expiry_policy": "stop",
            }
            response = await browser.post(
                "/api/agent-authorizations",
                json={"device_id": device_id, "name": "Fixture Codex", "policy": policy},
            )
            assert response.status_code == 201
            grant = response.json()
            assert grant["active"] is None
            async with (
                httpx.AsyncClient(
                    base_url=origin,
                    headers={"Authorization": "Bearer " + token},
                    trust_env=False,
                    timeout=20,
                ) as device,
                httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{worker_port}", trust_env=False
                ) as local,
            ):
                response = await device.post(
                    "/api/agent-devices/confirm",
                    json={"grant_id": grant["id"], "version": 1, "policy": policy},
                )
                assert response.status_code == 200, response.text
                state = {
                    "approvals": {grant["id"]: {"version": 1, "policy": policy}},
                    "instance_id": instance,
                }

                async def poll():
                    while True:
                        response = await device.post(
                            "/api/agent-devices/poll", json={"worker_status": "reachable"}
                        )
                        response.raise_for_status()
                        packet = response.json()
                        install_snapshot(packet, state, settings)
                        await process_request(device, local, state, settings, packet)
                        await asyncio.sleep(0.05)

                pump = asyncio.create_task(poll())
                bridge = BoundRelayBridge(
                    origin, private_json(auth_home / "bridge.json")["grants"][0]
                )
                assert (await bridge.check_connection())["status"] == "reachable"
                submitted = await bridge.submit("demo", "fix", "relay-one")
                duplicate = await bridge.submit("demo", "fix", "relay-one")
                assert submitted["task_id"] == duplicate["task_id"]
                for _ in range(100):
                    result = await bridge.status(submitted["task_id"])
                    if result["status"] in {"completed", "failed"}:
                        break
                    await asyncio.sleep(0.05)
                assert result["status"] == "completed", result
                assert result["result"]["validation"]["exit_code"] == 0
                assert len(worker.store.list_tasks()) == 1
                task = worker.store.get(submitted["task_id"])
                assert task.policy["authorization"] == grant["id"]
                assert task.session_id
                response = await browser.post(
                    "/api/agent-authorizations/" + grant["id"] + "/revocations",
                    json={"expected_version": 1},
                )
                assert response.status_code == 202
                with pytest.raises(BridgeError):
                    await bridge.submit("demo", "fix", "must-not-admit")
                assert len(worker.store.list_tasks()) == 1
                assert (await browser.get("/admin/agents")).status_code == 200
    finally:
        if pump:
            pump.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump
        if bridge:
            await bridge.close()
        process.terminate()
        await asyncio.wait_for(process.wait(), 5)
        upstream.close()
        await upstream.wait_closed()
