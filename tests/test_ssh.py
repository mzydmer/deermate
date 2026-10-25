import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

import asyncssh
import pytest
from mcp_helpers import call, mcp_session, wait_status
from ssh_helpers import ssh_worker as ssh_worker  # noqa: F401 - shared pytest fixture
from ssh_helpers import write_enrollment

from deermate.bridge import BridgeError
from deermate.ssh import RemoteTaskBridge


async def test_real_ssh_repair_and_evidence(ssh_worker):
    fixture = ssh_worker
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        task = await bridge.submit("demo", "fix", "repair")
        handle = task["task_id"]
        assert handle.startswith(fixture["data"]["expected_instance_id"] + ":")
        async with asyncio.timeout(10):
            while True:
                status = await bridge.status(handle)
                if status["status"] in {"completed", "failed"}:
                    break
                await asyncio.sleep(0.02)
        assert status["status"] == "completed", status
        assert status["result"]["validation"]["exit_code"] == 0
        assert "--worker home diff" in status["result"]["diff_command"]
        assert set(fixture["destinations"]) == {("127.0.0.1", fixture["data"]["worker_port"])}
        assert len(fixture["worker"].store.list_tasks()) == 1
    finally:
        await bridge.close()


async def test_real_remote_mcp_reconnect_and_cancel(ssh_worker):
    fixture = ssh_worker
    async with mcp_session(fixture["config"], worker_id="home") as first:
        task = await call(
            first, "submit_task", project_id="demo", prompt="slow", idempotency_key="one"
        )
        handle = task["task_id"]
        await wait_status(first, handle, {"running"})
    native = handle.split(":")[1]
    session_id = fixture["worker"].store.get(native).session_id
    assert fixture["worker"].store.get(native).status == "running"
    async with mcp_session(fixture["config"], worker_id="home") as second:
        duplicate = await call(
            second, "submit_task", project_id="demo", prompt="slow", idempotency_key="one"
        )
        assert duplicate["task_id"] == handle
        cancelled = await call(second, "cancel_task", task_id=handle)
        assert cancelled["status"] == "cancelled"
        assert (await call(second, "cancel_task", task_id=handle))["status"] == "cancelled"
        assert fixture["worker"].store.get(native).session_id == session_id
        bad = await second.call_tool("get_task_status", {"task_id": "a" * 32 + ":" + native})
        assert bad.isError
    assert len(fixture["worker"].store.list_tasks()) == 1


async def test_remote_cli_can_inspect_capabilities_and_evidence(ssh_worker):
    fixture = ssh_worker

    async def cli(*args):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "deermate.cli",
            "--config",
            str(fixture["config"]),
            "--worker",
            "home",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        assert process.returncode == 0, err.decode()
        return out.decode()

    capabilities = json.loads(await cli("capabilities"))
    assert capabilities["instance_id"] == fixture["worker"].store.instance_id
    assert capabilities["connection"] == {"type": "ssh", "worker_id": "home"}
    task = json.loads(await cli("submit", "--project", "demo", "--key", "cli", "--prompt", "fix"))
    task_id = task["task_id"]
    async with asyncio.timeout(10):
        while fixture["worker"].store.get(task_id).status not in {"completed", "failed"}:  # noqa: ASYNC110
            await asyncio.sleep(0.02)
    assert json.loads(await cli("status", task_id))["status"] == "completed"
    assert "return a + b" in await cli("diff", task_id)
    assert json.loads(await cli("events", task_id))["events"]


async def test_instance_bound_handle_rejected_before_network(ssh_worker):
    bridge = RemoteTaskBridge(ssh_worker["config"], "home")
    try:
        with pytest.raises(BridgeError, match="different Worker instance"):
            await bridge.status("a" * 32 + ":" + "b" * 32)
        assert not ssh_worker["connections"]
    finally:
        await bridge.close()


