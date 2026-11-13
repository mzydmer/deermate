"""Actual SDK spans and Worker protocol, with synthetic content and no model calls."""

import asyncio
import sqlite3

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

from deermate import telemetry
from deermate.api import create_app
from deermate.models import SubmitTask
from deermate.store import Store


@pytest.fixture
def traced(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_provider", provider)
    yield exporter
    provider.shutdown()


def test_trace_metadata_is_allowlisted_and_content_free(traced):
    secret = "SYNTHETIC_PRIVATE_DO_NOT_EXPORT"
    with telemetry.span("test.root", refs={"operation_id": "op-1", "password": secret}):
        value = telemetry.metadata()
        assert telemetry.carrier(value)["traceparent"]
        value["baggage"] = secret
        value["refs"]["password"] = secret
        with pytest.raises(ValueError):
            with telemetry.span("test.child", parent=value, attributes={"prompt": secret}):
                raise ValueError(secret)
    spans = traced.get_finished_spans()
    assert len(spans) == 2
    child, root = spans
    assert child.context.trace_id == root.context.trace_id
    assert child.parent.span_id == root.context.span_id
    assert child.attributes["error.type"] == "ValueError"
    assert child.status.status_code.name == "ERROR"
    assert not child.events
    assert secret not in "".join(s.to_json() for s in spans)
    assert "baggage" not in telemetry.headers(value)


@pytest.mark.parametrize(
    "parent",
    [
        None,
        {},
        {"traceparent": "bad"},
        {"traceparent": "00-" + "0" * 32 + "-" + "a" * 16 + "-01"},
        {"traceparent": ["a"]},
    ],
)
def test_invalid_carriers_are_ignored(parent):
    assert telemetry.carrier(parent) == {}


def test_task_binding_is_atomic_first_write_and_outside_fingerprint(settings, traced):
    store = Store(settings.state_dir / "trace-test.db")
    request = SubmitTask(project_id="demo", prompt="SYNTHETIC_PRIVATE", idempotency_key="same")
    with telemetry.span("submit.first", refs={"operation_id": "original"}):
        first, created = store.submit(request)
        original = telemetry.load_binding(store.db, first.task_id)
    assert created and original["refs"]["operation_id"] == "original"
    with telemetry.span("submit.retry", refs={"operation_id": "replacement"}):
        duplicate, created = store.submit(request)
    assert not created and duplicate.task_id == first.task_id
    assert telemetry.load_binding(store.db, first.task_id) == original
    assert "traceparent" not in first.model_dump_json()
    store.close()
    restored = Store(settings.state_dir / "trace-test.db")
    assert telemetry.load_binding(restored.db, first.task_id) == original
    restored.close()


def test_recovery_creates_linked_trace_instead_of_reusing_span(traced):
    with telemetry.span("original"):
        previous = telemetry.metadata()
    with telemetry.span("recovery", parent=previous, recovery=True):
        pass
    original, recovered = traced.get_finished_spans()
    assert recovered.context.trace_id != original.context.trace_id
    assert len(recovered.links) == 1
    assert recovered.links[0].context.trace_id == original.context.trace_id


@pytest.mark.asyncio
async def test_worker_two_turns_same_native_and_separate_validation(settings, traced):
    app = create_app(settings, token="t" * 48)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
            headers={"Authorization": "Bearer " + "t" * 48},
        ) as client:

            async def complete(task):
                async with asyncio.timeout(10):
                    while True:
                        result = (await client.get("/tasks/" + task["task_id"])).json()
                        if result["status"] in {"completed", "failed", "needs_review"}:
                            return result
                        await asyncio.sleep(0.02)

            with telemetry.span(
                "round.one", refs={"operation_id": "op-one", "conversation_id": "topic-one"}
            ):
                first = await client.post(
                    "/tasks",
                    json={
                        "project_id": "demo",
                        "prompt": "SYNTHETIC_PRIVATE_ONE trace-tools",
                        "idempotency_key": "round-one",
                    },
                    headers=telemetry.headers(),
                )
                assert first.status_code == 201
            one = await complete(first.json())
            with telemetry.span(
                "round.two", refs={"operation_id": "op-two", "conversation_id": "topic-one"}
            ):
                second = await client.post(
                    "/tasks/" + one["task_id"] + "/continue",
                    json={
                        "message": "SYNTHETIC_PRIVATE_TWO trace-tools",
                        "idempotency_key": "round-two",
                    },
                    headers=telemetry.headers(),
                )
                assert second.status_code == 201
            two = await complete(second.json())
            assert one["status"] == two["status"] == "completed"
            assert one["session_id"] == two["session_id"]
            assert one["turn_id"] != two["turn_id"]
            assert (
                one["result"]["validation_status"] == two["result"]["validation_status"] == "passed"
            )
    spans = traced.get_finished_spans()
    executions = [s for s in spans if s.name == "worker.execute"]
    validations = [s for s in spans if s.name == "worker.validation"]
    tools = [s for s in spans if s.name == "codex.tool"]
    assert len(tools) == len(executions) == len(validations) == 2
    assert all(s.attributes["deermate.item_type"] == "fileChange" for s in tools)
    assert all(
        s.parent.span_id in {t.context.span_id for t in spans if t.name == "codex.turn"}
        for s in tools
    )
    assert {s.attributes["deermate.operation_id"] for s in executions} == {"op-one", "op-two"}
    assert len({s.context.trace_id for s in executions}) == 2
    assert len({s.attributes["deermate.native_session_id"] for s in executions}) == 1
    assert all(
        "SYNTHETIC_PRIVATE" not in s.to_json() and "PRIVATE_TOOL_DIFF" not in s.to_json()
        for s in spans
    )


