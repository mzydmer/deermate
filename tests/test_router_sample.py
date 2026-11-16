"""Completion contracts; a completed Worker alone never closes a sample."""

import json
import time
from copy import deepcopy
from threading import Event, Lock
from types import SimpleNamespace

import httpx
import pytest

from scripts import run_router_sample as sample
from scripts.run_router_sample import barrier_state


@pytest.fixture
def settled():
    operation = {
        "id": "native-op",
        "kind": "operation",
        "state": "settled",
        "data": {"kind": "execute"},
    }
    evidence = {
        "worker_tasks": [{"status": "completed"}],
        "mcp_tasks": [
            {
                "id": "original",
                "user_id": "owner",
                "thread_id": "work-thread",
                "notification_status": "delivered",
                "event_version": 1,
                "notified_version": 1,
            }
        ],
        "go_records": [operation],
        "model_events": [],
        "runs": [{"status": "success", "user_id": "owner"}],
    }
    public = {
        "thread_id": "work-thread",
        "items": [
            {"task_id": "original", "status": "completed", "notification_status": "delivered"}
        ],
    }
    view = {"items": [{"state": "settled"}]}
    work = {"data": {"stage": "completed"}}
    return evidence, public, view, work


def test_worker_complete_does_not_hide_unsettled_tracking_or_notifications(settled):
    evidence, public, view, work = deepcopy(settled)
    public["items"][0]["status"] = "working"
    public["items"][0]["notification_status"] = "dispatched"
    evidence["mcp_tasks"][0]["notified_version"] = 0
    evidence["runs"][0]["status"] = "running"
    reasons = barrier_state(evidence, public, view, work, "B", "owner")
    assert {
        "owned_public_mcp_not_terminal",
        "mcp_owner_or_notification_unsettled",
        "public_notification_unsettled",
        "related_runs_unsettled",
    } <= set(reasons)


def test_original_go_operation_and_owner_are_required(settled):
    evidence, public, view, work = deepcopy(settled)
    evidence["go_records"][0]["state"] = "uncertain"
    evidence["mcp_tasks"][0]["user_id"] = "other"
    public["items"][0]["task_id"] = "replacement"
    reasons = barrier_state(evidence, public, view, work, "C", "owner")
    assert {
        "go_operations_unsettled",
        "mcp_owner_or_notification_unsettled",
        "public_mcp_identity_not_reconciled",
    } <= set(reasons)


def test_all_layers_settle_on_original_identity(settled):
    assert barrier_state(*settled, "B", "owner") == []


def test_s1_offsets_are_independent_and_failed_attempts_are_retained(monkeypatch, tmp_path):
    cfg = {"logical_operation_id": "s1-1101"}
    bound_four = Event()
    arrivals = {}
    mutex = Lock()

    def handle(request):
        body = json.loads(request.content)
        kind = "foreground" if request.url.path.endswith("router/messages") else body["id"] % 100
        with mutex:
            arrivals[kind] = time.monotonic_ns()
        if kind == 4:
            bound_four.set()
        if kind == "foreground":
            assert bound_four.wait(2), "later input was gated on the foreground HTTP response"
            return httpx.Response(200, json={"id": "front-inbox"})
        if kind == 99:
            assert request.headers["X-Expected-User-Id"] == "outside"
            assert "outside-cookie" in request.headers["Cookie"]
            return httpx.Response(403, json={"detail": {"code": "owner_bound"}})
        if kind == 1:
            return httpx.Response(503, json={"detail": {"code": "fixture_failure"}})
        return httpx.Response(200, json={"event": {"id": "event-" + str(kind)}})

    actual_client = httpx.Client
    transport = httpx.MockTransport(handle)

    def client_factory(**kwargs):
        return actual_client(**kwargs, transport=transport)

    monkeypatch.setattr(sample.httpx, "Client", client_factory)
    main = SimpleNamespace(
        base_url="http://localhost:22045",
        cookies={"access_token": "owner-cookie"},
        headers={"X-Expected-User-Id": "owner"},
    )
    outside = {
        "user_id": "outside",
        "headers": {"X-Expected-User-Id": "outside"},
        "cookies": {"access_token": "outside-cookie"},
    }
    result = {"scheduled_deliveries": sample.s1_plan(cfg, 1101)}

    def api(method, path):
        return {"items": [{"id": "front-inbox", "data": {"reply": "EVAL_VISIBLE s1-1101"}}]}

    with pytest.raises(RuntimeError, match="all attempts are retained"):
        sample.run_s1(
            main,
            api,
            cfg,
            1101,
            time.monotonic_ns(),
            time.monotonic() + 5,
            tmp_path,
            result,
            outside,
        )
    rows = result["scheduled_deliveries"]
    assert len(rows) == len(arrivals) == 9
    assert len((tmp_path / "schedule.jsonl").read_text().splitlines()) == 9
    assert all(v["sent_runner_ns"] and v["completed_runner_ns"] for v in rows)
    failed = next(v for v in rows if v["kind"] == "bound" and v["index"] == 1)
    assert failed["response_status"] == 503 and failed["error_kind"] == "HTTPStatusError"
    assert failed["attempt_status"] == "failed"
    assert next(v for v in rows if v["kind"] == "wrong_owner")["actor_user_id"] == "outside"


