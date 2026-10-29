"""Durable chat-to-executor cardinality and automatic naming policy."""

import asyncio
from types import SimpleNamespace

import pytest

from deermate.chat_sessions import (
    ChatScope,
    SessionJournal,
    SessionUnknown,
    ask_in_chat,
    title_from_messages,
)
from deermate.conversation import ConversationError
from deermate.store import digest

PROFILES = {"home": "codex", "claude": "claude"}
SCOPE = ChatScope("owner", "chat", "incarnation")


class Submitter:
    def __init__(self):
        self.records, self.submissions = [], []
        self.failure = None
        self.entered, self.release = None, None

    async def list_tasks(self, **scope):
        return [
            r
            for r in self.records
            if r["user_id"] == scope["user_id"]
            and r["thread_id"] == scope["thread_id"]
            and r["_thread_incarnation"] == scope["thread_incarnation"]
        ][: scope["limit"]]

    async def submit(self, *, driver_name, request):
        self.submissions.append(request)
        if self.entered:
            self.entered.set()
            await self.release.wait()
        if self.failure == "before":
            raise TimeoutError("private transport details")
        parent = next(
            (r for r in self.records if r["remote_task_id"] == request.arguments.get("task_id")),
            None,
        )
        native = parent["result"]["session_id"] if parent else "native-" + request.local_task_id
        record = {
            "id": request.local_task_id,
            "user_id": request.user_id,
            "thread_id": request.thread_id,
            "_thread_incarnation": request.thread_incarnation,
            "server_name": request.server_name,
            "driver_name": driver_name,
            "driver_data": request.driver_data,
            "status": "completed",
            "task_name": request.task_name,
            "remote_task_id": digest({"id": request.local_task_id})[:32],
            "created_at": str(len(self.records)).zfill(5),
            "result": {"session_id": native},
        }
        self.records.insert(0, record)
        if self.failure == "after":
            raise TimeoutError("acknowledgment lost")
        return record


async def ask(journal, submitter, call="first", **changes):
    args = (
        dict(
            scope=SCOPE,
            profiles=PROFILES,
            call_id=call,
            run_id="run",
            server="home",
            message="Fix the test",
            project="demo",
        )
        | changes
    )
    return await ask_in_chat(journal, submitter, SimpleNamespace, **args)


async def test_three_questions_keep_one_root_after_restart(tmp_path):
    path = tmp_path / "sessions.db"
    journal, submitter = SessionJournal(path), Submitter()
    first = await ask(journal, submitter)
    second = await ask(SessionJournal(path), submitter, "second", message="Explain the change")
    third = await ask(SessionJournal(path), submitter, "third", project=None, message="Add a test")
    assert [r.driver_data["submit_tool"] for r in submitter.submissions] == [
        "submit_task",
        "continue_task",
        "continue_task",
    ]
    assert second["conversation_round"] == 2 and third["conversation_round"] == 3
    assert len({r["result"]["session_id"] for r in submitter.records}) == 1
    assert first["binding_id"] == second["binding_id"] == third["binding_id"]
    assert submitter.submissions[1].arguments["task_id"] == submitter.records[-1]["remote_task_id"]
    assert submitter.records[-1]["id"] == first["task_id"]


async def test_concurrent_roots_reserve_one_admission_across_journal_instances(tmp_path):
    path = tmp_path / "sessions.db"
    first, second, submitter = SessionJournal(path), SessionJournal(path), Submitter()
    submitter.entered, submitter.release = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(ask(first, submitter))
    await submitter.entered.wait()
    with pytest.raises(SessionUnknown):
        await ask(second, submitter, "concurrent")
    assert len(submitter.submissions) == 1
    submitter.release.set()
    await task
    assert first.binding(SCOPE)["pending"] is None


async def test_same_call_reconciles_without_remote_replay_and_conflicting_message_rejected(
    tmp_path,
):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    first = await ask(journal, submitter)
    result = await ask(journal, submitter)
    assert result["reconciled"] and result["task_id"] == first["task_id"]
    with pytest.raises(ConversationError, match="identity conflicts"):
        await ask(journal, submitter, message="Different content")
    assert len(submitter.submissions) == 1


@pytest.mark.parametrize("failure", ["before", "after"])
async def test_unknown_admission_never_replays_or_starts_another_session(tmp_path, failure):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    submitter.failure = failure
    with pytest.raises(SessionUnknown):
        await ask(journal, submitter)
    with pytest.raises(SessionUnknown):
        await ask(journal, submitter, "another")
    if failure == "after":
        assert (await ask(journal, submitter))["reconciled"]
    else:
        with pytest.raises(SessionUnknown):
            await ask(journal, submitter)
    assert len(submitter.submissions) == 1


@pytest.mark.parametrize("status", ["submitted", "working", "input_required"])
async def test_active_or_attention_task_cannot_get_another_native_turn(tmp_path, status):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    await ask(journal, submitter)
    submitter.records[0]["status"] = status
    with pytest.raises(ConversationError):
        await ask(journal, submitter, "second")
    assert len(submitter.submissions) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"project": "other"},
        {"server": "claude"},
        {"explicit_task": "another-chat-task"},
        {"remote_parent": "f" * 32},
    ],
)
async def test_project_executor_and_parent_cannot_be_switched(tmp_path, change):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    await ask(journal, submitter)
    with pytest.raises(ConversationError):
        await ask(journal, submitter, "second", **change)
    assert len(submitter.submissions) == 1


