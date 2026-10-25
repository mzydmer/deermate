import asyncio
import json

import httpx
import pytest

from deermate.api import create_app, token_file
from deermate.bridge import BridgeError, TaskBridge, read_token, snapshot
from deermate.models import State, SubmitTask
from deermate.store import Store


@pytest.fixture
def token_path(tmp_path):
    token_file(tmp_path / "auth")
    return tmp_path / "auth/api.token"


@pytest.fixture
def task(settings):
    store = Store(settings.state_dir / "test.sqlite3")
    result, _ = store.submit(
        SubmitTask(project_id="demo", prompt="private prompt", idempotency_key="first"),
        settings.policy("demo"),
    )
    store.close()
    return result


@pytest.mark.parametrize("state", list(State))
def test_all_states_preserve_outcome_and_attention(task, state):
    data = snapshot(task.model_copy(update={"status": state}))
    assert data["worker_status"] == state
    if state in {State.COMPLETED, State.FAILED, State.CANCELLED}:
        assert data["status"] == state
    elif state in {State.INPUT_REQUIRED, State.NEEDS_REVIEW, State.RECOVERY_REQUIRED}:
        assert data["status"] == "input_required"
        assert data["input_required"]["kind"] == state
    else:
        assert data["status"] == "running"


def test_result_is_bounded_without_private_task_configuration(task):
    task.status = State.COMPLETED
    task.result = {
        "summary": "x" * 64000,
        "diff": "private patch" * 100000,
        "validation_status": "passed",
        "validation": {"exit_code": 0, "stdout": "o" * 64000, "stderr": "e" * 64000},
    }
    data = snapshot(task)
    encoded = json.dumps(data)
    assert len(encoded) < 10000
    for text in ["private prompt", "private patch", str(task.policy["project"]["root"])]:
        assert text not in encoded
    assert "policy" not in data and "prompt" not in data
    assert data["result"]["summary_truncated"]
    assert data["result"]["validation"]["output_truncated"]
    assert data["result"]["validation"]["exit_code"] == 0


@pytest.mark.parametrize("status", [401, 403, 409, 422, 503, 302])
async def test_http_errors_are_call_failures_not_task_failures(token_path, status):
    def respond(request):
        return httpx.Response(status, text="secret token, private host path")

    bridge = TaskBridge(token_path, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(BridgeError) as error:
            await bridge.status("a" * 32)
        assert "secret" not in str(error.value) and "private host" not in str(error.value)
    finally:
        await bridge.close()


async def test_missing_task_is_structured_and_bad_ids_never_reach_worker(token_path):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(404)

    bridge = TaskBridge(token_path, transport=httpx.MockTransport(respond))
    try:
        for operation in [bridge.status, bridge.cancel]:
            result = await operation("a" * 32)
            assert result["status"] == "failed" and result["error_code"] == "task_not_found"
            with pytest.raises(BridgeError):
                await operation("../capabilities")
        assert len(requests) == 2
        with pytest.raises(BridgeError, match="Project is not registered"):
            await bridge.submit("unknown", "fix", "first")
    finally:
        await bridge.close()


async def test_unavailable_worker_and_invalid_response_do_not_terminalize(token_path, task):
    for value in ["offline", "invalid", "oversized", "mismatched"]:

        def respond(request, value=value):
            if value == "offline":
                raise httpx.ConnectError("private endpoint and credential", request=request)
            if value == "invalid":
                return httpx.Response(200, text="not JSON")
            if value == "oversized":
                return httpx.Response(200, content=b"x" * 2_000_001)
            return httpx.Response(200, json=task.model_dump(mode="json"))

        bridge = TaskBridge(token_path, transport=httpx.MockTransport(respond))
        try:
            with pytest.raises(BridgeError) as error:
                await bridge.status("b" * 32)
            assert "private endpoint" not in str(error.value)
        finally:
            await bridge.close()


@pytest.mark.parametrize("state", [State.CANCELLING, State.RECOVERY_REQUIRED, State.NEEDS_REVIEW])
async def test_unconfirmed_cancel_is_never_stopped(token_path, task, state):
    task.status = state
    bridge = TaskBridge(
        token_path,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=task.model_dump(mode="json"))
        ),
        cancel_timeout=0.03,
    )
    try:
        with pytest.raises(BridgeError, match="unconfirmed|not confirmed"):
            await bridge.cancel(task.task_id)
    finally:
        await bridge.close()


@pytest.mark.parametrize("state", [State.COMPLETED, State.FAILED, State.CANCELLED])
async def test_cancel_keeps_terminal_race_outcome(token_path, task, state):
    task.status = state
    bridge = TaskBridge(
        token_path,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=task.model_dump(mode="json"))
        ),
    )
    try:
        assert (await bridge.cancel(task.task_id))["status"] == state
    finally:
        await bridge.close()


def test_token_read_does_not_create_or_follow_or_disclose(tmp_path):
    path = tmp_path / "api.token"
    with pytest.raises(BridgeError):
        read_token(path)
    assert not path.exists()
    path.write_text("private" * 8)
    path.chmod(0o644)
    with pytest.raises(BridgeError, match="private regular"):
        read_token(path)
    path.chmod(0o600)
    assert read_token(path) == "private" * 8
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(BridgeError):
        read_token(link)


async def test_bridge_uses_existing_worker_without_acquiring_its_database(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        bridge = TaskBridge(
            settings.state_dir / "api.token", transport=httpx.ASGITransport(app=app)
        )
        try:
            created = await bridge.submit("demo", "fix", "first")
            duplicate = await bridge.submit("demo", "fix", "first")
            assert created["task_id"] == duplicate["task_id"]
            with pytest.raises(BridgeError, match="conflicts"):
                await bridge.submit("demo", "changed", "first")
            assert len(app.state.worker.store.list_tasks()) == 1
        finally:
            await bridge.close()


async def test_worker_restart_exposes_recovery_without_replay(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        bridge = TaskBridge(
            settings.state_dir / "api.token", transport=httpx.ASGITransport(app=app)
        )
        try:
            created = await bridge.submit("demo", "slow", "stable")
            task_id = created["task_id"]
            async with asyncio.timeout(5):
                while True:
                    if (await bridge.status(task_id))["worker_status"] == "running":
                        break
                    await asyncio.sleep(0.02)
            session_id = app.state.worker.store.get(task_id).session_id
        finally:
            await bridge.close()
    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        bridge = TaskBridge(
            settings.state_dir / "api.token", transport=httpx.ASGITransport(app=restarted)
        )
        try:
            status = await bridge.status(task_id)
            assert status["status"] == "input_required"
            assert status["input_required"]["kind"] == "recovery_required"
            assert (await bridge.submit("demo", "slow", "stable"))["task_id"] == task_id
            assert not restarted.state.worker.store.queued()
            assert restarted.state.worker.store.get(task_id).session_id == session_id
            with pytest.raises(BridgeError, match="unconfirmed"):
                await bridge.cancel(task_id)
        finally:
            await bridge.close()
