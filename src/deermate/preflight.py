"""Operator entry point; configuration failures are sanitized JSON check results."""

from pathlib import Path

from .bridge import BridgeError, TaskBridge, connection_report
from .config import load_settings


async def check_worker(config: Path, port: int, worker_id: str | None) -> dict:
    connection = {"type": "ssh", "worker_id": worker_id} if worker_id else {"type": "loopback"}
    try:
        if worker_id:
            try:
                from .ssh import RemoteTaskBridge
            except ImportError:
                return connection_report(
                    connection,
                    error=BridgeError(
                        "SSH support requires installation with the 'ssh' extra.",
                        code="dependency_unavailable",
                    ),
                )
            bridge = RemoteTaskBridge(config, worker_id)
        else:
            settings = load_settings(config)
            bridge = TaskBridge(settings.state_dir / "api.token", port)
    except BridgeError as error:
        return connection_report(connection, error=error)
    except (OSError, ValueError):
        return connection_report(
            connection,
            error=BridgeError(
                "Local Worker configuration is unavailable or invalid.",
                code="configuration_invalid",
            ),
        )
    try:
        return await bridge.check_connection()
    finally:
        await bridge.close()
