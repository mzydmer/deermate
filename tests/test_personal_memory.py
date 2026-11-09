"""Pinned DeerMem contract tests. Run with the frozen Gateway interpreter."""

import hashlib
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("deerflow.agents.memory.backends.deermem.deermem.core.storage")

from deermate.memory import AGENT, PersonalMemory  # noqa: E402


@pytest.fixture
def memory(tmp_path):
    database = tmp_path / "deerflow.db"
    source = (
        Path(__file__).parents[1] / "backend/internal/controlplane/memory_store.go"
    ).read_text()
    ddl = re.search(r"s.DB.Exec\(`(.*?)`\)", source, re.S).group(1)
    scopes_source = (
        Path(__file__).parents[1] / "backend/internal/controlplane/memory_scopes.go"
    ).read_text()
    scopes_ddl = re.search(r"s.DB.Exec\(`(.*?)`\)", scopes_source, re.S).group(1)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE users(id TEXT PRIMARY KEY,disabled INTEGER,needs_setup INTEGER)")
        db.executescript(ddl)
        db.executescript(scopes_ddl)
        for owner in ["alice", "bob"]:
            db.execute("INSERT INTO users VALUES(?,0,0)", (owner,))
            db.execute(
                "INSERT INTO deermate_personal_profiles"
                "(owner,memory_enabled,revision,policy_revision) VALUES(?,1,1,1)",
                (owner,),
            )
    return PersonalMemory(database, tmp_path / "memory")


def admit(memory, key, content="控制端使用 Go，Worker 保留 Python", *, kind="create", fact=None):
    fact = fact or "mem_" + key
    with sqlite3.connect(memory.database) as db:
        db.execute(
            "INSERT OR IGNORE INTO deermate_memory_refs"
            "(id,owner,category,source_id,status,content_hash,updated_at) "
            "VALUES(?,'alice','context',?,'pending',?,1)",
            (fact, key, hashlib.sha256(content.strip().encode()).hexdigest()),
        )
        ref = db.execute("SELECT revision FROM deermate_memory_refs WHERE id=?", (fact,)).fetchone()
        payload = json.dumps(
            {"content": content, "category": "context", "expected_revision": ref[0]}
        )
        db.execute(
            "INSERT INTO deermate_memory_operations(id,owner,fact_id,kind,status,policy_revision,"
            "deletion_revision,request_hash,payload,created_at,lease_until) "
            "VALUES(?,'alice',?,?,'processing',1,0,'hash',?,1,?)",
            (key, fact, kind, payload, int(time.time()) + 90),
        )
        if kind == "update":
            db.execute("UPDATE deermate_memory_refs SET status='updating' WHERE id=?", (fact,))
    return fact


def finish(memory, key, result):
    with sqlite3.connect(memory.database) as db:
        payload = json.loads(
            db.execute(
                "SELECT payload FROM deermate_memory_operations WHERE id=?", (key,)
            ).fetchone()[0]
        )
        db.execute(
            "UPDATE deermate_memory_refs SET status='active',revision=?,content_hash=? "
            "WHERE source_id=?",
            (
                result["revision"],
                hashlib.sha256(payload["content"].strip().encode()).hexdigest(),
                key,
            ),
        )
        db.execute(
            "UPDATE deermate_memory_operations SET status='completed',payload='' WHERE id=?", (key,)
        )


def test_canonical_markdown_cjk_search_and_restart(memory):
    fact = admit(memory, "first")
    result = memory.apply("alice", "first")
    assert result["revision"] == 1
    finish(memory, "first", result)
    body = memory.read("alice", [fact], "控制端")
    assert body["items"][0]["content"].startswith("控制端使用 Go")
    assert list(
        memory.storage._config.storage_path
        and Path(memory.storage._config.storage_path).glob(
            "users/alice/agents/deermate-personal/facts/*/*.md"
        )
    )
    second = PersonalMemory(memory.database, Path(memory.storage._config.storage_path))
    assert second.read("alice", [fact], "Worker")["items"][0]["id"] == fact
    assert fact in second.context("alice", "控制端应该用什么")
    assert second.read("alice", [fact], "unrelatedterm")["items"] == []


def test_lost_ack_reconciles_same_fact_and_revision(memory):
    fact = admit(memory, "lost-ack")
    first = memory.apply("alice", "lost-ack")
    again = memory.apply("alice", "lost-ack")
    assert first == again and first["revision"] == 1
    data = memory.storage.load(user_id="alice", agent_name=AGENT)
    assert [f["id"] for f in data["facts"]] == [fact]