@pytest.mark.parametrize(
    "failure", ["host_key", "missing_trust", "client_key", "token", "instance"]
)
async def test_identity_and_credentials_fail_before_mutation(ssh_worker, failure, tmp_path):
    fixture = ssh_worker
    data = fixture["data"]
    if failure == "host_key":
        wrong = asyncssh.generate_private_key("ssh-ed25519")
        tmp_path.joinpath("known_hosts").write_text(
            f"[127.0.0.1]:{fixture['server'].get_port()} " + wrong.export_public_key().decode()
        )
    elif failure == "missing_trust":
        tmp_path.joinpath("known_hosts").unlink()
    elif failure == "client_key":
        tmp_path.joinpath("client.key").write_bytes(
            asyncssh.generate_private_key("ssh-ed25519").export_private_key()
        )
    elif failure == "token":
        token = tmp_path / "wrong.token"
        token.write_text("wrong" * 10)
        token.chmod(0o600)
        data["token_file"] = str(token)
    else:
        data["expected_instance_id"] = "a" * 32
    write_enrollment(fixture["config"], data)
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        with pytest.raises(BridgeError) as error:
            await bridge.submit("demo", "fix", "one")
        assert "wrongwrong" not in str(error.value) and str(tmp_path) not in str(error.value)
        assert not fixture["worker"].store.list_tasks()
        assert bridge.transport.connection is None
    finally:
        await bridge.close()


