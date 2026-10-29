import httpx
import pytest
from mcp_helpers import call, mcp_session, wait_status

from deermate.models import State


async def test_stdio_discovery_validation_and_tool_errors(local_server):
    config, port, worker = local_server
    async with mcp_session(config, port) as session:
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} == {
            "submit_task",
            "get_task_status",
            "cancel_task",
            "check_worker_connection",
            "continue_task",
            "get_continuation_status",
            "cancel_continuation_task",
        }
        assert all(tool.inputSchema["additionalProperties"] is False for tool in tools.tools)
        for name, arguments in [
            (
                "submit_task",
                {
                    "project_id": "demo",
                    "prompt": "fix",
                    "idempotency_key": "one",
                    "command": ["arbitrary"],
                },
            ),
            ("submit_task", {"project_id": "demo", "prompt": "", "idempotency_key": "one"}),
            ("get_task_status", {"task_id": "../health"}),
            ("get_task_status", {"task_id": 123}),
            ("unknown_tool", {}),
        ]:
            result = await session.call_tool(name, arguments)
            assert result.isError
        assert not worker.store.list_tasks()
        result = await session.call_tool(
            "submit_task", {"project_id": "unknown", "prompt": "fix", "idempotency_key": "one"}
        )
        assert result.isError and result.structuredContent is None
        result = await call(session, "get_task_status", task_id="a" * 32)
        assert result["status"] == "failed" and result["error_code"] == "task_not_found"
        # A changed token is a call error, not a false terminal task outcome.
        (worker.settings.state_dir / "api.token").write_text("wrong-token" * 5)
        result = await session.call_tool("get_task_status", {"task_id": "a" * 32})
        assert result.isError and result.structuredContent is None
        assert "wrong-token" not in str(result)


async def test_reconnect_duplicate_and_confirmed_cancellation(local_server, settings):
    config, port, worker = local_server
    async with mcp_session(config, port) as first:
        submitted = await call(
            first, "submit_task", project_id="demo", prompt="slow", idempotency_key="stable"
        )
        task_id = submitted["task_id"]
        await wait_status(first, task_id, {State.RUNNING})
        session_id = worker.store.get(task_id).session_id
    # The bridge process is gone. The independently owned Worker is still running.
    assert worker.store.get(task_id).status == State.RUNNING
    async with mcp_session(config, port) as second:
        duplicate = await call(
            second, "submit_task", project_id="demo", prompt="slow", idempotency_key="stable"
        )
        assert duplicate["task_id"] == task_id and duplicate["status"] == "running"
        assert len(worker.store.list_tasks()) == 1
        cancelled = await call(second, "cancel_task", task_id=task_id)
        assert cancelled["status"] == "cancelled"
        assert (await call(second, "cancel_task", task_id=task_id))["status"] == "cancelled"
        assert worker.store.get(task_id).session_id == session_id
    trace = (settings.state_dir.parent / "native/trace.jsonl").read_text()
    assert trace.count('"method": "thread/start"') == 1


@pytest.mark.parametrize("prompt,expected", [("fix", "completed"), ("bad-fix", "failed")])
async def test_stdio_actual_patch_and_validation(local_server, prompt, expected):
    config, port, worker = local_server
    async with mcp_session(config, port) as session:
        task = await call(
            session, "submit_task", project_id="demo", prompt=prompt, idempotency_key="test"
        )
        result = await wait_status(session, task["task_id"], {State.COMPLETED, State.FAILED})
        assert result["status"] == expected
        assert result["result"]["session_id"]
        assert result["result"]["validation"]["exit_code"] == (0 if expected == "completed" else 1)
        assert "prompt" not in result and "policy" not in result
        assert worker.store.get(task["task_id"]).result["diff"]
        duplicate = await call(
            session, "submit_task", project_id="demo", prompt=prompt, idempotency_key="test"
        )
        assert duplicate["task_id"] == task["task_id"] and duplicate["status"] == "running"
        assert (await call(session, "get_task_status", task_id=task["task_id"]))[
            "status"
        ] == expected


async def test_pending_form_is_not_auto_answered(local_server, settings):
    config, port, worker = local_server
    async with mcp_session(config, port) as session:
        task = await call(
            session, "submit_task", project_id="demo", prompt="question", idempotency_key="form"
        )
        result = await wait_status(session, task["task_id"], {State.INPUT_REQUIRED})
        assert result["status"] == "input_required"
        assert result["input_required"]["kind"] == "input_required"
        assert worker.store.get(task["task_id"]).status == State.INPUT_REQUIRED
        token = (settings.state_dir / "api.token").read_text()
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            trust_env=False,
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.post(
                f"/tasks/{task['task_id']}/input", json={"answers": {"choice": ["yes"]}}
            )
            assert response.status_code == 200
        result = await wait_status(session, task["task_id"], {State.COMPLETED, State.FAILED})
        assert result["status"] == "completed"
