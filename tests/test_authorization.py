import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from deermate.api import create_app
from deermate.authorization import admit_remote, private_save
from deermate.models import Conflict, State, SubmitTask
from deermate.worker import Worker


@pytest.mark.asyncio
async def test_connector_refuses_a_worker_without_authorization_enforcement(settings):
    import json

    import httpx

    from deermate.device_connector import process_request

    token = settings.state_dir / "api.token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text("a" * 48)
    token.chmod(0o600)
    policy = {"operations": ["submit"], "projects": ["demo"]}
    state = {"instance_id": "a" * 32, "approvals": {"fixture": {"version": 1, "policy": policy}}}
    packet = {
        "server_time": int(time.time()),
        "grants": [{"id": "fixture", "revoked": False, "version": 1, "active": policy}],
        "request": {
            "id": "request",
            "grant_id": "fixture",
            "version": 1,
            "method": "POST",
            "path": "/tasks",
            "body": {"project_id": "demo"},
            "deadline": int(time.time()) + 15,
        },
    }
    recorded = []

    async def old_worker(request):
        assert request.method == "GET" and request.url.path == "/capabilities"
        return httpx.Response(200, json={"instance_id": "a" * 32})

    async def cloud(request):
        recorded.append(json.loads(request.content))
        return httpx.Response(200, json={"saved": True})

    async with (
        httpx.AsyncClient(base_url="http://cloud", transport=httpx.MockTransport(cloud)) as client,
        httpx.AsyncClient(
            base_url="http://worker", transport=httpx.MockTransport(old_worker)
        ) as local,
    ):
        await process_request(client, local, state, settings, packet)
    assert recorded[0]["status"] == 409
    assert "upgrade" in recorded[0]["body"]["detail"]


def grant_state(settings, **changes):
    policy = {
        "projects": ["demo"],
        "operations": ["submit", "status", "continue", "cancel"],
        "duration": "fixed",
        "expires_at": time.time() + 60,
        "expiry_policy": "finish",
    }
    policy.update(changes)
    data = {
        "observed_at": time.time(),
        "observed_monotonic": time.monotonic(),
        "grants": {"fixture": {"policy": policy, "version": 1, "revoked": False}},
    }
    private_save(settings.state_dir / "remote-authorizations.json", data)
    return data


def test_local_grant_scope_expiry_revocation_and_two_clocks(settings):
    data = grant_state(settings)
    admit_remote(settings, "fixture", "submit", "demo")
    with pytest.raises(Conflict):
        admit_remote(settings, "fixture", "submit", "other")
    data["grants"]["fixture"]["revoked"] = True
    private_save(settings.state_dir / "remote-authorizations.json", data)
    with pytest.raises(Conflict):
        admit_remote(settings, "fixture", "status", "demo")
    data = grant_state(settings, expires_at=time.time() - 1)
    with pytest.raises(Conflict):
        admit_remote(settings, "fixture", "submit", "demo")
    data = grant_state(settings, duration="until_revoked", expires_at=None)
    data["observed_monotonic"] += 100
    private_save(settings.state_dir / "remote-authorizations.json", data)
    with pytest.raises(Conflict):
        admit_remote(settings, "fixture", "submit", "demo")


def test_remote_api_cannot_access_other_tasks_or_resume(settings):
    grant_state(settings)
    with TestClient(create_app(settings, token="a" * 48), base_url="http://127.0.0.1") as client:
        client.headers["Authorization"] = "Bearer " + "a" * 48
        local = client.post(
            "/tasks", json={"project_id": "demo", "prompt": "fixture", "idempotency_key": "local"}
        ).json()
        client.headers["X-Deermate-Authorization"] = "fixture"
        assert client.get("/tasks/" + local["task_id"]).status_code == 409
        assert client.get("/tasks").status_code == 403
        assert (
            client.post(
                "/tasks/" + local["task_id"] + "/resume",
                json={"message": "x", "idempotency_key": "r"},
            ).status_code
            == 403
        )
        data = grant_state(settings, operations=["status"])
        assert (
            client.post(
                "/tasks",
                json={"project_id": "demo", "prompt": "fixture", "idempotency_key": "remote"},
            ).status_code
            == 409
        )
        data["observed_at"] -= 91
        private_save(settings.state_dir / "remote-authorizations.json", data)
        assert client.get("/capabilities").status_code == 409