def test_temporary_topic_never_receives_existing_memory_across_turns(memory):
    fact = admit(memory, "temporary-scope", content="以后回答先给结论")
    finish(memory, "temporary-scope", memory.apply("alice", "temporary-scope"))
    with sqlite3.connect(memory.database) as db:
        db.execute(
            "CREATE TABLE deermate_topic_memory(owner TEXT,thread_id TEXT,mode TEXT,"
            "PRIMARY KEY(owner,thread_id))"
        )
        db.execute("INSERT INTO deermate_topic_memory VALUES('alice','private-chat','temporary')")
    for message in ["我喜欢怎样的回答？", "先说结论", "继续上一个问题"]:
        assert memory.context("alice", message, thread="private-chat") == ""
    assert fact in memory.context("alice", "结论", thread="ordinary-chat")
    # A different owner's topic must never change this owner's context policy.
    with sqlite3.connect(memory.database) as db:
        db.execute("INSERT INTO deermate_topic_memory VALUES('bob','ordinary-chat','temporary')")
    assert fact in memory.context("alice", "结论", thread="ordinary-chat")


def test_owner_isolation_and_allowlist_precedes_limit(memory):
    for index in range(15):
        key = "match" + str(index)
        admit(memory, key, "控制端 Go " * (index + 1))
        finish(memory, key, memory.apply("alice", key))
    only = "mem_match0"
    assert memory.read("bob", [only], "Go")["items"] == []
    assert [m["id"] for m in memory.read("alice", [only], "Go")["items"]] == [only]
    with pytest.raises(PermissionError):
        memory.apply("bob", "match0")


def test_forget_barrier_blocks_old_candidate_before_purge(memory):
    fact = admit(memory, "old")
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_personal_profiles SET deletion_revision=1 WHERE owner='alice'")
        db.execute("INSERT INTO deermate_memory_barriers VALUES('alice',?,1,1)", (fact,))
    with pytest.raises(PermissionError):
        memory.apply("alice", "old")
    assert memory._fact("alice", fact) is None


def test_off_disables_injection_but_keeps_management_and_no_shared_summary(memory):
    fact = admit(memory, "saved")
    finish(memory, "saved", memory.apply("alice", "saved"))
    with sqlite3.connect(memory.database) as db:
        db.execute(
            "UPDATE deermate_personal_profiles SET memory_enabled=0,revision=2 WHERE owner='alice'"
        )
    assert memory.context("alice", "Go") == ""
    assert memory.read("alice", [fact])["items"][0]["id"] == fact
    summaries = memory.storage.load(user_id="alice", agent_name=AGENT)["user"]
    assert all(not entry["summary"] for entry in summaries.values())


def test_correction_never_exposes_old_text_while_pending(memory):
    fact = admit(memory, "saved", "控制端使用 Python")
    finish(memory, "saved", memory.apply("alice", "saved"))
    admit(memory, "corrected", "控制端使用 Go", kind="update", fact=fact)
    assert memory.read("alice", [fact])["items"] == []
    result = memory.apply("alice", "corrected")
    assert result["revision"] == 2
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_memory_refs SET source_id='corrected' WHERE id=?", (fact,))
    finish(memory, "corrected", result)
    assert memory.read("alice", [fact], "控制端")["items"][0]["content"] == "控制端使用 Go"


