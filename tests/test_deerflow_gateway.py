"""Opt-in full upstream backend verification, isolated from ordinary tests."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("transport", ["local", "ssh"])
async def test_real_gateway_sql_restart_and_reconnect(tmp_path, transport):
    checkout = os.environ.get("DEERMATE_DEERFLOW_CHECKOUT")
    gateway_python = os.environ.get("DEERMATE_GATEWAY_PYTHON")
    if not checkout or not gateway_python:
        pytest.skip("Set both upstream checkout and frozen Gateway Python to run this check")
    receipt = tmp_path / "gateway-receipt.json"
    replay = tmp_path / "gateway.html"
    command = [
        sys.executable,
        str(ROOT / "scripts/verify_deerflow_gateway.py"),
        "--checkout",
        checkout,
        "--gateway-python",
        gateway_python,
        "--receipt",
        str(receipt),
        "--transport",
        transport,
        "--replay",
        str(replay),
        "--work-dir",
        str(tmp_path / "work"),
    ]
    process = await asyncio.create_subprocess_exec(*command, cwd=ROOT)
    try:
        code = await asyncio.wait_for(process.wait(), timeout=420)
    except BaseException:
        process.terminate()
        await process.wait()
        raise
    assert code == 0
    data = json.loads(receipt.read_text())
    assert data["passed"] and data["configured_cloud_models"] == 0
    assert data["transport"] == transport
    assert "-    return a - b" in data["demo_artifacts"]["patch_excerpt"]
    assert "+    return a + b" in data["demo_artifacts"]["patch_excerpt"]
    assert all(check["passed"] for check in data["checks"])
    assert {
        "gateway_process_restart_preserves_identity",
        "http_cancel_confirmed_in_sql_and_worker",
        "background_validation_completed",
        "background_validation_failed",
        "outage_is_retryable_not_terminal",
        "reconnect_requires_explicit_recovery",
        "no_replayed_sessions_or_turns",
        "pinned_upstream_unchanged",
        "read_only_worker_preflight_through_gateway",
        "three_rounds_one_native_session_and_workspace",
        "continuation_reconcile_and_chat_scope",
    } <= {check["name"] for check in data["checks"]}
    if transport == "ssh":
        assert {
            "ssh_instance_bound_path",
            "ssh_outage_preserves_running_worker",
            "ssh_reconnect_preserves_identity",
            "ssh_revocation_does_not_claim_cancelled",
            "ssh_grant_restore_completes_requested_cancel",
            "ssh_fixture_enforced_forwarding",
        } <= {check["name"] for check in data["checks"]}
    assert str(tmp_path) not in receipt.read_text()
    assert str(tmp_path) not in replay.read_text()
    assert data["verifier_sha256"] in replay.read_text()
