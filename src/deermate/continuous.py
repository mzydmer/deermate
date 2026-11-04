"""Narrow, identity-preserving operations over the pinned DeerFlow runtime.

Go owns admissions. This adapter never chooses a host/project, retries a submit,
changes a native root, or runs a second coding model.
"""

import asyncio
import hashlib
import hmac
import json
import time

from .briefing import gate

NAMESPACE = "deermate.continuous"


def record(db, owner, kind, identifier):
    row = db.execute(
        "SELECT * FROM deermate_work_records WHERE owner=? AND kind=? AND id=?",
        (owner, kind, identifier),
    ).fetchone()
    if not row:
        raise PermissionError("The owned operation is unavailable")
    return {**dict(row), "data": json.loads(row["data"])}


def load(owner, payload, *, writing=False):
    with gate(owner) as (db, user):
        op = record(db, owner, "operation", payload.get("operation_id"))
        data = op["data"]
        if (
            data.get("_user_version") != user["token_version"]
            or not isinstance(payload.get("nonce"), str)
            or not hmac.compare_digest(payload["nonce"], data.get("_nonce", ""))
            or op["state"] not in {"dispatching", "acknowledged", "uncertain", "settled"}
        ):
            raise PermissionError("A current canonical admission is required")
        if writing:
            if op["state"] != "dispatching":
                raise PermissionError("This operation may only be reconciled")
            settings = record(db, owner, "settings", "settings")
            if not settings["data"].get("enabled"):
                raise PermissionError("Continuous work is disabled")
            if data["kind"] in {"execute", "followup", "cancel"}:
                validate_native(db, owner, op)
            elif data["kind"] == "assessor":
                event = record(db, owner, "event", data["event_id"])
                rule = record(db, owner, "rule", data["rule_id"])
                source = record(db, owner, "source", event["data"]["source_id"])
                if (
                    event["revision"] != data["event_revision"]
                    or rule["revision"] != data["rule_revision"]
                    or rule["state"] == "off"
                    or source["state"] != "enabled"
                    or source["data"]["generation"] != data["source_generation"]
                ):
                    raise PermissionError("The assessment source changed")
        return op


def validate_native(db, owner, op):
    data = op["data"]
    work = record(db, owner, "work", op["parent"])
    if (
        data["thread_id"] != work["data"]["thread_id"]
        or data["project"] != work["data"]["project"]
        or (data["kind"] != "cancel" and work["state"] != "active")
    ):
        raise PermissionError("The work scope changed")
    row = db.execute(
        "SELECT data FROM deermate_agent_grants WHERE owner=? AND id=?",
        (owner, data["grant_id"]),
    ).fetchone()
    grant = json.loads(row[0]) if row else {}
    policy = grant.get("active") or {}
    operation = {"execute": "submit", "followup": "continue", "cancel": "cancel"}[data["kind"]]
    if (
        grant.get("revoked")
        or grant.get("version") != data["grant_version"]
        or grant.get("instance_id") != data["instance_id"]
        or not policy
        or (policy.get("expires_at") is not None and policy["expires_at"] <= time.time())
        or data["project"] not in policy.get("projects", [])
        or operation not in policy.get("operations", [])
    ):
        raise PermissionError("The device admission changed")
    for ref in data.get("context_refs", []):
        event = record(db, owner, "event", ref["id"])
        source = record(db, owner, "source", event["data"]["source_id"])
        if (
            event["revision"] != ref["revision"]
            or source["state"] != "enabled"
            or source["data"].get("error")
            or source["data"].get("generation") != event["data"]["source_generation"]
        ):
            raise PermissionError("Subscribed reference data changed before admission")
    return work


def canonical_key(owner, thread, opid):
    return (
        "http-run:"
        + hashlib.sha256(
            (owner + "\0" + thread + "\0extension:" + NAMESPACE + ":" + opid).encode()
        ).hexdigest()
    )