def test_s1_unstarted_slots_remain_explicit_after_deadline(monkeypatch, tmp_path):
    cfg = {"logical_operation_id": "s1-1101"}
    actual_client = httpx.Client
    monkeypatch.setattr(
        sample.httpx,
        "Client",
        lambda **kwargs: actual_client(
            **kwargs,
            transport=httpx.MockTransport(lambda _: pytest.fail("unsent slot made HTTP request")),
        ),
    )
    main = SimpleNamespace(
        base_url="http://localhost:22045", cookies={}, headers={"X-Expected-User-Id": "owner"}
    )
    outside = {"user_id": "outside", "headers": {}, "cookies": {}}
    result = {"scheduled_deliveries": sample.s1_plan(cfg, 1101)}
    with pytest.raises((TimeoutError, RuntimeError)):
        sample.run_s1(
            main,
            lambda *_: None,
            cfg,
            1101,
            time.monotonic_ns() - 2_000_000_000,
            time.monotonic() - 1,
            tmp_path,
            result,
            outside,
        )
    rows = result["scheduled_deliveries"]
    assert len(rows) == 9 and len((tmp_path / "schedule.jsonl").read_text().splitlines()) == 9
    assert all(v["attempt_status"] == "not_started_deadline" for v in rows)
    assert all(v["sent_runner_ns"] is None and v["response_status"] is None for v in rows)


def test_s2_duplicate_is_independent_and_uses_exact_original_owner_input(monkeypatch, tmp_path):
    cfg = {"logical_operation_id": "s2-1101"}
    duplicate_sent = Event()
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if body["operation_id"] == "front-s2-1101":
            assert duplicate_sent.wait(2), "duplicate was gated on foreground HTTP response"
            return httpx.Response(200, json={"id": "front-inbox"})
        duplicate_sent.set()
        return httpx.Response(200, json={"id": "original-inbox"})

    actual_client = httpx.Client
    monkeypatch.setattr(
        sample.httpx,
        "Client",
        lambda **kwargs: actual_client(**kwargs, transport=httpx.MockTransport(handle)),
    )
    main = SimpleNamespace(
        base_url="http://localhost:22045", cookies={}, headers={"X-Expected-User-Id": "owner"}
    )
    result = {"scheduled_deliveries": sample.s2_plan(cfg)}
    sample.run_scheduled(
        main,
        lambda *_: {"items": [{"id": "front-inbox", "data": {"reply": "EVAL_VISIBLE s2-1101"}}]},
        cfg,
        time.monotonic_ns(),
        time.monotonic() + 5,
        tmp_path,
        result,
    )
    assert requests == [
        (
            "/api/me/router/messages",
            {"operation_id": "front-s2-1101", "text": "EVAL_FRONT s2-1101"},
        ),
        (
            "/api/me/router/messages",
            {"operation_id": "start-s2-1101", "text": "EVAL_START s2-1101"},
        ),
    ]
    assert len((tmp_path / "schedule.jsonl").read_text().splitlines()) == 2
    assert all(v["attempt_status"] == "responded" for v in result["scheduled_deliveries"])


@pytest.mark.parametrize("kind", ["barrier_not_reached", "upstream_not_success", "observer_error"])
def test_s2_failed_injection_never_counts_as_recovery(kind):
    verdict = sample.s2_contract({"fault_events": [{"kind": kind}]})
    assert not verdict["passed"]
    assert not verdict["conditions"]["exactly_one_actual_durable_barrier"]
    assert not verdict["conditions"]["exactly_one_actual_ack_drop"]
    assert not verdict["conditions"]["no_injection_errors"]
