"""Real SSH protocol fixture with generated keys; never uses the host sshd."""

import json
from datetime import UTC, datetime, timedelta

import asyncssh
import pytest


def write_enrollment(path, data, *, worker_id="home"):
    path.write_text(
        f"[workers.{worker_id}]\n"
        + "\n".join(
            f"{key} = {json.dumps(value)}" for key, value in data.items() if value is not None
        )
        + "\n"
    )


@pytest.fixture
async def ssh_worker(local_server, tmp_path):
    config, worker_port, worker = local_server
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    key_path = tmp_path / "client.key"
    key_path.write_bytes(client_key.export_private_key())
    key_path.chmod(0o600)
    connections, destinations = [], []
    allowed = {client_key.convert_to_public()}

    class Server(asyncssh.SSHServer):
        def connection_made(self, connection):
            connections.append(connection)

        def begin_auth(self, username):
            return True

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            return username == "deermate" and key in allowed

        def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
            destinations.append((dest_host, dest_port))
            return dest_host == "127.0.0.1" and dest_port == worker_port

        def session_requested(self):
            return False

    server = await asyncssh.create_server(
        Server,
        "127.0.0.1",
        0,
        server_host_keys=[host_key],
    )
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(
        f"[127.0.0.1]:{server.get_port()} " + host_key.export_public_key().decode()
    )
    known_hosts.chmod(0o644)
    data = {
        "host": "127.0.0.1",
        "port": server.get_port(),
        "username": "deermate",
        "known_hosts": str(known_hosts),
        "client_key": str(key_path),
        "token_file": str(worker.settings.state_dir / "api.token"),
        "expected_instance_id": worker.store.instance_id,
        "worker_port": worker_port,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    controller = tmp_path / "controller.toml"
    write_enrollment(controller, data)
    try:
        yield {
            "config": controller,
            "data": data,
            "worker": worker,
            "worker_config": config,
            "server": server,
            "connections": connections,
            "destinations": destinations,
            "allowed": allowed,
            "client_key": client_key,
            "host_key": host_key,
        }
    finally:
        server.close()
        for connection in connections:
            connection.close()
        await server.wait_closed()
        for connection in connections:
            await connection.wait_closed()
