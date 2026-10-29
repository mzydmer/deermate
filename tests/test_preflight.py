import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncssh
import httpx
import pytest
from mcp_helpers import call, mcp_session
from ssh_helpers import ssh_worker as ssh_worker  # noqa: F401 - shared pytest fixture
from ssh_helpers import write_enrollment

from deermate.api import token_file
from deermate.bridge import BridgeError, TaskBridge
from deermate.protocol import CAPABILITIES_LIMIT
from deermate.ssh import RemoteTaskBridge


@pytest.fixture
def token_path(tmp_path):
    token_file(tmp_path / "auth")
    return tmp_path / "auth/api.token"


@pytest.fixture
def capabilities():
    return {
        "protocol_version": 1,
        "instance_id": "a" * 32,
        "adapter": "codex-app-server",
        "operations": ["submit", "status", "events", "cancel", "resume", "input"],
        "remote": False,
    }


async def doctor(config, *, port=None, worker=None):
    args = [sys.executable, "-m", "deermate.cli", "--config", str(config)]
    if port:
        args += ["--port", str(port)]
    if worker:
        args += ["--worker", worker]
    process = await asyncio.create_subprocess_exec(
        *args, "doctor", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await asyncio.wait_for(process.communicate(), timeout=30)
    assert not err, err.decode()
    return process.returncode, json.loads(out)


def assert_blocked(report, code):
    assert report["status"] == "blocked"
    assert report["error"]["code"] == code
    assert report["execution_readiness"] == report["task_outcome"] == "not_checked"
    assert "capabilities" not in report and "identity" not in report


async def test_local_cli_and_mcp_check_never_execute(local_server, tmp_path):
    config, port, worker = local_server
    code, report = await doctor(config, port=port)
    assert code == 0 and report["status"] == "reachable"
    assert report["connection"] == {"type": "loopback"}
    assert report["capabilities"]["instance_id"] == worker.store.instance_id
    assert report["identity"] == {"ssh_host_key": "not_applicable", "worker_instance": "observed"}
    assert datetime.fromisoformat(report["checked_at"]).utcoffset() == timedelta(0)
    async with mcp_session(config, port) as session:
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        check = tools["check_worker_connection"]
        assert check.annotations.readOnlyHint and check.annotations.idempotentHint
        assert check.inputSchema["properties"] == {}
        assert check.inputSchema["additionalProperties"] is False
        assert (await call(session, "check_worker_connection"))["status"] == "reachable"
        for args in [{"host": "arbitrary"}, {"worker_id": "other"}, {"command": "run"}]:
            assert (await session.call_tool("check_worker_connection", args)).isError
        (worker.settings.state_dir / "api.token").write_text("wrong-token" * 5)
        report = await call(session, "check_worker_connection")
        assert_blocked(report, "authentication_rejected")
        assert "wrong-token" not in json.dumps(report)
    assert not worker.store.list_tasks()
    assert not (tmp_path / "native").exists()


async def test_probe_projects_only_known_bounded_fields(token_path, capabilities):
    capabilities["private_extra"] = "secret/path/token"
    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        assert request.headers["authorization"] == "Bearer " + token_path.read_text().strip()
        return httpx.Response(200, json=capabilities)

    bridge = TaskBridge(token_path, transport=httpx.MockTransport(respond))
    try:
        report = await bridge.check_connection()
        assert report["status"] == "reachable"
        assert "private_extra" not in report["capabilities"]
        assert "secret" not in json.dumps(report)
        assert calls == [("GET", "/capabilities")]
    finally:
        await bridge.close()


@pytest.mark.parametrize(
    "change,code",
    [
        ({"protocol_version": 2}, "unsupported_protocol"),
        ({"protocol_version": True}, "invalid_response"),
        ({"protocol_version": "1"}, "invalid_response"),
        ({"adapter": "untrusted-adapter"}, "unsupported_adapter"),
        ({"instance_id": "secret/invalid"}, "invalid_response"),
        ({"remote": True}, "invalid_response"),
        ({"remote": 0}, "invalid_response"),
        ({"operations": ["submit", "status", "status"]}, "invalid_response"),
        ({"operations": ["submit", "status", "shell"]}, "invalid_response"),
        ({"operations": ["submit", "status"]}, "invalid_response"),
    ],
)
async def test_incompatible_or_invalid_capabilities(token_path, capabilities, change, code):
    bridge = TaskBridge(
        token_path,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=capabilities | change)),
    )
    try:
        report = await bridge.check_connection()
        assert_blocked(report, code)
        assert "secret" not in json.dumps(report) and "untrusted-adapter" not in json.dumps(report)
    finally:
        await bridge.close()


