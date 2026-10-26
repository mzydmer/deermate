"""Generated-key, loopback-only SSH fixture process for the Gateway demo.

This is test infrastructure, never an operator's SSH daemon or production API.
"""

import argparse
import asyncio
import json
import os
import signal
from pathlib import Path

import asyncssh


async def serve(state: Path, port: int, worker_port: int):
    stats_path = state / "stats.json"
    stats = {
        "generation": 0,
        "connections": 0,
        "authenticated": 0,
        "forward_requests": 0,
        "denied_forwards": 0,
        "denied_sessions": 0,
    }
    if stats_path.exists():
        previous = json.loads(stats_path.read_text())
        stats.update({key: int(previous[key]) for key in stats})
    stats["generation"] += 1
    stats["ready"] = False
    connections = []
    client_key = asyncssh.read_public_key(state / "client.pub")

    def save():
        temporary = state / "stats.tmp"
        temporary.write_text(json.dumps(stats))
        temporary.chmod(0o600)
        os.replace(temporary, stats_path)

    class Server(asyncssh.SSHServer):
        def connection_made(self, connection):
            connections.append(connection)
            stats["connections"] += 1
            save()

        def begin_auth(self, username):
            return True

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            return username == "deermate" and key == client_key

        def auth_completed(self):
            stats["authenticated"] += 1
            save()

        def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
            allowed = dest_host == "127.0.0.1" and dest_port == worker_port
            stats["forward_requests"] += 1
            if not allowed:
                stats["denied_forwards"] += 1
            save()
            return allowed

        def session_requested(self):
            stats["denied_sessions"] += 1
            save()
            return False

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    server = await asyncssh.create_server(
        Server,
        "127.0.0.1",
        port,
        server_host_keys=[asyncssh.read_private_key(state / "host.key")],
    )
    try:
        stats["ready"] = True
        save()
        print("Loopback SSH fixture ready.", flush=True)
        await stop.wait()
    finally:
        stats["ready"] = False
        save()
        server.close()
        for connection in connections:
            connection.close()
        try:
            async with asyncio.timeout(5):
                await server.wait_closed()
                for connection in connections:
                    await connection.wait_closed()
        except TimeoutError:
            for connection in connections:
                connection.abort()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--worker-port", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(serve(args.state, args.port, args.worker_port))


if __name__ == "__main__":
    main()