def thread_scope(owner, op):
    from .chat_sessions import ChatScope

    with gate(owner) as (db, _):
        row = db.execute(
            "SELECT incarnation,metadata_json,project_id FROM threads_meta "
            "WHERE user_id=? AND thread_id=?",
            (owner, op["data"]["thread_id"]),
        ).fetchone()
        if (
            not row
            or not row["incarnation"]
            or row["project_id"]
            or json.loads(row["metadata_json"] or "{}").get("deerflow_archived")
            or (op["data"].get("incarnation") and row["incarnation"] != op["data"]["incarnation"])
        ):
            raise PermissionError("The execution conversation changed")
        return ChatScope(owner, op["data"]["thread_id"], row["incarnation"])


async def perform(payload, context):
    from .memory import _owner

    owner = _owner(context)
    try:
        op = await asyncio.to_thread(load, owner, payload, writing=True)
    except PermissionError:
        # This branch is strictly before run/native admission. It is positive
        # rejection evidence, unlike a timeout after crossing the send barrier.
        return {
            "known": True,
            "accepted": False,
            "status": "rejected",
            "preview": "Scope or authorization changed before admission",
        }
    runs = context.agent_runs
    if runs is None:
        raise PermissionError("Host-owned run admission is unavailable")
    data = op["data"]
    title = (
        "私人秘书"
        if data["kind"] == "router"
        else ("规则研判" if data["kind"] == "assessor" else data.get("message", "工作")[:40])
    )
    await runs.create_thread(thread_id=data["thread_id"], metadata={"title": title})
    # Check canonical authority again after creating a thread and before effects.
    op = await asyncio.to_thread(load, owner, payload, writing=True)
    if data["kind"] in {"router", "assessor"}:
        run = await runs.start(
            thread_id=data["thread_id"],
            input={
                "messages": [
                    {
                        "type": "human",
                        "id": "continuous-" + op["id"],
                        "content": data["message"],
                        "additional_kwargs": {
                            "deermate_continuous_operation": op["id"],
                            "deermate_continuous_token": data["_nonce"],
                        },
                    }
                ]
            },
            context={
                "model_name": data["model"],
                "model_selection_requested": data["model"],
                "thinking_enabled": False,
                "subagent_enabled": False,
            },
            idempotency_key=op["id"],
        )
        return {
            "known": True,
            "accepted": True,
            "run_id": run.run_id,
            "thread_id": run.thread_id,
            "status": normalize_run(run.status),
        }
    from deerflow.mcp.tasks.models import TaskSubmitRequest
    from deerflow.mcp.tasks.runtime import get_mcp_task_submitter

    from .chat_sessions import ask_in_chat
    from .session_middleware import DEFAULT_PROFILES, journal

    scope = await asyncio.to_thread(thread_scope, owner, op)
    saved = journal()
    binding = await asyncio.to_thread(saved.binding, scope)
    if data["kind"] != "cancel" and (binding or {}).get("head", "") != data["expected_head"]:
        raise PermissionError("The coding head changed; inspect the original work")
    if data["kind"] == "cancel":
        tracking = await asyncio.to_thread(cancel_tracking, saved, scope, op)
        if not tracking:
            return {"known": False, "status": "original_admission_unknown"}
        await get_mcp_task_submitter().cancel_matching_task(**scope.query(), task=tracking)
        return {
            "known": True,
            "accepted": True,
            "status": "cancel_requested",
            "thread_id": scope.thread_id,
            "incarnation": scope.incarnation,
        }
    from .work_reports import work_prompt

    await ask_in_chat(
        saved,
        get_mcp_task_submitter(),
        TaskSubmitRequest,
        scope=scope,
        profiles=DEFAULT_PROFILES,
        call_id=op["id"],
        run_id="continuous:" + op["id"],
        server=data["server"],
        message=work_prompt(op["parent"], op["id"], data["project"], data["message"]),
        project=data["project"],
        explicit_task=data["expected_head"] or None,
    )
    return await query(payload, context)


def normalize_run(status):
    return {"success": "completed", "interrupted": "input_required", "error": "failed"}.get(
        status, status
    )