@pytest.mark.parametrize("action", ["disable", "expire", "remove", "change"])
async def test_revocation_and_config_changes_do_not_claim_stopped(ssh_worker, action):
    fixture = ssh_worker
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        task = await bridge.submit("demo", "slow", "one")
        native = task["task_id"].split(":")[1]
        async with asyncio.timeout(5):
            while fixture["worker"].store.get(native).status != "running":  # noqa: ASYNC110
                await asyncio.sleep(0.02)
        if action == "disable":
            fixture["data"]["enabled"] = False
        elif action == "expire":
            fixture["data"]["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        elif action == "change":
            fixture["data"]["worker_port"] += 1
        write_enrollment(
            fixture["config"], fixture["data"], worker_id="other" if action == "remove" else "home"
        )
        with pytest.raises(BridgeError):
            await bridge.cancel(task["task_id"])
        assert fixture["worker"].store.get(native).status == "running"
        assert bridge.transport.connection is None
    finally:
        await bridge.close()


async def test_ssh_disconnect_reconnect_does_not_restart_native_session(ssh_worker):
    fixture = ssh_worker
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        task = await bridge.submit("demo", "slow", "one")
        native = task["task_id"].split(":")[1]
        async with asyncio.timeout(5):
            while fixture["worker"].store.get(native).status != "running":  # noqa: ASYNC110
                await asyncio.sleep(0.02)
        session = fixture["worker"].store.get(native).session_id
        fixture["connections"][-1].abort()
        await fixture["connections"][-1].wait_closed()
        # The next call may observe the disconnect before connection_lost runs;
        # retry the read explicitly, never a hidden mutation retry.
        try:
            await bridge.status(task["task_id"])
        except BridgeError:
            pass
        status = await bridge.status(task["task_id"])
        assert status["status"] == "running"
        assert (await bridge.submit("demo", "slow", "one"))["task_id"] == task["task_id"]
        assert len(fixture["worker"].store.list_tasks()) == 1
        assert fixture["worker"].store.get(native).session_id == session
        await bridge.cancel(task["task_id"])
    finally:
        await bridge.close()


async def test_lost_submission_ack_is_not_automatically_replayed(ssh_worker, monkeypatch):
    fixture = ssh_worker
    original = fixture["worker"].store.submit
    admissions = []

    def lose_ack(*args, **kwargs):
        result = original(*args, **kwargs)
        admissions.append(result[0].task_id)
        for connection in fixture["connections"]:
            connection.abort()
        return result

    monkeypatch.setattr(fixture["worker"].store, "submit", lose_ack)
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        with pytest.raises(BridgeError, match="unknown"):
            await bridge.submit("demo", "fix", "stable")
        assert len(admissions) == 1
        monkeypatch.setattr(fixture["worker"].store, "submit", original)
        recovered = await bridge.submit("demo", "fix", "stable")
        assert recovered["task_id"].endswith(":" + admissions[0])
        assert len(fixture["worker"].store.list_tasks()) == 1
    finally:
        await bridge.close()


async def test_expiring_connection_closes_idle_tunnel_and_reauthenticates(ssh_worker):
    fixture = ssh_worker
    fixture["data"]["max_connection_age_seconds"] = 5
    write_enrollment(fixture["config"], fixture["data"])
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        await bridge.status(bridge.instance_id + ":" + "a" * 32)
        assert bridge.transport.connection is not None
        fixture["allowed"].clear()  # Server revokes new authentication, not existing SSH sessions.
        await asyncio.sleep(5.1)
        assert bridge.transport.connection is None
        with pytest.raises(BridgeError, match="client key was rejected"):
            await bridge.submit("demo", "fix", "one")
        assert not fixture["worker"].store.list_tasks()
    finally:
        await bridge.close()


async def test_key_rotation_and_encrypted_key_reference(ssh_worker, monkeypatch, tmp_path):
    fixture = ssh_worker
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        await bridge.status(bridge.instance_id + ":" + "a" * 32)
        count = len(fixture["connections"])
        replacement = asyncssh.generate_private_key("ssh-ed25519")
        tmp_path.joinpath("client.key").write_bytes(replacement.export_private_key())
        fixture["allowed"].clear()
        fixture["allowed"].add(replacement.convert_to_public())
        await bridge.status(bridge.instance_id + ":" + "a" * 32)
        assert len(fixture["connections"]) > count
    finally:
        await bridge.close()
    fixture["data"]["passphrase_env"] = "DEERMATE_TEST_SSH_PASSPHRASE"
    write_enrollment(fixture["config"], fixture["data"])
    tmp_path.joinpath("client.key").write_bytes(
        replacement.export_private_key(passphrase="fixture-passphrase")
    )
    encrypted = RemoteTaskBridge(fixture["config"], "home")
    try:
        with pytest.raises(BridgeError, match="passphrase is unavailable"):
            await encrypted.status(encrypted.instance_id + ":" + "a" * 32)
        monkeypatch.setenv("DEERMATE_TEST_SSH_PASSPHRASE", "fixture-passphrase")
        assert (await encrypted.status(encrypted.instance_id + ":" + "a" * 32))[
            "error_code"
        ] == "task_not_found"
    finally:
        await encrypted.close()


@pytest.mark.parametrize("file", ["client_key", "known_hosts", "token_file"])
async def test_unsafe_files_fail_closed(ssh_worker, file, tmp_path):
    fixture = ssh_worker
    from pathlib import Path

    path = Path(fixture["data"][file])
    await asyncio.to_thread(path.chmod, 0o666)
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        with pytest.raises(BridgeError):
            await bridge.submit("demo", "fix", "one")
        assert not fixture["connections"]
        assert not fixture["worker"].store.list_tasks()
    finally:
        await bridge.close()
        await asyncio.to_thread(path.chmod, 0o600)


async def test_credential_symlink_does_not_open(ssh_worker, tmp_path):
    fixture = ssh_worker
    link = tmp_path / "symlink.key"
    link.symlink_to(fixture["data"]["client_key"])
    fixture["data"]["client_key"] = str(link)
    write_enrollment(fixture["config"], fixture["data"])
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        with pytest.raises(BridgeError, match="unavailable"):
            await bridge.submit("demo", "fix", "one")
        assert not fixture["connections"]
    finally:
        await bridge.close()


async def test_instance_rechecked_and_server_denies_other_channels(ssh_worker, monkeypatch):
    fixture = ssh_worker
    bridge = RemoteTaskBridge(fixture["config"], "home")
    try:
        await bridge.status(bridge.instance_id + ":" + "a" * 32)
        connection = bridge.transport.connection
        with pytest.raises(asyncssh.ChannelOpenError):
            await connection.create_process("denied-by-test-server")
        with pytest.raises(asyncssh.ChannelOpenError):
            await connection.open_connection("127.0.0.1", fixture["data"]["worker_port"] + 1)
        monkeypatch.setattr(fixture["worker"].store, "instance_id", "a" * 32)
        with pytest.raises(BridgeError, match="instance identity"):
            await bridge.submit("demo", "fix", "one")
        assert not fixture["worker"].store.list_tasks()
    finally:
        await bridge.close()
