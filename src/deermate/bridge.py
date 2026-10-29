"""Local HTTP client and the DeerFlow ordinary-tools lifecycle mapping."""

import asyncio
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import ValidationError

from .models import ContinueTask, State, SubmitTask, Task
from .protocol import CAPABILITIES_LIMIT, ProtocolError, parse_capabilities

CONNECTION_CHECK_TIMEOUT = 15


def connection_report(connection: dict, *, capabilities=None, error=None) -> dict:
    report = {
        "status": "blocked" if error else "reachable",
        "checked_at": datetime.now(UTC).isoformat(),
        "connection": connection,
        "execution_readiness": "not_checked",
        "task_outcome": "not_checked",
    }
    if error:
        report["error"] = {"code": error.code, "message": str(error)}
    else:
        report["capabilities"] = capabilities.model_dump()
        report["identity"] = {
            "ssh_host_key": "verified" if connection["type"] == "ssh" else "not_applicable",
            "worker_instance": "pinned" if connection["type"] == "ssh" else "observed",
        }
    return report


class BridgeError(RuntimeError):
    """A tool call failed; the task's outcome is not established by this error."""

    def __init__(self, message: str, *, code: str = "connection_rejected"):
        super().__init__(message)
        self.code = code


class TaskMissing(BridgeError):
    pass


