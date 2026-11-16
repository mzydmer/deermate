"""Completion contracts; a completed Worker alone never closes a sample."""

from copy import deepcopy

import pytest

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
