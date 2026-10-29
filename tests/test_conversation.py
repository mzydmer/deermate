import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from mcp_helpers import call, mcp_session, wait_status
from ssh_helpers import ssh_worker as ssh_worker

from deermate.bridge import BridgeError, TaskBridge
from deermate.conversation import ConversationError, continue_in_chat
from deermate.models import Conflict, ContinueTask, ResumeTask, State, SubmitTask
from deermate.store import Store


async def test_old_worker_is_rejected_before_continuation_mutation(tmp_path):
    token = tmp_path / "token"
    token.write_text("a" * 40)
    token.chmod(0o600)
    paths = []

    def respond(request):
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "protocol_version": 1,
                "instance_id": "a" * 32,
                "adapter": "codex-app-server",
                "operations": ["submit", "status", "cancel"],
                "remote": False,
            },
        )

    bridge = TaskBridge(token, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(BridgeError, match="upgrade"):
            await bridge.continue_task("a" * 32, "next", "stable")
    finally:
        await bridge.close()
    assert paths == ["/capabilities"]


def completed_root(store):
    task, _ = store.submit(SubmitTask(project_id="demo", prompt="first", idempotency_key="first"))
    return store.update(
        task.task_id,
        status=State.COMPLETED,
        session_id="native-session",
        workspace="workspace",
        base_commit="base",
        result={"summary": "original evidence"},
    )


def test_continuation_keeps_parent_and_head_across_restart(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = Store(path)
    parent = completed_root(store)
    body = ContinueTask(message="explain", idempotency_key="followup")
    child, created = store.continue_task(parent.task_id, body, {})
    assert created and child.task_id != parent.task_id
    assert child.session_id == parent.session_id and child.workspace == parent.workspace
    assert child.parent_task_id == parent.task_id and child.conversation_round == 2
    assert store.get(parent.task_id) == parent
    # Rebuild the additive index from persisted tasks, without reopening an old parent.
    store.db.execute("DROP TABLE conversation_heads")
    store.close()
    store = Store(path)
    again, created = store.continue_task(parent.task_id, body, {})
    assert not created and again == child
    with pytest.raises(Conflict):
        store.continue_task(parent.task_id, body.model_copy(update={"message": "changed"}), {})
    with pytest.raises(Conflict, match="latest"):
        store.resume(parent.task_id, ResumeTask(message="fork", idempotency_key="fork"))
    with pytest.raises(Conflict, match="latest"):
        store.continue_task(parent.task_id, body.model_copy(update={"idempotency_key": "fork"}), {})
    with pytest.raises(Conflict, match="active"):
        store.continue_task(child.task_id, body.model_copy(update={"idempotency_key": "busy"}), {})
    store.close()


def test_concurrent_continuations_admit_one_head(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    first, second = Store(path), Store(path)
    parent = completed_root(first)

    def submit(pair):
        store, key = pair
        try:
            return store.continue_task(
                parent.task_id, ContinueTask(message="follow up", idempotency_key=key), {}
            )[1]
        except Conflict:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(submit, [(first, "a"), (second, "b")])) == [False, True]
    assert len(first.list_tasks()) == 2
    first.close()
    second.close()


@pytest.mark.parametrize(
    "failure", ["session", "workspace", "policy", "recovery", "input", "review"]
)
def test_continuation_refuses_unsafe_parent(tmp_path, failure):
    store = Store(tmp_path / "tasks.sqlite3")
    parent = completed_root(store)
    changes = {
        "session": {"session_id": None},
        "workspace": {"workspace": None},
        "policy": {"policy": {"changed": True}},
        "recovery": {"status": State.RECOVERY_REQUIRED},
        "input": {"status": State.INPUT_REQUIRED},
        "review": {"status": State.NEEDS_REVIEW},
    }
    store.update(parent.task_id, **changes[failure])
    with pytest.raises(Conflict):
        store.continue_task(
            parent.task_id, ContinueTask(message="next", idempotency_key="next"), {}
        )
    assert len(store.list_tasks()) == 1
    store.close()


@pytest.mark.parametrize("remote", [False, True], ids=["local", "ssh"])
async def test_three_mcp_rounds_share_session_preserve_evidence_and_reconnect(
    local_server, ssh_worker, settings, remote
):
    config, port, worker = local_server
    worker_id = None
    if remote:
        config, worker_id = ssh_worker["config"], "home"
    snapshots = []
    for round_number in range(1, 4):
        async with mcp_session(config, port, worker_id=worker_id) as session:
            if round_number == 1:
                submitted = await call(
                    session,
                    "submit_task",
                    project_id="demo",
                    prompt="fix",
                    idempotency_key="round1",
                )
            else:
                arguments = dict(
                    task_id=snapshots[-1]["task_id"],
                    message="explain",
                    idempotency_key=f"round{round_number}",
                )
                submitted = await call(session, "continue_task", **arguments)
                assert (await call(session, "continue_task", **arguments))["task_id"] == submitted[
                    "task_id"
                ]
            result = await wait_status(session, submitted["task_id"], {State.COMPLETED})
            assert result["result"]["conversation_round"] == round_number
            assert result["result"]["validation"]["exit_code"] == 0
            for previous in snapshots:
                assert (
                    await call(session, "get_task_status", task_id=previous["task_id"]) == previous
                )
            snapshots.append(result)
    tasks = worker.store.list_tasks()
    assert len(tasks) == 3
    assert len({task.session_id for task in tasks}) == len({task.workspace for task in tasks}) == 1
    trace = [
        json.loads(line)
        for line in (settings.state_dir.parent / "native/trace.jsonl").read_text().splitlines()
    ]
    assert sum(row.get("method") == "thread/start" for row in trace) == 1
    assert sum(row.get("method") == "thread/resume" for row in trace) == 2
    assert sum(row.get("method") == "turn/start" for row in trace) == 3


def record(**changes):
    return (
        dict(
            id="mcp-task-parent",
            user_id="owner",
            thread_id="chat",
            driver_name="ordinary-tools",
            driver_data={
                "submit_tool": "submit_task",
                "status_tool": "get_task_status",
                "cancel_tool": "cancel_task",
            },
            server_name="deermate",
            task_name="coding",
            remote_task_id="a" * 32,
            status="completed",
            result={"session_id": "native"},
            created_at="2026-10-29T00:00:00Z",
        )
        | changes
    )


class Submitter:
    def __init__(self, records):
        self.records, self.submissions, self.scopes = records, [], []

    async def list_tasks(self, **scope):
        self.scopes.append(scope)
        return self.records

    async def submit(self, **submission):
        self.submissions.append(submission)
        req = submission["request"]
        self.records.insert(
            0,
            record(
                id="mcp-task-child",
                status="working",
                tool_call_id=req.tool_call_id,
                driver_data=req.driver_data,
            ),
        )
        return {"id": "mcp-task-child", "status": "submitted"}


async def followup(submitter, **changes):
    values = dict(
        user_id="owner",
        thread_id="chat",
        incarnation="current-incarnation",
        call_id="call1",
        run_id="run1",
        message="explain",
        task=None,
    )
    return await continue_in_chat(submitter, SimpleNamespace, **(values | changes))


async def test_scoped_provider_translates_private_handle_and_reconciles_saved_call():
    submitter = Submitter([record()])
    result = await followup(submitter)
    assert result["parent_task_id"] == "mcp-task-parent" and "remote_task_id" not in result
    req = submitter.submissions[0]["request"]
    assert req.arguments["task_id"] == "a" * 32
    assert req.driver_data["submit_tool"] == "continue_task"
    assert submitter.scopes[0]["thread_incarnation"] == "current-incarnation"
    assert (await followup(submitter))["reconciled"]
    assert len(submitter.submissions) == 1
    with pytest.raises(ConversationError):
        await followup(submitter, message="changed")


@pytest.mark.parametrize(
    "failure",
    [
        "other_user",
        "other_chat",
        "missing_task",
        "active",
        "recovery",
        "ambiguous",
        "truncated",
        "missing_context",
        "unsupported",
    ],
)
async def test_scoped_provider_rejects_before_submission(failure):
    records = [record()]
    arguments = {}
    if failure == "other_user":
        records = [record(user_id="another")]
    if failure == "other_chat":
        records = [record(thread_id="another")]
    if failure == "missing_task":
        arguments["task"] = "mcp-task-not-in-this-chat"
    if failure in {"active", "recovery"}:
        records = [record(status="working" if failure == "active" else "input_required")]
    if failure == "ambiguous":
        records += [record(id="other", result={"session_id": "other"})]
    if failure == "truncated":
        records *= 50
    if failure == "missing_context":
        arguments["incarnation"] = None
    if failure == "unsupported":
        records = [record(driver_data={})]
    submitter = Submitter(records)
    with pytest.raises(ConversationError):
        await followup(submitter, **arguments)
    assert not submitter.submissions
