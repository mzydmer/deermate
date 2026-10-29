"""Optional tool provider loaded via pinned DeerFlow's supported tools[].use config."""

from typing import Annotated

from deerflow.mcp.tasks.models import TaskSubmitRequest
from deerflow.mcp.tasks.runtime import get_mcp_task_submitter
from deerflow.mcp_scope import runtime_thread_incarnation
from deerflow.tools.builtins.list_uploaded_files_tool import _resolve_thread_id, _resolve_user_id
from deerflow.tools.types import Runtime
from langchain.tools import tool

from .conversation import ConversationError, continue_in_chat


@tool
async def continue_codex(
    runtime: Runtime,
    message: Annotated[str, "The next question or change for the existing remote Codex session."],
    task: Annotated[
        str | None,
        "Public DeerFlow task ID from this chat, not a native/remote ID. "
        "Omit only for one unambiguous finished conversation.",
    ] = None,
) -> dict:
    """Ask a follow-up in the same Codex session and workspace in this chat.

    Use for explanations and further edits after a previous Codex task finishes.
    Every round has a new tracked task and notification, preserving earlier results.
    Do not start a replacement task on an error: inspect status first. This tool
    never approves recovery or answers native permission/form requests.
    """
    try:
        return await continue_in_chat(
            get_mcp_task_submitter(),
            TaskSubmitRequest,
            user_id=_resolve_user_id(runtime),
            thread_id=_resolve_thread_id(runtime),
            incarnation=runtime_thread_incarnation(runtime),
            call_id=getattr(runtime, "tool_call_id", None),
            run_id=(runtime.context or {}).get("run_id"),
            message=message,
            task=task,
        )
    except ConversationError as error:
        return {"status": "not_submitted", "message": str(error)}
    except Exception:
        # A timeout/error can follow admission. Do not expose transport details or retry.
        return {
            "status": "outcome_unknown",
            "message": "Follow-up was not confirmed. Inspect this chat's background tasks; "
            "do not resubmit or start a replacement Codex session automatically.",
        }
