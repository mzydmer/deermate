"""Narrow, identity-preserving operations over the pinned DeerFlow runtime.

Go owns admissions. This adapter never chooses a host/project, retries a submit,
changes a native root, or runs a second coding model.
"""

import asyncio
import hashlib
import hmac
import json
import time

from . import telemetry
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


def check_background(db, owner, data):
    # Interactive admissions come from Go's default desk. Only source/automatic
    # work depends on the legacy background pause; never resume it implicitly.
    if (
        data.get("automatic")
        or data.get("kind") == "assessor"
        or data.get("origin") in {"event", "assessment"}
    ):
        settings = record(db, owner, "settings", "settings")
        if not settings["data"].get("enabled"):
            raise PermissionError("Background work is paused")


def load(owner, payload, *, writing=False):
    with gate(owner) as (db, user):
        op = record(db, owner, "operation", payload.get("operation_id"))
        data = op["data"]
        if (
            (writing and data.get("_user_version") != user["token_version"])
            or not isinstance(payload.get("nonce"), str)
            or not hmac.compare_digest(payload["nonce"], data.get("_nonce", ""))
            or op["state"] not in {"dispatching", "acknowledged", "uncertain", "settled"}
        ):
            raise PermissionError("A current canonical admission is required")
        if writing:
            if op["state"] != "dispatching":
                raise PermissionError("This operation may only be reconciled")
            check_background(db, owner, data)
            if data["kind"] in {"execute", "followup", "cancel"}:
                validate_native(db, owner, op)
            elif data["kind"] == "assessor":
                event = record(db, owner, "event", data["event_id"])
                rule = record(db, owner, "rule", data["rule_id"])
                source = record(db, owner, "source", event["data"]["source_id"])
                for ref in data.get("event_batch") or []:
                    item = record(db, owner, "event", ref["id"])
                    latest = db.execute(
                        "SELECT record FROM deermate_work_keys WHERE owner=? "
                        "AND kind='github_object' AND key=?",
                        (owner, item["data"].get("object_key", "")),
                    ).fetchone()
                    if (
                        item["revision"] != ref["revision"]
                        or not latest
                        or latest[0] != item["id"]
                        or item["data"]["source_generation"] != data["source_generation"]
                        or item["data"]["thread_key"] != event["data"]["thread_key"]
                    ):
                        raise PermissionError("The assessment batch changed")
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
    canonical = await asyncio.to_thread(load, owner, payload)
    saved = await asyncio.to_thread(rejected_receipt, owner, canonical["id"])
    if saved is not None:
        return saved
    from .runtime_telemetry import operation_parent

    with telemetry.span(
        "agent.operation",
        parent=operation_parent(canonical),
        refs={
            "operation_id": canonical["id"],
            "work_id": canonical["parent"],
            "conversation_id": canonical["data"].get("thread_id", ""),
        },
        attributes={"deermate.kind": canonical["data"]["kind"]},
    ):
        result = await _perform(payload, context)
    if result.get("status") == "rejected":
        await asyncio.to_thread(save_rejection, owner, canonical["id"], result)
    return result


