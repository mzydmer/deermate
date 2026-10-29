"""Thread-scoped continuation policy, independent of the optional DeerFlow runtime."""

import re

from .models import ContinueTask
from .store import digest

HISTORY_LIMIT = 50


class ConversationError(ValueError):
    pass


def select_parent(records: list[dict], task: str | None, *, user_id: str, thread_id: str) -> dict:
    candidates = []
    for record in records:
        data = record.get("driver_data") or {}
        if (
            record.get("user_id") == user_id
            and record.get("thread_id") == thread_id
            and record.get("driver_name") == "ordinary-tools"
            and data.get("submit_tool") in {"submit_task", "continue_task"}
            and (data.get("status_tool"), data.get("cancel_tool"))
            in {
                ("get_task_status", "cancel_task"),
                ("get_continuation_status", "cancel_continuation_task"),
            }
        ):
            candidates.append(record)
    if task:
        candidates = [record for record in candidates if record["id"] == task]
        if len(candidates) != 1:
            raise ConversationError("Task not found in this chat; use its public DeerFlow task ID.")
    else:
        if len(records) >= HISTORY_LIMIT:
            raise ConversationError("History is bounded; provide the latest public task ID.")
        if not candidates or any(
            record.get("status") not in {"completed", "failed", "cancelled"}
            for record in candidates
        ):
            raise ConversationError("No unambiguous finished conversation; inspect current tasks.")
        groups = {
            (record["server_name"], (record.get("result") or {}).get("session_id"))
            for record in candidates
        }
        if len(groups) != 1 or next(iter(groups))[1] is None:
            raise ConversationError(
                "Several conversations exist; provide the latest public task ID."
            )
        candidates = [max(candidates, key=lambda record: (record["created_at"], record["id"]))]
    parent = candidates[0]
    if parent.get("status") not in {"completed", "failed", "cancelled"}:
        raise ConversationError("Task is active or needs explicit input/review/recovery first.")
    if not (parent.get("result") or {}).get("session_id"):
        raise ConversationError("No confirmed native session; inspect the original task.")
    if not re.fullmatch(r"(?:[0-9a-f]{32}:)?[0-9a-f]{32}", parent.get("remote_task_id", "")):
        raise ConversationError("Task has no supported enrolled Worker handle.")
    return parent


async def continue_in_chat(
    submitter,
    request_factory,
    *,
    user_id,
    thread_id,
    incarnation,
    call_id,
    run_id,
    message,
    task=None,
):
    if not all(
        isinstance(value, str) and value for value in (user_id, thread_id, incarnation, call_id)
    ):
        raise ConversationError("Authenticated chat context is required; no task was submitted.")
    key = "codex-followup-" + digest(
        {"user": user_id, "thread": thread_id, "incarnation": incarnation, "call": call_id}
    )
    body = ContinueTask(message=message, idempotency_key=key)
    scope = {"user_id": user_id, "thread_id": thread_id, "thread_incarnation": incarnation}
    records = await submitter.list_tasks(**scope, limit=HISTORY_LIMIT, active_only=False)
    message_digest = digest({"message": body.message})
    for record in records:
        marker = (record.get("driver_data") or {}).get("deermate_followup") or {}
        if (
            record.get("user_id") == user_id
            and record.get("thread_id") == thread_id
            and record.get("tool_call_id") == call_id
            and marker
        ):
            if marker.get("message_digest") != message_digest or (
                task is not None and marker.get("parent_task_id") != task
            ):
                raise ConversationError("Follow-up identity conflicts with its saved request.")
            return {"task_id": record["id"], "status": record["status"], "reconciled": True}
    parent = select_parent(records, task, user_id=user_id, thread_id=thread_id)
    created = await submitter.submit(
        driver_name="ordinary-tools",
        request=request_factory(
            **scope,
            run_id=run_id,
            tool_call_id=call_id,
            server_name=parent["server_name"],
            task_name=parent["task_name"],
            arguments={"task_id": parent["remote_task_id"], **body.model_dump()},
            driver_data={
                **parent["driver_data"],
                "submit_tool": "continue_task",
                "status_tool": "get_continuation_status",
                "cancel_tool": "cancel_continuation_task",
                "deermate_followup": {
                    "message_digest": message_digest,
                    "parent_task_id": parent["id"],
                },
            },
        ),
    )
    return {
        "task_id": created["id"],
        "parent_task_id": parent["id"],
        "status": created["status"],
        "message": "Follow-up is tracked in this chat using the same Codex session and workspace.",
    }