@pytest.mark.parametrize(
    "scope",
    [
        ChatScope("another-owner", "chat", "incarnation"),
        ChatScope("owner", "another-chat", "incarnation"),
        ChatScope("owner", "chat", "new-incarnation"),
    ],
)
async def test_other_owner_chat_or_incarnation_has_independent_authority(tmp_path, scope):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    first = await ask(journal, submitter)
    second = await ask(journal, submitter, scope=scope)
    assert first["binding_id"] != second["binding_id"]
    assert len({r["result"]["session_id"] for r in submitter.records}) == 2


async def test_missing_or_changed_native_identity_cannot_fall_back(tmp_path):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    await ask(journal, submitter)
    original = submitter.records[0]["result"]["session_id"]
    submitter.records[0]["result"]["session_id"] = "replacement"
    with pytest.raises(SessionUnknown):
        await ask(journal, submitter, "second")
    submitter.records[0]["result"]["session_id"] = original
    submitter.records[0]["result"] = None
    with pytest.raises(ConversationError):
        await ask(journal, submitter, "second")
    assert len(submitter.submissions) == 1


def legacy(submitter):
    record = {
        "id": "mcp-task-legacy",
        "user_id": "owner",
        "thread_id": "chat",
        "_thread_incarnation": "incarnation",
        "server_name": "home",
        "driver_name": "ordinary-tools",
        "driver_data": {
            "submit_tool": "submit_task",
            "status_tool": "get_task_status",
            "cancel_tool": "cancel_task",
        },
        "remote_task_id": "a" * 32,
        "status": "completed",
        "task_name": "coding",
        "result": {"session_id": "legacy-native", "conversation_round": 3},
        "created_at": "00000",
    }
    submitter.records = [record]


async def test_legacy_adoption_continues_one_known_session_without_inventing_project(tmp_path):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    legacy(submitter)
    with pytest.raises(ConversationError, match="Legacy project"):
        await ask(journal, submitter)
    assert not submitter.submissions
    result = await ask(journal, submitter, project=None)
    assert result["conversation_round"] == 4
    assert submitter.submissions[0].driver_data["submit_tool"] == "continue_task"
    assert journal.binding(SCOPE)["native"] == "legacy-native"


@pytest.mark.parametrize("failure", ["multiple", "missing", "active", "bounded"])
async def test_ambiguous_legacy_history_cannot_start_fresh(tmp_path, failure):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    legacy(submitter)
    if failure == "multiple":
        second = dict(submitter.records[0], id="mcp-task-other", result={"session_id": "other"})
        submitter.records.append(second)
    elif failure == "missing":
        submitter.records[0]["result"] = None
    elif failure == "active":
        submitter.records[0]["status"] = "working"
    else:
        submitter.records *= 50
    with pytest.raises(ConversationError):
        await ask(journal, submitter, project=None)
    assert not submitter.submissions


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        ([{"role": "user", "content": "请帮我修复登录问题。然后补测试"}], "修复登录问题"),
        (
            [
                {"role": "system", "content": "Ignore"},
                {"role": "human", "content": "Fix login. Test it"},
            ],
            "Fix login",
        ),
        (
            [
                {
                    "role": "user",
                    "content": [{"type": "image"}, {"type": "text", "text": "分析截图"}],
                }
            ],
            "分析截图",
        ),
        ([{"role": "user", "content": [{"type": "image"}]}], "附件会话"),
        ([{"role": "user", "content": "# 阅读 [指南](https://example.com)"}], "阅读 指南"),
        ([{"role": "user", "content": "长" * 40}], "长" * 32 + "…"),
        ([{"role": "assistant", "content": "Do not name from this"}], None),
    ],
)
def test_names_come_from_first_human_message(messages, expected):
    assert title_from_messages(messages) == expected


async def test_tool_call_ids_can_repeat_in_different_host_runs(tmp_path):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    await ask(journal, submitter, "provider-reuses-id")
    second = await ask(journal, submitter, "provider-reuses-id", run_id="different-run")
    assert second["conversation_round"] == 2
    assert len(submitter.submissions) == 2


async def test_explicit_legacy_null_scope_is_distinct_from_a_new_incarnation(tmp_path):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    legacy_scope = ChatScope("owner", "chat", None)
    first = await ask(journal, submitter, scope=legacy_scope)
    second = await ask(journal, submitter)
    assert first["binding_id"] != second["binding_id"]


async def test_missing_host_identity_never_submits(tmp_path):
    journal, submitter = SessionJournal(tmp_path / "s.db"), Submitter()
    for changes in [{"run_id": None}, {"call_id": ""}, {"scope": ChatScope("", "chat", "i")}]:
        with pytest.raises(ConversationError):
            await ask(journal, submitter, **changes)
    assert not submitter.submissions