def test_binding_failure_does_not_change_work_admission(settings, traced):
    store = Store(settings.state_dir / "missing-trace-table.db")
    store.db.execute("DROP TABLE deermate_task_trace")
    with telemetry.span("still-admit"):
        task, created = store.submit(
            SubmitTask(project_id="demo", prompt="fixture", idempotency_key="once")
        )
    assert created and task.status == "queued"
    assert telemetry.load_binding(store.db, task.task_id) == {}
    store.close()


def test_disable_and_bad_exporter_do_not_load_network(monkeypatch):
    monkeypatch.setattr(telemetry, "_provider", None)
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setenv("DEERMATE_TELEMETRY_ENABLED", "false")
    telemetry.configure()
    with telemetry.span("disabled"):
        assert telemetry.metadata() == {}
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setenv("DEERMATE_TELEMETRY_ENABLED", "true")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://untrusted.example.invalid/traces"
    )
    telemetry.configure()
    assert telemetry._provider is None


def test_trace_schema_is_separate_from_task_data(settings):
    store = Store(settings.state_dir / "compat.db")
    assert store.db.execute("SELECT count(*) FROM deermate_task_trace").fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("INSERT INTO deermate_task_trace VALUES(NULL,NULL)")
    store.close()


def test_resource_attributes_are_allowlisted(monkeypatch):
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "service.version=local-test,private=SECRET,deployment.environment.name=test,service.namespace=deermate",
    )
    assert telemetry.resource_attributes("worker") == {
        "service.name": "worker",
        "service.version": "local-test",
        "service.namespace": "deermate",
        "deployment.environment.name": "test",
    }


def test_exporter_does_not_inherit_ambient_proxy():
    session = telemetry.exporter_session()
    assert session.trust_env is False
    session.close()


@pytest.mark.parametrize("value", [None, [], "not-a-map", {"traceparent": []}])
def test_invalid_metadata_is_ignored(value):
    assert telemetry.from_headers(value) == {}


def test_canonical_parent_refs_override_ambient_refs(traced):
    with telemetry.span("canonical", refs={"operation_id": "canonical-operation"}):
        parent = telemetry.metadata()
    with telemetry.span("ambient", refs={"operation_id": "ambient-operation"}):
        with telemetry.span("restored", parent=parent):
            assert telemetry.metadata()["refs"]["operation_id"] == "canonical-operation"
    child = next(s for s in traced.get_finished_spans() if s.name == "restored")
    assert f"{child.context.trace_id:032x}" == parent["traceparent"][3:35]


@pytest.mark.asyncio
async def test_completion_only_native_event_does_not_invent_tool_start(settings, traced):
    from deermate.codex import CodexAdapter

    store = Store(settings.state_dir / "event-only.db")
    task, _ = store.submit(SubmitTask(project_id="demo", prompt="fixture", idempotency_key="event"))

    async def record(kind, payload):
        pass

    adapter = CodexAdapter(settings, task, record)
    adapter.session_id, adapter.turn_id = "session-one", "turn-one"
    for message in [
        {"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"last": []}}},
        {
            "method": "item/completed",
            "params": {
                "item": {"type": "fileChange", "id": "completion-only", "diff": "PRIVATE_TOOL_DIFF"}
            },
        },
        {"method": "turn/completed", "params": {"turn": {"id": "turn-one", "status": "completed"}}},
    ]:
        await adapter.rpc.events.put(message)
    try:
        await adapter.run()
    finally:
        await adapter.close()
        store.close()
    spans = traced.get_finished_spans()
    assert [s.name for s in spans] == ["codex.turn"]
    assert "PRIVATE_TOOL_DIFF" not in spans[0].to_json()