@pytest.mark.asyncio
async def test_expired_remote_queue_never_starts_native(settings):
    grant_state(settings, expires_at=time.time() - 1)
    worker = Worker(settings)
    policy = settings.policy("demo") | {"authorization": "fixture"}
    task, _ = worker.store.submit(
        SubmitTask(project_id="demo", prompt="must not run", idempotency_key="expired"), policy
    )
    await worker.start()
    try:
        async with asyncio.timeout(3):
            for _ in range(60):
                if worker.store.get(task.task_id).status != State.QUEUED:
                    break
                await asyncio.sleep(0.05)
        observed = worker.store.get(task.task_id)
        assert observed.status == State.CANCELLED
        assert observed.session_id is None
        assert observed.workspace is None
    finally:
        await worker.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry_policy", ["finish", "stop"])
async def test_expiry_respects_running_task_policy(settings, expiry_policy):
    grant_state(settings, expiry_policy=expiry_policy)
    worker = Worker(settings)
    task, _ = worker.store.submit(
        SubmitTask(project_id="demo", prompt="slow fix", idempotency_key="running"),
        settings.policy("demo") | {"authorization": "fixture"},
    )
    await worker.start()
    try:
        for _ in range(100):
            if worker.store.get(task.task_id).status == State.RUNNING:
                break
            await asyncio.sleep(0.05)
        assert worker.store.get(task.task_id).status == State.RUNNING
        grant_state(settings, expires_at=time.time() - 1, expiry_policy=expiry_policy)
        for _ in range(400):
            if worker.store.get(task.task_id).status in {State.COMPLETED, State.CANCELLED}:
                break
            await asyncio.sleep(0.05)
        result = worker.store.get(task.task_id)
        assert result.status == (State.COMPLETED if expiry_policy == "finish" else State.CANCELLED)
        assert result.session_id
    finally:
        await worker.close()


def test_continuous_assignment_cannot_silently_use_newer_grant_or_device(settings):
    from deermate.work_reports import authorize_work, work_prompt

    state = grant_state(settings)
    prompt = work_prompt(
        "work",
        "operation",
        "demo",
        "bounded",
        {"grant_id": "fixture", "version": 1, "instance_id": "device-one"},
    )
    authorize_work(settings, prompt, "demo", "fixture", "device-one", "submit")
    state["grants"]["fixture"]["version"] = 2
    private_save(settings.state_dir / "remote-authorizations.json", state)
    with pytest.raises(Conflict):
        authorize_work(settings, prompt, "demo", "fixture", "device-one", "submit")
    with pytest.raises(Conflict):
        authorize_work(settings, prompt, "demo", "fixture", "device-two", "submit")


def test_continuous_relay_selects_only_frozen_grant_when_projects_overlap(tmp_path):
    from deermate.bridge import BridgeError
    from deermate.relay import RelayDirectoryBridge

    grants = [
        {"id": "one", "version": 1, "instance_id": "a" * 32, "projects": ["demo"]},
        {"id": "two", "version": 2, "instance_id": "b" * 32, "projects": ["demo"]},
    ]
    path = tmp_path / "relay.json"
    private_save(path, {"grants": grants})
    relay = RelayDirectoryBridge(path)
    with pytest.raises(BridgeError):
        relay.target(project="demo")
    selected, native = relay.target(
        project="demo", authorization={"grant_id": "two", "version": 2, "instance_id": "b" * 32}
    )
    assert selected["id"] == "two" and native is None
    with pytest.raises(BridgeError):
        relay.target(
            project="demo", authorization={"grant_id": "two", "version": 1, "instance_id": "b" * 32}
        )
