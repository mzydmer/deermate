"""Connection checks must never enroll a URL, execute a tool or leak credentials."""

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

from deermate import tooling


def context(**changes):
    return SimpleNamespace(principal=SimpleNamespace(
        user_id="current-owner", is_admin=True, is_internal=False, **changes
    ))


@pytest.mark.parametrize("action", [tooling.inventory, tooling.discover])
@pytest.mark.parametrize("principal", [
    SimpleNamespace(user_id="u", is_admin=False, is_internal=False),
    SimpleNamespace(user_id="u", is_admin=True, is_internal=True),
    SimpleNamespace(user_id="", is_admin=True, is_internal=False),
])
async def test_deny_before_loading_or_contacting_runtime(action, principal):
    with pytest.raises(PermissionError):
        await action({}, SimpleNamespace(principal=principal))


@pytest.fixture
def discovery(monkeypatch):
    snapshot = SimpleNamespace(mcp_servers={"saved": SimpleNamespace(enabled=True)})
    snapshots, calls = [], []

    async def load(scope, owner):
        snapshots.append((scope, owner))
        return snapshot

    async def discover(config, **kwargs):
        calls.append((config, kwargs))
        return {"saved": SimpleNamespace(tools=(SimpleNamespace(name="read_data"),))}

    module = ModuleType("deerflow.mcp.tools")
    module.get_mcp_tools_by_server = discover
    monkeypatch.setitem(sys.modules, "deerflow.mcp.tools", module)
    monkeypatch.setattr(tooling, "_snapshot", load)
    return snapshot, snapshots, calls, module


@pytest.mark.parametrize("scope", ["platform", "personal"])
async def test_discovery_binds_snapshot_and_actual_owner(discovery, scope):
    config, snapshots, calls, _ = discovery
    result = await tooling.discover({
        "scope": scope, "name": "saved", "owner": "victim", "url": "http://attacker"
    }, context())
    assert result == {"status": "discovered", "tools": ["read_data"], "total": 1}
    assert snapshots == [(scope, "current-owner")]
    assert calls == [(config, {
        "server_names": ["saved"],
        "personal_user_id": "current-owner" if scope == "personal" else None,
    })]


async def test_unknown_disabled_and_invalid_scope_never_contact(discovery):
    config, _, calls, _ = discovery
    result = await tooling.discover({"scope": "platform", "name": "http://new-server"}, context())
    assert result["status"] == "not_configured"
    config.mcp_servers["saved"].enabled = False
    assert (await tooling.discover({"scope": "platform", "name": "saved"}, context()))[
        "status"
    ] == "disabled"
    with pytest.raises(ValueError):
        await tooling.discover({"scope": "other", "name": "saved"}, context())
    assert not calls


@pytest.mark.parametrize("outcome", ["missing", "empty", "timeout", "secret"])
async def test_failure_is_distinct_from_zero_tools_and_never_leaks(discovery, outcome):
    _, _, _, module = discovery

    async def discover(*args, **kwargs):
        if outcome == "timeout":
            raise TimeoutError("private-token")
        if outcome == "secret":
            raise RuntimeError("https://user:private-token@example.com")
        return {} if outcome == "missing" else {"saved": SimpleNamespace(tools=())}

    module.get_mcp_tools_by_server = discover
    result = await tooling.discover({"scope": "platform", "name": "saved"}, context())
    assert "private-token" not in str(result)
    assert result["status"] == {
        "missing": "unavailable", "empty": "discovered", "timeout": "timeout",
        "secret": "unavailable",
    }[outcome]
    if outcome == "empty":
        assert result["total"] == 0


async def test_one_inflight_check_per_admin_and_cancellation_releases(discovery):
    _, _, _, module = discovery
    admitted = asyncio.Event()

    async def discover(*args, **kwargs):
        admitted.set()
        await asyncio.Future()

    module.get_mcp_tools_by_server = discover
    payload = {"scope": "platform", "name": "saved"}
    task = asyncio.create_task(tooling.discover(payload, context()))
    await admitted.wait()
    assert (await tooling.discover(payload, context()))["status"] == "busy"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "current-owner" not in tooling._discovering