@pytest.mark.parametrize("body", [b"[]", b"{}", b"not JSON", b"[" * 4000, b"x" * 32769])
async def test_untrusted_response_is_bounded_and_sanitized(token_path, body):
    bridge = TaskBridge(
        token_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    try:
        report = await bridge.check_connection()
        assert_blocked(report, "invalid_response")
        assert len(json.dumps(report)) < 1000
    finally:
        await bridge.close()


async def test_stream_limit_closes_response_without_draining_untrusted_body(token_path):
    closed, drained = [], []

    class UnboundedResponse(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 32768
            yield b"y"
            drained.append(True)
            yield b"private remainder"

        async def aclose(self):
            closed.append(True)

    bridge = TaskBridge(
        token_path,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=UnboundedResponse())),
    )
    try:
        assert_blocked(await bridge.check_connection(), "invalid_response")
        assert closed and not drained
    finally:
        await bridge.close()


@pytest.mark.parametrize("status", [302, 401, 403, 404, 500])
async def test_http_errors_are_reports_without_echo_or_redirect(token_path, status):
    calls = []

    def respond(request):
        calls.append(request.url)
        return httpx.Response(
            status, text="private upstream error", headers={"Location": "https://untrusted.invalid"}
        )

    bridge = TaskBridge(token_path, transport=httpx.MockTransport(respond))
    try:
        report = await bridge.check_connection()
        assert_blocked(
            report, "authentication_rejected" if status in {401, 403} else "endpoint_rejected"
        )
        assert "private" not in json.dumps(report) and len(calls) == 1
    finally:
        await bridge.close()


async def test_missing_token_never_connects(tmp_path):
    def unexpected(_):
        pytest.fail("No connection is permitted without a valid private token")

    bridge = TaskBridge(tmp_path / "secret", transport=httpx.MockTransport(unexpected))
    try:
        assert_blocked(await bridge.check_connection(), "credential_unavailable")
    finally:
        await bridge.close()


async def test_transport_failure_is_sanitized(token_path):
    def unavailable(_):
        raise httpx.ConnectError("private host/key/path")

    bridge = TaskBridge(token_path, transport=httpx.MockTransport(unavailable))
    try:
        report = await bridge.check_connection()
        assert_blocked(report, "unavailable")
        assert "private" not in json.dumps(report)
    finally:
        await bridge.close()


async def test_overall_deadline_and_caller_cancellation(token_path, monkeypatch):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def hung(_):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    bridge = TaskBridge(token_path, transport=httpx.MockTransport(hung))
    try:
        monkeypatch.setattr("deermate.bridge.CONNECTION_CHECK_TIMEOUT", 0.05)
        assert_blocked(await bridge.check_connection(), "timeout")
        assert cancelled.is_set()
        entered.clear()
        cancelled.clear()
        monkeypatch.setattr("deermate.bridge.CONNECTION_CHECK_TIMEOUT", 15)
        task = asyncio.create_task(bridge.check_connection())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
    finally:
        await bridge.close()


@pytest.mark.parametrize("remote", [False, True])
async def test_invalid_config_cli_returns_sanitized_json(tmp_path, remote):
    config = tmp_path / "private.toml"
    config.write_text('secret = "must-not-be-echoed"\n')
    code, report = await doctor(config, worker="home" if remote else None)
    assert code == 1
    assert_blocked(report, "configuration_invalid")
    assert str(tmp_path) not in json.dumps(report) and "must-not" not in json.dumps(report)


async def test_ssh_cli_mcp_check_only_forwards_enrolled_destination(ssh_worker, tmp_path):
    fixture = ssh_worker
    code, report = await doctor(fixture["config"], worker="home")
    assert code == 0 and report["status"] == "reachable"
    assert report["connection"] == {"type": "ssh", "worker_id": "home"}
    assert report["identity"] == {"ssh_host_key": "verified", "worker_instance": "pinned"}
    async with mcp_session(fixture["config"], worker_id="home") as session:
        assert (await call(session, "check_worker_connection"))["status"] == "reachable"
    assert set(fixture["destinations"]) == {("127.0.0.1", fixture["data"]["worker_port"])}
    assert not fixture["worker"].store.list_tasks()
    assert not (tmp_path / "native").exists()