async def query(payload, context):
    from .memory import _owner

    owner = _owner(context)
    op = await asyncio.to_thread(load, owner, payload)
    data = op["data"]
    if data["kind"] in {"router", "assessor"}:
        with gate(owner) as (db, _):
            row = db.execute(
                "SELECT run_id FROM runs WHERE user_id=? AND thread_id=? AND idempotency_key=?",
                (owner, data["thread_id"], canonical_key(owner, data["thread_id"], op["id"])),
            ).fetchone()
        if not row:
            return {"known": False, "status": "admission_unknown"}
        run = await context.agent_runs.get(thread_id=data["thread_id"], run_id=row["run_id"])
        status = normalize_run(run.status)
        preview = ""
        if status in {"completed", "failed", "input_required", "cancelled"}:
            # Go serializes router admission through receipt settlement. A later
            # run cannot replace this latest-state result before it is retained.
            state = await context.agent_runs.get_state(thread_id=data["thread_id"])
            messages = state.get("values", {}).get("messages", [])
            for message in reversed(messages):
                kind = message.get("type", message.get("role"))
                if kind in {"ai", "assistant", "tool"}:
                    content = message.get("content", "")
                    if isinstance(content, str) and content:
                        preview = content[:8000]
                        if data["kind"] == "router" and kind == "tool":
                            try:
                                reply = json.loads(content)
                                preview = reply.get("message") or (
                                    "已记录安排，操作 ID：" + reply["id"]
                                    if reply.get("id")
                                    else "已读取工作引用。"
                                )
                            except (ValueError, TypeError, KeyError):
                                preview = "已收到工作操作的回执。"
                        break
        return {
            "known": True,
            "run_id": run.run_id,
            "thread_id": data["thread_id"],
            "status": status,
            "preview": preview,
        }
    from deerflow.mcp.tasks.runtime import get_mcp_task_submitter

    from .session_middleware import journal
    from .store import digest

    scope = await asyncio.to_thread(thread_scope, owner, op)
    saved = journal()
    call = digest({"run": "continuous:" + op["id"], "call": op["id"]})
    turn = await asyncio.to_thread(saved.turn, scope, call)
    tracking = (turn or {}).get("tracking_id")
    if data["kind"] == "cancel":
        tracking = await asyncio.to_thread(cancel_tracking, saved, scope, op)
    if not tracking:
        return {"known": False, "status": "admission_unknown"}
    records = await get_mcp_task_submitter().list_tasks(
        **scope.query(), limit=50, active_only=False
    )
    from .chat_sessions import checked_record

    found = next((r for r in records if r["id"] == tracking), None)
    if found is None:
        return {"known": False, "status": "admission_unknown"}
    checked_record(found, scope, tracking, (turn or {}).get("request_digest"))
    if (
        data["kind"] == "cancel"
        and not found.get("cancel_requested_at")
        and found["status"] not in {"completed", "failed", "cancelled"}
    ):
        return {"known": False, "status": "cancel_request_unconfirmed"}
    if turn:
        await asyncio.to_thread(saved.confirm, scope, call, found)
    result = found.get("result") or {}
    validation = result.get("validation") or {}
    verified = (
        found["status"] == "completed"
        and result.get("validation_status") == "passed"
        and type(validation.get("exit_code")) is int
        and validation["exit_code"] == 0
    )
    return {
        "known": True,
        "accepted": bool(found.get("cancel_requested_at")),
        "tracking_id": tracking,
        "thread_id": scope.thread_id,
        "incarnation": scope.incarnation,
        "status": found["status"],
        "verified": verified,
        "native_session": result.get("session_id", ""),
        "preview": str(result.get("summary", ""))[:2000],
        "handoff": (
            isinstance(result.get("work_report"), dict)
            and result["work_report"].get("version") == 1
            and result["work_report"].get("work_id") == op["parent"]
            and result["work_report"].get("operation_id") == op["id"]
            and result["work_report"].get("scope") == "out_of_scope"
        ),
    }


def install(registry, config):
    from deerflow_extension_api import BackendAction, PluginContribution

    if not registry.plugin(
        PluginContribution(
            namespace=NAMESPACE,
            title="Continuous secretary",
            enabled=True,
            backend=(BackendAction("perform", perform), BackendAction("query", query)),
        )
    ):
        raise RuntimeError("Pinned operation and AgentRuns contracts are required")


def cancel_tracking(saved, scope, op):
    from .store import digest

    target = op["data"].get("target_operation")
    if target:
        call = digest({"run": "continuous:" + target, "call": target})
        turn = saved.turn(scope, call)
        return (turn or {}).get("tracking_id")
    return op["data"].get("expected_head")