def test_commit_fence_serializes_a_concurrent_forget(memory, monkeypatch):
    admit(memory, "inflight")
    entered, release = threading.Event(), threading.Event()
    original = memory.storage.apply_changes

    def paused(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(memory.storage, "apply_changes", paused)
    failures = []

    def worker():
        try:
            memory.apply("alice", "inflight")
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(5)
        with sqlite3.connect(memory.database, timeout=0.05) as db:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                db.execute("BEGIN IMMEDIATE")
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not failures
    with sqlite3.connect(memory.database) as db:
        db.execute("INSERT INTO deermate_memory_barriers VALUES('alice','mem_inflight',1,1)")
        db.execute("UPDATE deermate_memory_refs SET status='suppressed'")
    assert memory.read("alice", ["mem_inflight"])["items"] == []


@pytest.mark.parametrize(
    "question", ["控制端应该用什么？", [{"type": "text", "text": "控制端应该用什么？"}]]
)
def test_real_agent_assembly_recalls_only_current_owner_enabled_memory(
    memory, monkeypatch, question
):
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from deermate import memory as module
    from deermate.memory_middleware import PersonalMemoryMiddleware
    from deermate.session_middleware import CodingSessionMiddleware

    fact = admit(memory, "model-fact", "控制端使用 Go，Worker 保留 Python")
    finish(memory, "model-fact", memory.apply("alice", "model-fact"))
    monkeypatch.setattr(module, "runtime_memory", lambda: memory)
    with sqlite3.connect(memory.database) as db:
        db.execute("CREATE TABLE runs(run_id TEXT PRIMARY KEY,user_id TEXT,thread_id TEXT)")
        db.executemany(
            "INSERT INTO runs VALUES(?,?,?)",
            [
                ("alice-run", "alice", "new-chat"),
                ("bob-run", "bob", "other-chat"),
                ("temporary-run", "alice", "private-chat"),
            ],
        )
        db.execute(
            "CREATE TABLE deermate_topic_memory(owner TEXT,thread_id TEXT,mode TEXT,"
            "PRIMARY KEY(owner,thread_id))"
        )
        db.execute("INSERT INTO deermate_topic_memory VALUES('alice','private-chat','temporary')")
    seen = []

    class InspectMiddleware(PersonalMemoryMiddleware):
        def wrap_model_call(self, request, handler):
            updated = self._inject(request, self._context(request))
            seen.append(updated.system_message.content)
            return handler(updated)

    graph = create_agent(
        FakeListChatModel(responses=["fixture response"]),
        tools=[],
        middleware=[CodingSessionMiddleware(), InspectMiddleware()],
        system_prompt="Secretary",
    )
    graph.invoke(
        {"messages": [{"role": "user", "content": question}]},
        context={"user_id": "alice", "thread_id": "new-chat", "run_id": "alice-run"},
    )
    assert "控制端使用 Go" in seen[-1] and fact in seen[-1]
    graph.invoke(
        {"messages": [{"role": "user", "content": "控制端应该用什么？"}]},
        context={"user_id": "bob", "thread_id": "other-chat", "run_id": "bob-run"},
    )
    assert "控制端使用 Go" not in seen[-1]
    for context in [
        {"user_id": "alice", "thread_id": "new-chat"},
        {"user_id": "bob", "run_id": "alice-run"},
        {
            "user_id": "alice",
            "thread_id": "new-chat",
            "run_id": "temporary-run",
            "memory_mode": "normal",
        },
    ]:
        graph.invoke({"messages": [{"role": "user", "content": question}]}, context=context)
        assert "控制端使用 Go" not in seen[-1]
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_personal_profiles SET memory_enabled=0 WHERE owner='alice'")
    graph.invoke(
        {"messages": [{"role": "user", "content": "控制端应该用什么？"}]},
        context={"user_id": "alice", "thread_id": "new-chat", "run_id": "alice-run"},
    )
    assert "控制端使用 Go" not in seen[-1]


def test_stable_preference_is_injected_for_an_unrelated_question(memory):
    fact = admit(memory, "language", "回复请使用中文，先给结论")
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_memory_refs SET category='preference' WHERE id=?", (fact,))
        payload = json.dumps(
            {
                "content": "回复请使用中文，先给结论",
                "category": "preference",
                "expected_revision": 0,
            }
        )
        db.execute(
            "UPDATE deermate_memory_operations SET payload=? WHERE id='language'", (payload,)
        )
    finish(memory, "language", memory.apply("alice", "language"))
    assert "回复请使用中文" in memory.context("alice", "How does database replication work?")


def test_out_of_band_body_edit_fails_provenance_check(memory):
    from deermate.memory import MemoryUnavailable

    fact = admit(memory, "saved", "原本明确保存的背景")
    finish(memory, "saved", memory.apply("alice", "saved"))
    path = next(
        Path(memory.storage._config.storage_path).glob(
            f"users/alice/agents/{AGENT}/facts/*/{fact}.md"
        )
    )
    path.write_text(path.read_text().replace("原本明确保存的背景", "未经接纳的另一段背景"))
    with pytest.raises(MemoryUnavailable, match="provenance"):
        memory.read("alice", [fact])


def test_unknown_project_scope_cannot_fall_back_to_personal_memory(memory):
    fact = admit(memory, "project")
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_memory_refs SET scope='project:other' WHERE id=?", (fact,))
    with pytest.raises(PermissionError, match="scope"):
        memory.apply("alice", "project")
    assert memory.read("alice", [fact])["items"] == []
    assert memory.context("alice", "Go") == ""


def save_scoped(memory, key, scope, content):
    fact = admit(memory, key, content=content)
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_memory_refs SET scope=? WHERE id=?", (scope, fact))
    finish(memory, key, memory.apply("alice", key))
    return fact


def test_projects_are_filtered_before_search_and_reused_only_in_their_topic(memory):
    with sqlite3.connect(memory.database) as db:
        db.executemany(
            "INSERT INTO deermate_memory_projects VALUES('alice',?,?)",
            [("project-a", "ProjectA"), ("project-b", "ProjectB")],
        )
    a = save_scoped(memory, "a-backend", "project:project-a", "ProjectA 后端使用 Go")
    b = save_scoped(memory, "b-backend", "project:project-b", "ProjectB 后端使用 Rust")
    with sqlite3.connect(memory.database) as db:
        db.execute("CREATE TABLE deermate_topic_memory(owner TEXT,thread_id TEXT,mode TEXT)")
    context = memory.context("alice", "ProjectA 后端应该用什么", thread="a-chat")
    assert a in context and b not in context
    assert a in memory.context("alice", "继续聊后端", thread="a-chat")
    assert memory.context("alice", "后端应该用什么", thread="unbound-chat") == ""
    assert memory.context("bob", "ProjectA 后端应该用什么") == ""
    context = memory.context("alice", "ProjectB 后端应该用什么", thread="a-chat")
    assert b in context and a not in context
    # An explicitly named new project must clear the old operational binding.
    assert memory.context("alice", "NewProject 后端应该用什么", thread="a-chat") == ""
    assert memory.context("alice", "继续聊后端", thread="a-chat") == ""


def test_stage_memory_is_topic_bound_expires_and_remains_manageable(memory):
    fact = save_scoped(memory, "stage", "topic:prd-chat", "这次只做 PRD，不写代码")
    with sqlite3.connect(memory.database) as db:
        db.execute("CREATE TABLE deermate_topic_memory(owner TEXT,thread_id TEXT,mode TEXT)")
        db.execute(
            "UPDATE deermate_memory_refs SET expires_at=? WHERE id=?", (int(time.time()) + 60, fact)
        )
    assert fact in memory.context("alice", "PRD", thread="prd-chat")
    assert memory.context("alice", "PRD", thread="coding-chat") == ""
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_memory_refs SET expires_at=1 WHERE id=?", (fact,))
    assert memory.context("alice", "PRD", thread="prd-chat") == ""
    assert memory.read("alice", [fact])["items"][0]["id"] == fact


def test_shared_summary_without_source_lineage_is_never_injected(memory):
    admit(memory, "source", "明确保存的项目约束")
    finish(memory, "source", memory.apply("alice", "source"))
    data = memory.storage.load(user_id="alice", agent_name=AGENT)
    data["user"]["personalContext"]["summary"] = "UNSCOPED_PRIVATE_SUMMARY"
    memory.storage.apply_changes(
        {"summaries": {"user": data["user"], "history": data["history"]}},
        user_id="alice",
        agent_name=AGENT,
    )
    context = memory.context("alice", "项目约束")
    assert "明确保存的项目约束" in context and "UNSCOPED_PRIVATE_SUMMARY" not in context


def test_failed_index_rebuild_does_not_scan_all_markdown_files(memory, monkeypatch):
    from deermate.memory import MemoryUnavailable

    fact = admit(memory, "index", "项目约束")
    finish(memory, "index", memory.apply("alice", "index"))
    memory.storage._retrieval_dirty_scopes.add(("alice", AGENT))
    monkeypatch.setattr(memory.storage, "rebuild_index", lambda *a, **k: {"failed": ["fixture"]})
    with pytest.raises(MemoryUnavailable, match="no full-file scan"):
        memory.read("alice", [fact], "项目")


def test_unrelated_deletion_does_not_cancel_an_explicit_single_fact_delivery(memory):
    fact = admit(memory, "independent")
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_personal_profiles SET deletion_revision=1 WHERE owner='alice'")
        db.execute("INSERT INTO deermate_memory_barriers VALUES('alice','another-fact',1,1)")
    result = memory.apply("alice", "independent")
    finish(memory, "independent", result)
    assert memory.read("alice", [fact])["items"][0]["id"] == fact


def captured_source(memory, key="captured"):
    """Use the pinned ORM schema, not a separately invented runtime schema."""
    from deerflow.persistence.run.model import RunRow
    from deerflow.persistence.thread_meta.model import ThreadMetaRow
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite:///" + str(memory.database))
    ThreadMetaRow.__table__.create(engine, checkfirst=True)
    RunRow.__table__.create(engine, checkfirst=True)
    text = "请记住：我偏好简洁的中文回答。"
    fact = admit(memory, key, "我偏好简洁的中文回答。")
    with Session(engine) as session:
        session.add(
            ThreadMetaRow(thread_id="source-thread", user_id="alice", incarnation="gen-one")
        )
        session.add(
            RunRow(
                run_id="source-run",
                thread_id="source-thread",
                user_id="alice",
                status="success",
                operation_kind="run",
                evidence_origin="interactive",
                kwargs_json={
                    "input": {
                        "messages": [{"type": "human", "id": "source-message", "content": text}]
                    }
                },
            )
        )
        session.commit()
    engine.dispose()
    with sqlite3.connect(memory.database) as db:
        db.execute(
            "UPDATE deermate_personal_profiles SET auto_capture_enabled=1 WHERE owner='alice'"
        )
        db.execute(
            "INSERT INTO deermate_memory_sources VALUES(?,'alice','source-thread',"
            "'source-run','source-message',?,'gen-one',1,0,?,?,0)",
            (key, hashlib.sha256(text.encode()).hexdigest(), int(time.time()), int(time.time())),
        )
    return fact


def test_captured_source_roundtrip_and_reference(memory):
    fact = captured_source(memory)
    finish(memory, "captured", memory.apply("alice", "captured"))
    item = memory.read("alice", [fact], "简洁")["items"][0]
    assert item["source"]["thread_id"] == "source-thread"
    assert item["source"]["message_id"] == "source-message"
    assert "简洁" in memory.context("alice", "简洁")


@pytest.mark.parametrize(
    "change",
    [
        "DELETE FROM runs",
        "UPDATE runs SET origin_kind='mcp_notification'",
        "UPDATE runs SET user_id='bob'",
        "UPDATE threads_meta SET incarnation='new-generation'",
        "UPDATE threads_meta SET project_id='new-project'",
        "UPDATE threads_meta SET metadata_json='{\"deerflow_archived\":true}'",
        "UPDATE runs SET kwargs_json='{}'",
    ],
)
def test_captured_source_revocation_precedes_ranking_and_injection(memory, change, monkeypatch):
    fact = captured_source(memory)
    finish(memory, "captured", memory.apply("alice", "captured"))
    with sqlite3.connect(memory.database) as db:
        db.execute(change)

    def no_fact_read(*args, **kwargs):
        raise AssertionError("An unauthorized source reached canonical storage")

    monkeypatch.setattr(memory, "_fact", no_fact_read)
    assert memory.read("alice", [fact], "简洁")["items"] == []
    assert memory.context("alice", "简洁") == ""


def test_capture_generation_and_permission_checked_before_commit(memory):
    fact = captured_source(memory)
    with sqlite3.connect(memory.database) as db:
        db.execute("UPDATE deermate_personal_profiles SET deletion_revision=1 WHERE owner='alice'")
    with pytest.raises(PermissionError):
        memory.apply("alice", "captured")
    assert memory._fact("alice", fact) is None


def test_manual_correction_detaches_old_chat_source(memory):
    fact = captured_source(memory)
    finish(memory, "captured", memory.apply("alice", "captured"))
    admit(memory, "manual-correction", "我偏好详细回答。", kind="update", fact=fact)
    result = memory.apply("alice", "manual-correction")
    with sqlite3.connect(memory.database) as db:
        db.execute(
            "UPDATE deermate_memory_refs SET source_id='manual-correction' WHERE id=?", (fact,)
        )
        db.execute("DELETE FROM runs")
    finish(memory, "manual-correction", result)
    item = memory.read("alice", [fact])["items"][0]
    assert item["content"] == "我偏好详细回答。"
    assert item["source"] is None


def test_edited_source_is_permanently_revoked_after_observation(memory):
    from deerflow.persistence.run.model import RunRow
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    fact = captured_source(memory)
    finish(memory, "captured", memory.apply("alice", "captured"))
    engine = create_engine("sqlite:///" + str(memory.database))
    with Session(engine) as session:
        session.add(
            RunRow(
                run_id="edited-run",
                thread_id="source-thread",
                user_id="alice",
                status="success",
                metadata_json={"replay_kind": "edit", "regenerate_from_run_id": "source-run"},
            )
        )
        session.commit()
    engine.dispose()
    assert memory.read("alice", [fact], "简洁")["items"] == []
    with sqlite3.connect(memory.database) as db:
        assert db.execute("SELECT invalidated_at FROM deermate_memory_sources").fetchone()[0] > 0
        db.execute("DELETE FROM runs WHERE run_id='edited-run'")
    assert memory.context("alice", "简洁") == ""
