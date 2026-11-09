"""Fixed-runtime extraction receipts; every model in this suite is synthetic."""

import asyncio
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("deerflow.agents.memory.backends.deermem.deermem.core.storage")

from test_personal_memory import memory as memory_fixture  # noqa: E402,F401

from deermate import memory_extraction as module  # noqa: E402


@pytest.fixture
def extraction(request, monkeypatch):
    memory = request.getfixturevalue("memory_fixture")
    ddl = re.search(
        r"s.DB.Exec\(`(.*?)`\)",
        (Path(__file__).parents[1] / "backend/internal/controlplane/memory_jobs.go").read_text(),
        re.S,
    ).group(1)
    now = int(time.time())
    text = "我的答复习惯是简短直接"
    with sqlite3.connect(memory.database) as db:
        db.executescript(ddl)
        db.execute("UPDATE deermate_personal_profiles SET auto_capture_enabled=1")
        db.execute(
            "CREATE TABLE runs(run_id TEXT,thread_id TEXT,user_id TEXT,evidence_origin TEXT,"
            "origin_kind TEXT,operation_kind TEXT,kwargs_json TEXT,metadata_json TEXT)"
        )
        db.execute(
            "CREATE TABLE threads_meta(thread_id TEXT,user_id TEXT,"
            "incarnation TEXT,project_id TEXT,metadata_json TEXT DEFAULT '{}')"
        )
        db.execute("CREATE TABLE deermate_topic_memory(owner TEXT,thread_id TEXT,mode TEXT)")
        db.execute("INSERT INTO threads_meta VALUES('topic','alice','generation',NULL,'{}')")
        kwargs = json.dumps(
            {"input": {"messages": [{"id": "user-message", "type": "human", "content": text}]}}
        )
        db.execute(
            "INSERT INTO runs VALUES('run','topic','alice','interactive',NULL,'run',?,'{}')",
            (kwargs,),
        )
        db.execute(
            "INSERT INTO deermate_memory_jobs(id,owner,thread_id,run_id,message_id,message_hash,"
            "incarnation,policy_revision,deletion_revision,observed_at,status,mode,model,"
            "lease_until,created_at,updated_at) "
            "VALUES('job','alice','topic','run','user-message',?,'generation',1,0,?,"
            "'processing','model','fixture',?,?,?)",
            (hashlib.sha256(text.encode()).hexdigest(), now, now + 90, now, now),
        )
    monkeypatch.setattr(module, "runtime_memory", lambda: memory)
    return memory, text


def result(text):
    return json.dumps(
        {
            "candidates": [
                {
                    "content": "答复简短直接",
                    "category": "preference",
                    "scope": "personal",
                    "project": "",
                    "evidence": text,
                }
            ]
        },
        ensure_ascii=False,
    )


def state(memory):
    with sqlite3.connect(memory.database) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute("SELECT * FROM deermate_memory_jobs WHERE id='job'").fetchone())


@pytest.mark.asyncio
async def test_extraction_releases_database_and_reconciles_lost_reply(extraction, monkeypatch):
    memory, text = extraction
    calls = []

    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            # A separate writer succeeds during provider I/O.
            with sqlite3.connect(memory.database, timeout=0.01) as db:
                db.execute("BEGIN IMMEDIATE")
            await asyncio.sleep(0)
            return SimpleNamespace(content=result(text))

    monkeypatch.setattr(module, "bounded_memory_model", lambda _: Model())
    assert (await module.extract("alice", "job"))["state"] == "completed"
    assert state(memory)["provider_state"] == "completed"
    assert (await module.extract("alice", "job"))["known"] is True
    assert len(calls) == 1
    assert len(calls[0][0].content.encode()) + len(calls[0][1].content.encode()) <= 4000


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["pause", "forget", "source", "temporary"])
async def test_late_result_never_restores_invalidated_policy_or_source(
    extraction, monkeypatch, change
):
    memory, text = extraction

    class Model:
        async def ainvoke(self, _):
            with sqlite3.connect(memory.database) as db:
                if change == "pause":
                    db.execute("UPDATE deermate_personal_profiles SET auto_capture_enabled=0")
                elif change == "forget":
                    db.execute("UPDATE deermate_personal_profiles SET deletion_revision=1")
                elif change == "source":
                    db.execute("DELETE FROM runs")
                else:
                    db.execute(
                        "INSERT INTO deermate_topic_memory VALUES('alice','topic','temporary')"
                    )
            return SimpleNamespace(content=result(text))

    monkeypatch.setattr(module, "bounded_memory_model", lambda _: Model())
    assert (await module.extract("alice", "job"))["state"] == "invalidated"
    assert state(memory)["result"] == ""


@pytest.mark.asyncio
async def test_cancelled_provider_claim_is_never_reinvoked(extraction, monkeypatch):
    memory, _ = extraction
    calls = 0

    class Model:
        async def ainvoke(self, _):
            nonlocal calls
            calls += 1
            raise asyncio.CancelledError

    monkeypatch.setattr(module, "bounded_memory_model", lambda _: Model())
    with pytest.raises(asyncio.CancelledError):
        await module.extract("alice", "job")
    assert state(memory)["provider_state"] == "calling"
    assert (await module.extract("alice", "job"))["known"] is False
    assert calls == 1


