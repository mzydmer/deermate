"""Scope-bound bridge over the Go relay; no arbitrary network target in tool arguments."""

import json
import re
import time
from pathlib import Path

import httpx

from .authorization import private_json
from .bridge import BridgeError, TaskBridge, connection_report, task_path


def operation_path(method, path):
    if method == "GET":
        return path == "/capabilities" or bool(re.fullmatch(r"/tasks/[0-9a-f]{32}", path))
    return method == "POST" and (
        path == "/tasks" or bool(re.fullmatch(r"/tasks/[0-9a-f]{32}/(?:cancel|continue)", path))
    )


class RelayTransport(httpx.AsyncBaseTransport):
    def __init__(self, origin, grant):
        self.grant = grant
        self.client = httpx.AsyncClient(
            base_url=origin, trust_env=False, follow_redirects=False, timeout=18
        )

    async def handle_async_request(self, request):
        if not operation_path(request.method, request.url.path):
            raise BridgeError("Operation not allowed by relay")
        response = await self.client.post(
            "/api/agent-relay/" + self.grant["id"] + "/requests",
            json={
                "method": request.method,
                "path": request.url.path,
                "body": json.loads(request.content) if request.content else None,
            },
            headers={"Authorization": "Bearer " + self.grant["token"]},
        )
        if len(response.content) > 2_000_000:
            raise BridgeError("Relay response exceeded limit")
        return httpx.Response(
            response.status_code,
            content=response.content,
            headers={"Content-Type": "application/json"},
        )

    async def aclose(self):
        await self.client.aclose()


class BoundRelayBridge(TaskBridge):
    def __init__(self, origin, grant):
        self.grant = grant
        super().__init__(Path("unused"), transport=RelayTransport(origin, grant), cancel_timeout=35)
        self.client.timeout = httpx.Timeout(20)
        self.connection_info = {"type": "https-relay", "worker_id": grant["id"]}

    def _read_token(self):
        return self.grant["token"]

    async def check_connection(self):
        result = await super().check_connection()
        if result["status"] == "reachable":
            if result["capabilities"].get("authorization_protocol") != "local-grants-v1":
                return connection_report(
                    self.connection_info,
                    error=BridgeError(
                        "Worker upgrade required for local authorization enforcement",
                        code="unsupported_protocol",
                    ),
                )
            if result["capabilities"]["instance_id"] != self.grant["instance_id"]:
                return connection_report(
                    self.connection_info,
                    error=BridgeError("Worker identity mismatch", code="worker_identity_mismatch"),
                )
            result["identity"] = {
                "transport": "authenticated_https_relay",
                "worker_instance": "pinned",
            }
        return result


class RelayDirectoryBridge:
    def __init__(self, config, origin="http://control:8080"):
        if origin not in {"http://control:8080", "http://127.0.0.1:8080"}:
            raise ValueError("Relay MCP uses the fixed internal Go control-plane origin")
        self.config = config
        self.origin = origin

    def target(self, *, project=None, handle=None):
        try:
            grants = private_json(self.config)["grants"]
        except (OSError, ValueError, KeyError) as error:
            raise BridgeError(
                "No active device authorization; open Agent authorizations", code="not_enrolled"
            ) from error
        candidates = [
            g
            for g in grants
            if (g.get("expires_at") is None or g["expires_at"] > time.time())
            and (project is None or project in g["projects"])
        ]
        native = None
        if handle is not None:
            instance, sep, native = handle.partition(":")
            if sep != ":":
                raise BridgeError("Use the saved Worker instance-bound task handle")
            task_path(native)
            candidates = [g for g in candidates if g["instance_id"] == instance]
        if len(candidates) != 1:
            raise BridgeError(
                "Select exactly one active authorization for this project/device",
                code="authorization_selection_required",
            )
        return candidates[0], native

    async def close(self):
        pass

    async def check_connection(self):
        try:
            grant, _ = self.target()
            bridge = BoundRelayBridge(self.origin, grant)
            try:
                return await bridge.check_connection()
            finally:
                await bridge.close()
        except BridgeError as error:
            return connection_report({"type": "https-relay"}, error=error)

    async def operation(self, name, *, handle=None, project=None, **arguments):
        grant, native = self.target(project=project, handle=handle)
        bridge = BoundRelayBridge(self.origin, grant)
        try:
            # Native namespace is checked before every mutation, not just in a model preflight.
            report = await bridge.check_connection()
            if report["status"] != "reachable":
                raise BridgeError(
                    "Authorization or Worker connection blocked; no task mutation was submitted"
                )
            result = await getattr(bridge, name)(
                **arguments, **({"task_id": native} if native else {})
            )
            result["task_id"] = grant["instance_id"] + ":" + result["task_id"]
            for key in ("parent_task_id", "conversation_id"):
                if result.get("result", {}).get(key):
                    result["result"][key] = grant["instance_id"] + ":" + result["result"][key]
            return result
        finally:
            await bridge.close()

    async def submit(self, project_id, prompt, idempotency_key):
        return await self.operation(
            "submit",
            project=project_id,
            project_id=project_id,
            prompt=prompt,
            idempotency_key=idempotency_key,
        )

    async def status(self, task_id):
        return await self.operation("status", handle=task_id)

    async def continue_task(self, task_id, message, idempotency_key):
        return await self.operation(
            "continue_task", handle=task_id, message=message, idempotency_key=idempotency_key
        )

    async def cancel(self, task_id):
        return await self.operation("cancel", handle=task_id)
