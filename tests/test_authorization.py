import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from deermate.api import create_app
from deermate.authorization import admit_remote, private_save
from deermate.models import Conflict, State, SubmitTask
from deermate.worker import Worker


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