@pytest.mark.asyncio
async def test_cross_owner_and_secret_source_never_reach_model(extraction, monkeypatch):
    memory, _ = extraction

    def denied(_):
        pytest.fail("unsafe extraction reached model construction")

    monkeypatch.setattr(module, "bounded_memory_model", denied)
    with pytest.raises(PermissionError):
        await module.extract("bob", "job")
    text = "我的答复习惯是带上验证码123456"
    with sqlite3.connect(memory.database) as db:
        db.execute(
            "UPDATE runs SET kwargs_json=?",
            (
                json.dumps(
                    {
                        "input": {
                            "messages": [{"id": "user-message", "type": "human", "content": text}]
                        }
                    }
                ),
            ),
        )
        db.execute(
            "UPDATE deermate_memory_jobs SET message_hash=?",
            (hashlib.sha256(text.encode()).hexdigest(),),
        )
    with pytest.raises(PermissionError):
        await module.extract("alice", "job")
    assert state(memory)["result"] == ""


@pytest.mark.asyncio
async def test_unsubstantiated_or_secret_outputs_are_not_cached(extraction, monkeypatch):
    memory, text = extraction

    class Model:
        async def ainvoke(self, _):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "candidates": [
                            {
                                "content": "喜欢跑步",
                                "category": "preference",
                                "scope": "personal",
                                "evidence": "原文没有的证据",
                            },
                            {
                                "content": "api key: fake_secret_value",
                                "category": "context",
                                "scope": "personal",
                                "evidence": text,
                            },
                        ]
                    }
                )
            )

    monkeypatch.setattr(module, "bounded_memory_model", lambda _: Model())
    await module.extract("alice", "job")
    assert json.loads(state(memory)["result"])["candidates"] == []


@pytest.mark.asyncio
async def test_inbox_uses_go_provenance_and_rejects_event_origin(extraction, monkeypatch):
    memory, text = extraction
    with sqlite3.connect(memory.database) as db:
        db.execute("CREATE TABLE deermate_work_records(owner TEXT,kind TEXT,id TEXT,data TEXT)")
        data = {
            "text": text,
            "origin": "user",
            "_memory_eligible": True,
            "_memory_thread": "router-one",
        }
        db.execute(
            "INSERT INTO deermate_work_records VALUES('alice','inbox','user-message',?)",
            (json.dumps(data),),
        )
        db.execute(
            "INSERT INTO deermate_work_records VALUES('alice','router','router',?)",
            (json.dumps({"thread_id": "router-one"}),),
        )
        db.execute(
            "UPDATE deermate_memory_jobs SET thread_id='router-one',"
            "incarnation='router-one',run_id='inbox:user-message'"
        )
    calls = []

    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content=result(text))

    monkeypatch.setattr(module, "bounded_memory_model", lambda _: Model())
    assert (await module.extract("alice", "job"))["state"] == "completed"
    assert len(calls) == 1
    with sqlite3.connect(memory.database) as db:
        data["origin"] = "event"
        db.execute(
            "UPDATE deermate_work_records SET data=? WHERE kind='inbox'", (json.dumps(data),)
        )
    with pytest.raises(PermissionError):
        await module.extract("alice", "job")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_single_json_fence_is_validated_without_a_second_model_call(extraction, monkeypatch):
    memory, text = extraction
    calls = []

    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content="```json\n" + result(text) + "\n```")

    monkeypatch.setattr(module, "bounded_memory_model", lambda _: Model())
    assert (await module.extract("alice", "job"))["state"] == "completed"
    assert len(calls) == 1 and state(memory)["provider_state"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("job_state", ["processing", "uncertain"])
async def test_provider_failure_retains_only_a_safe_code_and_is_not_replayed(
    extraction, monkeypatch, job_state
):
    memory, _ = extraction
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_memory_jobs SET status=? WHERE id='job'", (job_state,))
    calls = []

    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            raise RuntimeError("synthetic private provider detail")

    monkeypatch.setattr(module, "bounded_memory_model", lambda _: Model())
    with pytest.raises(module.MemoryUnavailable) as failure:
        await module.extract("alice", "job")
    assert "synthetic private" not in str(failure.value)
    record = state(memory)
    assert record["failure_code"] == "provider_error" and record["result"] == ""
    with pytest.raises(PermissionError):
        await module.extract("alice", "job")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_plugin_returns_before_provider_and_background_receipt_is_single(
    extraction, monkeypatch
):
    from deermate import memory as owned

    memory, text = extraction
    monkeypatch.setattr(owned, "runtime_memory", lambda: memory)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            entered.set()
            await release.wait()
            return SimpleNamespace(content=result(text))

    monkeypatch.setattr(module, "bounded_memory_model", lambda _: Model())
    context = SimpleNamespace(principal=SimpleNamespace(user_id="alice", is_internal=False))
    assert (await owned.extract_action({"job_id": "job"}, context))["state"] == "scheduled"
    tasks = list(owned._extraction_tasks)
    await asyncio.wait_for(entered.wait(), 1)
    assert (await owned.extract_action({"job_id": "job"}, context))["state"] == "calling"
    assert len(calls) == 1 and state(memory)["provider_state"] == "calling"
    release.set()
    await asyncio.gather(*tasks)
    assert state(memory)["provider_state"] == "completed" and len(calls) == 1