async def _perform(payload, context):
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
    try:
        op = await asyncio.to_thread(load, owner, payload, writing=True)
    except PermissionError:
        return {
            "known": True,
            "accepted": False,
            "status": "rejected",
            "preview": "Authority changed before run/native admission",
        }
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

    saved = journal()
    try:
        scope = await asyncio.to_thread(thread_scope, owner, op)
        root_task_name = await asyncio.to_thread(native_profile, owner, data["server"])
        binding = await asyncio.to_thread(saved.binding, scope)
        if data["kind"] != "cancel" and (binding or {}).get("head", "") != data["expected_head"]:
            if (
                binding
                and not binding["pending"]
                and binding["server"] == data["server"]
                and binding["project"] == data["project"]
                and binding["executor"] == "codex"
            ):
                return {
                    "known": True,
                    "accepted": False,
                    "status": "rejected",
                    "current_head": binding["head"],
                    "thread_id": scope.thread_id,
                    "incarnation": scope.incarnation,
                    "preview": (
                        "Another round changed this chat's head. The same binding was "
                        "reconciled; send an explicit follow-up again."
                    ),
                }
            raise PermissionError("The coding head changed")
    except PermissionError:
        return {
            "known": True,
            "accepted": False,
            "status": "rejected",
            "preview": "The execution conversation, head or coding connection changed",
        }
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
        message=work_prompt(
            op["parent"],
            op["id"],
            data["project"],
            data["message"],
            {
                "grant_id": data["grant_id"],
                "version": data["grant_version"],
                "instance_id": data["instance_id"],
            },
        ),
        project=data["project"],
        explicit_task=data["expected_head"] or None,
        root_task_name=root_task_name,
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
    rejected = await asyncio.to_thread(rejected_receipt, owner, op["id"])
    if rejected is not None:
        return rejected
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
        host_model_revision = None
        try:
            evidence = await context.agent_runs.configuration_evidence(
                thread_id=data["thread_id"], run_id=run.run_id
            )
            host_model_revision = evidence.get("model_version")
        except Exception:
            pass  # Optional evidence is unavailable, never represented as zero usage.
        return {
            "known": True,
            "host_model_revision": host_model_revision,
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


async def capabilities(payload, context):
    from .continuous_middleware import bounded_model
    from .memory import _owner

    owner = _owner(context)
    with gate(owner):
        pass
    try:
        bounded_model(payload.get("model"))
    except Exception:
        return {"contract_version": 1, "bounded": False}
    return {
        "contract_version": 1,
        "bounded": True,
        "output_tokens": 1024,
        "max_retries": 0,
        "model_calls_per_operation": 1,
    }


def install(registry, config):
    from deerflow_extension_api import BackendAction, PluginContribution

    if not registry.plugin(
        PluginContribution(
            namespace=NAMESPACE,
            title="Continuous secretary",
            enabled=True,
            backend=(
                BackendAction("perform", perform),
                BackendAction("query", query),
                BackendAction("capabilities", capabilities),
            ),
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


def native_profile(owner, server):
    from deerflow.config import get_app_config

    config = get_app_config().extensions.mcp_servers.get(server)
    if config is None or not config.enabled:
        raise PermissionError("The existing coding connection is disabled")
    starts = [
        item
        for item in config.task_toolsets
        if (item.submit_tool, item.status_tool, item.cancel_tool)
        == ("submit_task", "get_task_status", "cancel_task")
    ]
    follows = [
        item
        for item in config.task_toolsets
        if (item.submit_tool, item.status_tool, item.cancel_tool)
        == ("continue_task", "get_continuation_status", "cancel_continuation_task")
    ]
    if len(starts) != 1 or len(follows) != 1:
        raise PermissionError("Both existing ordinary task lifecycle contracts are required")
    if "--relay-config" in getattr(config, "args", []):
        from deerflow.config.paths import get_paths

        from .authorization import private_json

        snapshot = private_json(get_paths().base_dir / "agent-authorizations/bridge.json")
        if snapshot.get("owner_id") != owner:
            raise PermissionError("The configured connector belongs to another owner")
    return starts[0].name


def rejected_receipt(owner, identifier):
    import sqlite3

    with gate(owner) as (db, _):
        try:
            row = db.execute(
                "SELECT response FROM deermate_continuous_receipts WHERE owner=? AND operation=?",
                (owner, identifier),
            ).fetchone()
        except sqlite3.OperationalError as error:
            if "no such table" not in str(error):
                raise
            return None
        return json.loads(row[0]) if row else None


def save_rejection(owner, identifier, response):
    with gate(owner) as (db, _):
        db.execute(
            "CREATE TABLE IF NOT EXISTS deermate_continuous_receipts("
            "owner TEXT NOT NULL,operation TEXT NOT NULL,response TEXT NOT NULL,"
            "PRIMARY KEY(owner,operation))"
        )
        db.execute(
            "INSERT OR IGNORE INTO deermate_continuous_receipts VALUES(?,?,?)",
            (owner, identifier, json.dumps(response)),
        )
