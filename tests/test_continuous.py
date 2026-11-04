"""Owned continuous adapter/graph contracts. No provider or native process calls."""

import json
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("deerflow.config")

from deermate import briefing, continuous  # noqa: E402
from deermate import continuous_middleware as middleware  # noqa: E402


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "authority.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE users(id TEXT PRIMARY KEY,system_role TEXT,disabled INTEGER,
                needs_setup INTEGER,token_version INTEGER);
            INSERT INTO users VALUES('alice','admin',0,0,1);
            CREATE TABLE runs(run_id TEXT,user_id TEXT,thread_id TEXT,
                kwargs_json TEXT,metadata_json TEXT,idempotency_key TEXT);
            CREATE TABLE threads_meta(thread_id TEXT,user_id TEXT,incarnation TEXT,
                metadata_json TEXT,project_id TEXT);
            INSERT INTO threads_meta VALUES('execution','alice','inc','{}',NULL);
            CREATE TABLE deermate_agent_grants(owner TEXT,id TEXT,data TEXT);
        """)
        source = (
            Path(__file__).parents[1] / "backend/internal/controlplane/continuous_store.go"
        ).read_text()
        db.executescript(re.search(r"s.DB.Exec\(`(.*?)`\)", source, re.S).group(1))
    monkeypatch.setattr(briefing, "database", lambda: path)
    monkeypatch.setattr(middleware, "database", lambda: path)

    def put(identifier, kind, data, state="dispatching", parent=""):
        with sqlite3.connect(path) as db:
            db.execute(
                "INSERT OR REPLACE INTO deermate_work_records VALUES(?,?,?,?,?,?,?,?,?)",
                (identifier, kind, "alice", parent, state, 1, 1, 1, json.dumps(data)),
            )

    put("settings", "settings", {"enabled": True}, "enabled")
    return path, put


def operation(put, kind="router", **changes):
    data = {
        "kind": kind,
        "_nonce": "opaque",
        "_user_version": 1,
        "thread_id": "router",
        "model": "fixture",
        **changes,
    }
    put("operation", "operation", data, parent="work")
    return {"owner": "alice", "id": "operation", "data": data}


def context():
    return SimpleNamespace(principal=SimpleNamespace(user_id="alice", is_internal=False))


@pytest.mark.parametrize("change", [{"nonce": "wrong"}, {"operation_id": "foreign"}])
def test_capability_cannot_select_another_operation(ledger, change):
    _, put = ledger
    operation(put)
    with pytest.raises(PermissionError):
        continuous.load("alice", {"operation_id": "operation", "nonce": "opaque", **change})


def test_revoked_version_and_disabled_cannot_admit_but_disabled_can_query(ledger):
    path, put = ledger
    operation(put)
    put("settings", "settings", {"enabled": False})
    payload = {"operation_id": "operation", "nonce": "opaque"}
    assert continuous.load("alice", payload)["id"] == "operation"
    with pytest.raises(PermissionError):
        continuous.load("alice", payload, writing=True)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE users SET token_version=2")
    assert continuous.load("alice", payload)["id"] == "operation"
    with pytest.raises(PermissionError):
        continuous.load("alice", payload, writing=True)


def test_native_grant_rechecks_exact_version_project_and_instance(ledger):
    path, put = ledger
    put("work", "work", {"thread_id": "execution", "project": "demo"}, "active")
    operation(
        put,
        "execute",
        thread_id="execution",
        project="demo",
        grant_id="grant",
        grant_version=1,
        instance_id="instance",
    )
    grant = {
        "version": 1,
        "instance_id": "instance",
        "active": {"projects": ["demo"], "operations": ["submit"]},
    }
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO deermate_agent_grants VALUES('alice','grant',?)", (json.dumps(grant),)
        )
    payload = {"operation_id": "operation", "nonce": "opaque"}
    assert continuous.load("alice", payload, writing=True)["id"] == "operation"
    with sqlite3.connect(path) as db:
        db.execute("UPDATE deermate_agent_grants SET data=json_set(data,'$.revoked',1)")
    with pytest.raises(PermissionError):
        continuous.load("alice", payload, writing=True)


def test_canonical_markers_cannot_be_forged_from_ordinary_chat(ledger):
    path, put = ledger
    operation(put)
    message = {
        "additional_kwargs": {
            "deermate_continuous_operation": "operation",
            "deermate_continuous_token": "opaque",
        }
    }
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO runs VALUES('run','alice','router',?,'{}','ordinary')",
            (json.dumps({"input": {"messages": [message]}}),),
        )
    runtime = SimpleNamespace(context={"user_id": "alice", "run_id": "run"})
    with pytest.raises(PermissionError):
        middleware.profile(runtime)
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE runs SET idempotency_key=?",
            (continuous.canonical_key("alice", "router", "operation"),),
        )
    assert middleware.profile(runtime)["id"] == "operation"


async def test_one_call_router_graph_returns_without_waiting_or_second_model(ledger, monkeypatch):
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool

    _, put = ledger
    op = operation(put)
    monkeypatch.setattr(middleware, "profile", lambda runtime: op)
    actions = []

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            assert [t.name for t in tools] == ["secretary_route"]
            return self

    model = Model(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "secretary_route",
                        "id": "route",
                        "args": {"action": "respond", "text": "accepted"},
                    }
                ],
            )
        ]
    )
    monkeypatch.setattr(middleware, "bounded_model", lambda name: model)

    async def command(op, args):
        actions.append(args)
        return '{"operation_id":"stable","status":"pending"}'

    monkeypatch.setattr(middleware, "command", command)

    @tool
    def unsafe_shell() -> str:
        """Forbidden execution tool."""
        raise AssertionError("Router executed shell")

    graph = create_agent(
        model,
        tools=[unsafe_shell, middleware.secretary_route],
        middleware=[middleware.ContinuousMiddleware()],
    )
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "hello"}]},
        context={"user_id": "alice", "run_id": "run"},
    )
    assert len(actions) == 1
    assert result["messages"][-1].type == "tool"
    with pytest.raises(PermissionError):
        middleware.claim_model(op)


@pytest.mark.parametrize(
    "kind,tool_name", [("assessor", "secretary_route"), ("router", "unsafe_shell")]
)
async def test_role_boundary_blocks_adversarial_calls(ledger, monkeypatch, kind, tool_name):
    _, put = ledger
    op = operation(put, kind)
    monkeypatch.setattr(middleware, "profile", lambda runtime: op)
    request = SimpleNamespace(runtime=SimpleNamespace(), tool_call={"name": tool_name})

    async def handler(request):
        raise AssertionError("Forbidden tool handler invoked")

    with pytest.raises(PermissionError):
        await middleware.ContinuousMiddleware().awrap_tool_call(request, handler)


async def test_native_two_rounds_and_lost_ack_query_never_replays(ledger, monkeypatch, tmp_path):
    from deerflow.mcp.tasks import runtime
    from test_chat_sessions import Submitter

    from deermate import session_middleware
    from deermate.chat_sessions import SessionJournal, SessionUnknown

    path, put = ledger
    journal = SessionJournal(tmp_path / "journal.db")
    submitter = Submitter()
    monkeypatch.setattr(session_middleware, "journal", lambda: journal)
    monkeypatch.setattr(runtime, "get_mcp_task_submitter", lambda: submitter)
    monkeypatch.setattr(continuous, "native_profile", lambda owner, server: "coding")
    put("work", "work", {"thread_id": "execution", "project": "demo"}, "active")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO deermate_agent_grants VALUES('alice','grant',?)",
            (
                json.dumps(
                    {
                        "version": 1,
                        "instance_id": "instance",
                        "active": {"projects": ["demo"], "operations": ["submit", "continue"]},
                    }
                ),
            ),
        )
    data = dict(
        thread_id="execution",
        project="demo",
        grant_id="grant",
        grant_version=1,
        instance_id="instance",
        expected_head="",
        server="deermate",
        message="fix",
    )
    operation(put, "execute", **data)

    class Runs:
        async def create_thread(self, **kwargs):
            return kwargs["thread_id"]

    ctx = context()
    ctx.agent_runs = Runs()
    payload = {"operation_id": "operation", "nonce": "opaque"}
    first = await continuous.perform(payload, ctx)
    assert first["known"] and len(submitter.submissions) == 1
    await continuous.query(payload, ctx)
    assert len(submitter.submissions) == 1
    data["expected_head"] = first["tracking_id"]
    operation(put, "followup", **data)
    # A new immutable operation ID is needed for the second native round.
    with sqlite3.connect(path) as db:
        db.execute("UPDATE deermate_work_records SET id='second' WHERE id='operation'")
    submitter.failure = "after"
    payload["operation_id"] = "second"
    with pytest.raises(SessionUnknown):
        await continuous.perform(payload, ctx)
    result = await continuous.query(payload, ctx)
    assert result["known"] and len(submitter.submissions) == 2
    assert len({r["result"]["session_id"] for r in submitter.records}) == 1
    assert submitter.submissions[1].driver_data["submit_tool"] == "continue_task"


async def test_bounded_provider_payload_and_no_sdk_retry(monkeypatch):
    import httpx
    from deerflow.models import factory
    from langchain_openai import ChatOpenAI
    from openai import RateLimitError

    requests = []

    def transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            429,
            json={"error": {"message": "fixture rate limit", "type": "rate_limit_error"}},
            headers={"retry-after": "0"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        model = ChatOpenAI(
            model="fixture",
            api_key="synthetic-only",
            max_tokens=1024,
            max_retries=0,
            use_responses_api=False,
            http_async_client=client,
        )
        monkeypatch.setattr(factory, "create_chat_model", lambda *args, **kwargs: model)
        bounded = middleware.bounded_model("fixture")
        with pytest.raises(RateLimitError):
            await bounded.ainvoke("bounded synthetic request")
    assert len(requests) == 1
    assert requests[0].get("max_completion_tokens", requests[0].get("max_tokens")) == 1024


@pytest.mark.parametrize(
    "extra", [{"max_tokens": 99999}, {"max_completion_tokens": None}, {"max_output_tokens": 0}]
)
def test_provider_body_cannot_override_output_ceiling(monkeypatch, extra):
    from deerflow.models import factory
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model="fixture",
        api_key="synthetic-only",
        max_tokens=1024,
        max_retries=0,
        use_responses_api=False,
        extra_body=extra,
    )
    monkeypatch.setattr(factory, "create_chat_model", lambda *args, **kwargs: model)
    with pytest.raises(PermissionError):
        middleware.bounded_model("fixture")


async def test_rejected_before_send_has_a_durable_read_only_receipt(ledger):
    _, put = ledger
    operation(put)
    put("settings", "settings", {"enabled": False})
    payload = {"operation_id": "operation", "nonce": "opaque"}
    ctx = context()
    ctx.agent_runs = None
    first = await continuous.perform(payload, ctx)
    assert first["known"] and first["status"] == "rejected"
    # Re-enabling cannot replay a rejected operation with the same identity.
    put("settings", "settings", {"enabled": True})
    assert await continuous.query(payload, ctx) == first
    assert await continuous.perform(payload, ctx) == first