def read_token(path: Path) -> str:
    """Read an existing private token without creating or following a symlink."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd) as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise BridgeError(
                    "Worker token must be a private regular file.", code="credential_invalid"
                )
            token = source.read(1024).strip()
    except (OSError, UnicodeError) as error:
        raise BridgeError(
            "Worker token is unavailable; start the configured local Worker.",
            code="credential_unavailable",
        ) from error
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        raise BridgeError("Worker token is invalid.", code="credential_invalid")
    return token


def task_path(task_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", task_id):
        raise BridgeError("task_id must be the 32-character ID returned by submit_task.")
    return f"/tasks/{task_id}"


def missing(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "status": "failed",
        "error_code": "task_not_found",
        "error": "The configured Worker does not recognize this task ID.",
    }


def snapshot(task: Task) -> dict:
    """Never expose a Task wholesale: it contains prompt, paths and policy."""
    response = {"task_id": task.task_id, "worker_status": task.status.value}
    if task.status in {State.COMPLETED, State.FAILED, State.CANCELLED}:
        response["status"] = task.status.value
    elif task.status in {State.INPUT_REQUIRED, State.NEEDS_REVIEW, State.RECOVERY_REQUIRED}:
        response["status"] = "input_required"
        guidance = {
            State.INPUT_REQUIRED: "Inspect local events and use the local answer command.",
            State.NEEDS_REVIEW: "Inspect local status, validation and diff before continuing.",
            State.RECOVERY_REQUIRED: (
                "Verify the previous process stopped before explicit recovery."
            ),
        }
        response["input_required"] = {
            "kind": task.status.value,
            "message": guidance[task.status],
            "inspect_command": f"deermate status {task.task_id}",
            "events_command": f"deermate events {task.task_id}",
        }
    else:
        response["status"] = "running"
    if response["status"] in {"running", "input_required"}:
        response["poll_after_seconds"] = 5
    if task.status == State.FAILED:
        response["error"] = "Worker execution or validation failed; inspect local task evidence."
    if task.result is not None:
        result = task.result
        summary = str(result.get("summary", ""))
        evidence = {
            "worker_status": task.status.value,
            "session_id": task.session_id,
            "attempt": task.attempt,
            "conversation_id": task.root_task_id or task.task_id,
            "parent_task_id": task.parent_task_id,
            "conversation_round": task.conversation_round,
            "summary": summary[:2000],
            "summary_truncated": len(summary) > 2000,
            "validation_status": result.get("validation_status"),
            "diff_available": bool(result.get("diff")),
            "diff_command": f"deermate diff {task.task_id}",
            "acceptance": "Configured command exit status; not a correctness guarantee.",
        }
        receipt = result.get("validation")
        if isinstance(receipt, dict):
            stdout, stderr = str(receipt.get("stdout", "")), str(receipt.get("stderr", ""))
            evidence["validation"] = {
                "exit_code": receipt.get("exit_code"),
                "stdout": stdout[:2000],
                "stderr": stderr[:2000],
                "output_truncated": len(stdout) > 2000 or len(stderr) > 2000,
            }
        response["result"] = evidence
    return response


class TaskBridge:
    def __init__(
        self,
        token_path: Path,
        port: int = 18777,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        cancel_timeout: float = 8,
    ):
        if not 1 <= port <= 65535:
            raise ValueError("Worker port must be between 1 and 65535")
        self.token_path = token_path
        self.connection_info = {"type": "loopback"}
        self.cancel_timeout = cancel_timeout
        self.client = httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            timeout=6,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    async def close(self):
        await self.client.aclose()

    async def check_connection(self) -> dict:
        """Read authenticated capabilities without admitting work or running an agent."""
        try:
            async with asyncio.timeout(CONNECTION_CHECK_TIMEOUT):
                token = await asyncio.to_thread(read_token, self.token_path)
                async with self.client.stream(
                    "GET", "/capabilities", headers={"Authorization": f"Bearer {token}"}
                ) as response:
                    if response.status_code in {401, 403}:
                        raise BridgeError(
                            "Worker authentication or local access check failed.",
                            code="authentication_rejected",
                        )
                    if response.status_code != 200:
                        raise BridgeError(
                            "Worker capabilities endpoint was rejected.", code="endpoint_rejected"
                        )
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > CAPABILITIES_LIMIT:
                            raise BridgeError(
                                "Worker capabilities exceeded the response limit.",
                                code="invalid_response",
                            )
                        chunks.append(chunk)
                    capabilities = parse_capabilities(b"".join(chunks))
            return connection_report(self.connection_info, capabilities=capabilities)
        except ProtocolError as error:
            failure = BridgeError(str(error), code=error.code)
        except BridgeError as error:
            failure = error
        except (TimeoutError, httpx.TimeoutException):
            failure = BridgeError("Worker connection check timed out.", code="timeout")
        except httpx.HTTPError:
            failure = BridgeError("Worker connection is unavailable.", code="unavailable")
        return connection_report(self.connection_info, error=failure)

    async def _request(self, method: str, path: str, body: dict | None = None) -> Task:
        try:
            async with self.client.stream(
                method,
                path,
                json=body,
                headers={"Authorization": f"Bearer {read_token(self.token_path)}"},
            ) as response:
                if response.status_code == 404:
                    if method == "POST" and path == "/tasks":
                        raise BridgeError("Project is not registered in the configured Worker.")
                    raise TaskMissing("Task not found.")
                if response.status_code in {401, 403}:
                    raise BridgeError("Worker authentication or local access check failed.")
                if response.status_code == 409:
                    raise BridgeError("Request conflicts with an existing key or task state.")
                if response.status_code >= 300:
                    raise BridgeError(f"Worker rejected the request (HTTP {response.status_code}).")
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise BridgeError("Worker response exceeded the bridge limit.")
                    chunks.append(chunk)
                return Task.model_validate_json(b"".join(chunks))
        except httpx.HTTPError as error:
            raise BridgeError(
                "Local Worker is unavailable or timed out; task outcome is unknown. "
                "Retry with the same task ID or submission key."
            ) from error
        except ValidationError as error:
            raise BridgeError(
                "Worker returned an invalid task response; outcome is unknown."
            ) from error

    async def submit(self, project_id: str, prompt: str, idempotency_key: str) -> dict:
        request = SubmitTask(project_id=project_id, prompt=prompt, idempotency_key=idempotency_key)
        task = await self._request("POST", "/tasks", request.model_dump())
        # DeerFlow's submit parser only accepts running. Polling resolves even a
        # duplicate of an already terminal task without replaying its execution.
        return {"task_id": task.task_id, "status": "running", "worker_status": task.status.value}

    async def status(self, task_id: str) -> dict:
        path = task_path(task_id)
        try:
            task = await self._request("GET", path)
        except TaskMissing:
            return missing(task_id)
        if task.task_id != task_id:
            raise BridgeError("Worker response did not match the requested task ID.")
        return snapshot(task)

    async def continue_task(self, task_id: str, message: str, idempotency_key: str) -> dict:
        path = task_path(task_id)
        request = ContinueTask(message=message, idempotency_key=idempotency_key)
        report = await self.check_connection()
        if report["status"] != "reachable":
            raise BridgeError("Worker connection is blocked; no continuation was submitted.")
        if report["capabilities"].get("continuation") != "child-tasks-v1":
            raise BridgeError(
                "Worker does not support conversation continuation; upgrade it first."
            )
        task = await self._request("POST", path + "/continue", request.model_dump())
        if task.parent_task_id != task_id or task.task_id == task_id:
            raise BridgeError("Worker continuation identity did not match; outcome is unknown.")
        return {"task_id": task.task_id, "status": "running", "worker_status": task.status.value}

    async def cancel(self, task_id: str) -> dict:
        path = task_path(task_id)
        try:
            # Bound the complete call, including HTTP requests and confirmation.
            async with asyncio.timeout(self.cancel_timeout):
                task = await self._request("POST", path + "/cancel")
                while True:
                    if task.task_id != task_id:
                        raise BridgeError("Worker response did not match the requested task ID.")
                    if task.status in {State.COMPLETED, State.FAILED, State.CANCELLED}:
                        return snapshot(task)
                    if task.status in {State.NEEDS_REVIEW, State.RECOVERY_REQUIRED}:
                        raise BridgeError(
                            "Task requires local review or recovery; cancellation is unconfirmed."
                        )
                    await asyncio.sleep(0.1)
                    task = await self._request("GET", path)
        except TaskMissing:
            return missing(task_id)
        except TimeoutError as error:
            raise BridgeError(
                "Cancellation is not confirmed; poll status or retry cancellation."
            ) from error