@pytest.mark.parametrize(
    "failure,code",
    [
        ("host_key", "host_key_rejected"),
        ("client_key", "authentication_rejected"),
        ("token", "authentication_rejected"),
        ("instance", "worker_identity_mismatch"),
        ("disable", "grant_disabled"),
        ("expire", "grant_expired"),
        ("remove", "not_enrolled"),
        ("change", "enrollment_changed"),
        ("missing_trust", "credential_unavailable"),
        ("invalid_key", "credential_invalid"),
        ("offline", "unavailable"),
    ],
)
async def test_ssh_preflight_failure_closes_connection(ssh_worker, failure, code):
    fixture = ssh_worker
    bridge = RemoteTaskBridge(fixture["config"], "home")
    data = fixture["data"]
    if failure == "host_key":
        await asyncio.to_thread(
            Path(data["known_hosts"]).write_text,
            f"[127.0.0.1]:{fixture['server'].get_port()} "
            + asyncssh.generate_private_key("ssh-ed25519").export_public_key().decode(),
        )
    elif failure == "client_key":
        await asyncio.to_thread(
            Path(data["client_key"]).write_bytes,
            asyncssh.generate_private_key("ssh-ed25519").export_private_key(),
        )
    elif failure == "token":
        await asyncio.to_thread(Path(data["token_file"]).write_text, "wrong-token" * 5)
    elif failure == "instance":
        fixture["worker"].store.instance_id = "a" * 32
    elif failure == "disable":
        data["enabled"] = False
    elif failure == "expire":
        data["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    elif failure == "change":
        data["worker_port"] += 1
    elif failure == "missing_trust":
        await asyncio.to_thread(Path(data["known_hosts"]).unlink)
    elif failure == "invalid_key":
        await asyncio.to_thread(Path(data["client_key"]).write_text, "private invalid key")
    elif failure == "offline":
        fixture["server"].close()
        await fixture["server"].wait_closed()
    write_enrollment(fixture["config"], data, worker_id="other" if failure == "remove" else "home")
    try:
        report = await bridge.check_connection()
        assert_blocked(report, code)
        assert str(fixture["config"].parent) not in json.dumps(report)
        assert "wrong-token" not in json.dumps(report)
        assert bridge.transport.connection is None
        assert not fixture["worker"].store.list_tasks()
    finally:
        await bridge.close()


@pytest.mark.parametrize("failure", ["version", "adapter", "invalid", "oversized"])
async def test_ssh_incompatible_protocol_rejected_before_mutation(ssh_worker, monkeypatch, failure):
    bridge = RemoteTaskBridge(ssh_worker["config"], "home")
    exchange = bridge.transport._exchange
    calls = []

    async def altered_capabilities(request, **kwargs):
        # Exercise a real SSH/HTTP connection, then corrupt its application response.
        calls.append((request.method, request.url.path))
        response = await exchange(request, **kwargs)
        if request.url.path == "/capabilities":
            await response.aread()
            data = response.json()
            if failure == "invalid":
                return httpx.Response(200, content=b"secret-invalid-response")
            if failure == "oversized":
                return httpx.Response(200, content=b"x" * (CAPABILITIES_LIMIT + 1))
            data.update({"protocol_version": 2} if failure == "version" else {"adapter": "other"})
            return httpx.Response(200, json=data)
        return response

    monkeypatch.setattr(bridge.transport, "_exchange", altered_capabilities)
    expected = {
        "version": "unsupported_protocol",
        "adapter": "unsupported_adapter",
        "invalid": "invalid_response",
        "oversized": "invalid_response",
    }[failure]
    try:
        assert_blocked(await bridge.check_connection(), expected)
        with pytest.raises(BridgeError) as error:
            await bridge.submit("demo", "fix", "must-not-execute")
        assert error.value.code == expected
        assert all(method == "GET" and path == "/capabilities" for method, path in calls)
        assert not ssh_worker["worker"].store.list_tasks()
    finally:
        await bridge.close()


async def test_revoked_check_preserves_running_work_and_recovers(ssh_worker):
    fixture = ssh_worker
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        task = await bridge.submit("demo", "slow", "stable")
        task_id = task["task_id"].split(":")[1]
        async with asyncio.timeout(10):
            while fixture["worker"].store.get(task_id).status != "running":  # noqa: ASYNC110
                await asyncio.sleep(0.02)
        native_session = fixture["worker"].store.get(task_id).session_id
        fixture["data"]["enabled"] = False
        write_enrollment(fixture["config"], fixture["data"])
        assert_blocked(await bridge.check_connection(), "grant_disabled")
        assert fixture["worker"].store.get(task_id).status == "running"
        fixture["data"].pop("enabled")
        write_enrollment(fixture["config"], fixture["data"])
        assert (await bridge.check_connection())["status"] == "reachable"
        assert fixture["worker"].store.get(task_id).session_id == native_session
        assert len(fixture["worker"].store.list_tasks()) == 1
        await bridge.cancel(task["task_id"])
    finally:
        await bridge.close()
