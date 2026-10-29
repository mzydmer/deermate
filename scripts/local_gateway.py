"""Local verification Gateway: original app plus an owner/key-protected submit shim.

Staged only by the local development profile, never baked into ACK images.
"""

import os
import secrets
import uuid
from types import SimpleNamespace

import uvicorn
from app.gateway.app import app
from app.gateway.deps import get_current_user_from_request, get_mcp_task_repo, get_thread_store
from deerflow.mcp.tools import get_mcp_tools
from deerflow.persistence.mcp_tasks.sql import DuplicateMcpRemoteTaskError
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    thread_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    prompt: str = Field(min_length=1, max_length=8000)
    key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")


@app.post("/api/deermate-local/submit", tags=["local verification only"])
async def submit(request: Request, body: Submission):
    expected = os.environ.get("DEERMATE_LOCAL_VERIFICATION_KEY", "")
    supplied = request.headers.get("X-DeerMate-Local", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        raise HTTPException(403, "Local verification key required")
    user = await get_current_user_from_request(request)
    if user.system_role != "admin":
        raise HTTPException(403, "Local verification requires the owner administrator")
    user_id = str(user.id)
    thread = await get_thread_store(request).get(body.thread_id, user_id=user_id)
    if thread is None:
        raise HTTPException(404, "Thread not found")
    tools = await get_mcp_tools()
    by_name = {tool.name: tool for tool in tools}
    if "deermate_submit_task" not in by_name or set(by_name) - {
        "deermate_submit_task",
        "deermate_check_worker_connection",
    }:
        raise HTTPException(503, "Expected enrolled Worker tool is unavailable")
    runtime = SimpleNamespace(
        context={
            "thread_id": body.thread_id,
            "thread_incarnation": thread.get("incarnation"),
            "user_id": user_id,
        },
        config={},
        tool_call_id=uuid.uuid4().hex,
    )
    try:
        result = await by_name["deermate_submit_task"].coroutine(
            runtime=runtime, project_id="demo", prompt=body.prompt, idempotency_key=body.key
        )
    except DuplicateMcpRemoteTaskError as error:
        # The pinned upstream permits one durable owner per remote handle. Keep
        # that policy: a second tracking row is a conflict, not another task.
        records = await get_mcp_task_repo(request).list_by_thread(
            body.thread_id, user_id=user_id, thread_incarnation=thread.get("incarnation"), limit=100
        )
        for record in records:
            # This exception has no structured handle in the pinned upstream.
            # Match its complete message against scoped SQL records, rather than
            # extracting an unscoped identifier or revealing another thread.
            expected_error = (
                f"Remote MCP task {record['remote_task_id']!r} is already tracked "
                "for server 'deermate' by this user"
            )
            if record["server_name"] == "deermate" and str(error) == expected_error:
                raise HTTPException(
                    409,
                    {
                        "error": "remote_handle_already_tracked",
                        "task_id": record["id"],
                        "remote_task_id": record["remote_task_id"],
                    },
                ) from None
        raise HTTPException(409, "Remote handle already tracked outside this thread") from None
    record = await get_mcp_task_repo(request).get(
        result["task_id"],
        user_id=user_id,
        thread_id=body.thread_id,
        thread_incarnation=thread.get("incarnation"),
    )
    if record is None:
        raise HTTPException(503, "Tracking row was not committed")
    return {
        "tracking": result,
        "remote_task_id": record["remote_task_id"],
        "visible_tools": [tool.name for tool in tools],
    }


if __name__ == "__main__":
    if not os.environ.get("DEERMATE_LOCAL_VERIFICATION_KEY"):
        raise SystemExit("A local verification key is required")
    uvicorn.run(app, host="0.0.0.0", port=8001, access_log=False, log_level="warning")
