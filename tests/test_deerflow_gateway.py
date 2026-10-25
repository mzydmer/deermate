"""Opt-in full upstream backend verification, isolated from ordinary tests."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


async def test_real_gateway_sql_restart_and_reconnect(tmp_path):
    checkout = os.environ.get("DEERMATE_DEERFLOW_CHECKOUT")
    gateway_python = os.environ.get("DEERMATE_GATEWAY_PYTHON")
    if not checkout or not gateway_python:
        pytest.skip("Set both upstream checkout and frozen Gateway Python to run this check")
    receipt = tmp_path / "gateway-receipt.json"
    command = [
        sys.executable,
        str(ROOT / "scripts/verify_deerflow_gateway.py"),
        "--checkout",
        checkout,
        "--gateway-python",
        gateway_python,
        "--receipt",
        str(receipt),
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
    } <= {check["name"] for check in data["checks"]}
    assert str(tmp_path) not in receipt.read_text()
