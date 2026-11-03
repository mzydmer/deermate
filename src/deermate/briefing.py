"""Owned home actions over the pinned runtime; no new execution authority."""

import asyncio
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def database():
    from deerflow.config import get_app_config

    config = get_app_config().database
    if config.backend != "sqlite":
        raise PermissionError("Home actions require the pinned local SQLite profile")
    return Path(config.sqlite_path)


@contextmanager
def gate(owner):
    db = sqlite3.connect(database().resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN IMMEDIATE")
        user = db.execute("SELECT * FROM users WHERE id=?", (owner,)).fetchone()
        if not user or user["disabled"] or user["needs_setup"] or user["system_role"] != "admin":
            raise PermissionError("Current run permission is required")
        yield db, user
        db.commit()
    finally:
        db.rollback()
        db.close()


def topic_source(db, owner, topic_id):
    topic = db.execute(
        "SELECT * FROM deermate_attention_topics WHERE owner=? AND id=?", (owner, topic_id)
    ).fetchone()
    if not topic or topic["status"] != "active" or topic["snoozed_until"] > time.time():
        raise PermissionError("The attention topic is unavailable")
    thread = db.execute(
        "SELECT * FROM threads_meta WHERE thread_id=? AND user_id=?", (topic["thread_id"], owner)
    ).fetchone()
    if (
        not thread
        or not thread["incarnation"]
        or thread["incarnation"] != topic["incarnation"]
        or thread["project_id"]
        or topic["project_id"]
        or json.loads(thread["metadata_json"] or "{}").get("deerflow_archived")
    ):
        raise PermissionError("The source conversation changed")
    return topic


def evidence_version(db, topic):
    row = db.execute(
        "SELECT id,status,last_poll_error,cancel_requested_at,"
        "coalesce(json_extract(result,'$.validation_status')='passed' AND "
        "json_type(result,'$.validation.exit_code')='integer' AND "
        "json_extract(result,'$.validation.exit_code')=0,0) AS verified, "
        "coalesce(json_type(result,'$.validation.exit_code')='integer' AND "
        "json_extract(result,'$.validation.exit_code')!=0,0) AS failed "
        "FROM mcp_tasks WHERE thread_id=? AND user_id=? AND coalesce(thread_incarnation,'')=? "
        "ORDER BY created_at DESC,id DESC LIMIT 1",
        (topic["thread_id"], topic["owner"], topic["incarnation"]),
    ).fetchone()
    if row:
        # Actions are prepared only for an idle, non-stale terminal source.
        data = [
            "task",
            row["id"],
            "",
            row["status"],
            bool(row["verified"] and row["status"] == "completed"),
            bool(row["last_poll_error"]),
            row["cancel_requested_at"] is not None,
            False,
            bool(row["failed"]),
        ]
    else:
        row = db.execute(
            "SELECT run_id,status FROM runs WHERE thread_id=? AND user_id=? "
            "AND evidence_origin='interactive' AND origin_kind IS NULL "
            "ORDER BY created_at DESC,run_id DESC LIMIT 1",
            (topic["thread_id"], topic["owner"]),
        ).fetchone()
        data = [
            "conversation",
            "",
            row["run_id"] if row else "",
            row["status"] if row else "no_tasks",
            False,
            False,
            False,
            False,
            False,
        ]
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def validate(db, user, intent):
    if intent["user_version"] != user["token_version"]:
        raise PermissionError("The action authorization changed")
    if intent["topic_id"]:
        topic = topic_source(db, intent["owner"], intent["topic_id"])
        if (
            topic["revision"] != intent["topic_revision"]
            or evidence_version(db, topic) != intent["source_version"]
        ):
            raise PermissionError("The action evidence changed")
    elif intent["kind"] == "new_topic":
        profile = db.execute(
            "SELECT * FROM deermate_personal_profiles WHERE owner=?", (intent["owner"],)
        ).fetchone()
        fact = db.execute(
            "SELECT * FROM deermate_memory_refs WHERE owner=? AND id=?",
            (intent["owner"], intent["fact_id"]),
        ).fetchone()
        frame = json.loads(intent["context_json"])
        if (
            not profile
            or not profile["memory_enabled"]
            or not profile["proactive_enabled"]
            or profile["policy_revision"] != frame["policy_revision"]
            or not fact
            or fact["status"] != "active"
            or fact["scope"] != "personal"
            or fact["revision"] != intent["fact_revision"]
        ):
            raise PermissionError("The suggested goal is no longer available")
        from .memory import PersonalMemory

        sources = PersonalMemory._sources(db, intent["owner"], [fact["source_id"]])
        if sources.get(fact["source_id"]) is False:
            raise PermissionError("The suggested goal's source changed")
    else:
        raise PermissionError("Unsupported home action")


def load(owner, intent_id):
    with gate(owner) as (db, user):
        row = db.execute(
            "SELECT * FROM deermate_briefing_intents WHERE owner=? AND id=?", (owner, intent_id)
        ).fetchone()
        if not row or row["status"] not in {"submitting", "running", "uncertain", "completed"}:
            raise PermissionError("An admitted home action is required")
        validate(db, user, row)
        return dict(row)


async def describe(owner, topic_id, version):
    from deerflow.config import get_app_config
    from deerflow.mcp.tasks.runtime import get_mcp_task_submitter

    from .chat_sessions import ChatScope, checked_record
    from .conversation import select_parent
    from .session_middleware import DEFAULT_PROFILES, journal

    with gate(owner) as (db, _):
        topic = dict(topic_source(db, owner, topic_id))
        if evidence_version(db, topic) != version:
            raise PermissionError("The task evidence changed")
    scope = ChatScope(owner, topic["thread_id"], topic["incarnation"])
    binding = await asyncio.to_thread(journal().binding, scope)
    if (
        not binding
        or binding["pending"]
        or not binding["project"]
        or binding["executor"] != "codex"
        or binding["server"] not in DEFAULT_PROFILES
    ):
        raise PermissionError("No unambiguous existing coding session is available")
    server = get_app_config().extensions.mcp_servers.get(binding["server"])
    if not server or not server.enabled:
        raise PermissionError("The existing coding connection is disabled")
    records = await get_mcp_task_submitter().list_tasks(
        **scope.query(), limit=50, active_only=False
    )
    parent = checked_record(
        next((r for r in records if r["id"] == binding["head"]), None), scope, binding["head"]
    )
    select_parent([parent], parent["id"], user_id=owner, thread_id=scope.thread_id)
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                scope.key,
                binding["server"],
                binding["project"],
                binding["native"],
                parent["id"],
                parent.get("driver_data"),
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "project": binding["project"],
        "server": binding["server"],
        "executor": "codex",
        "head": parent["id"],
        "fingerprint": fingerprint,
    }


async def perform(payload, context):
    from .memory import _owner, runtime_memory

    owner = _owner(context)
    intent = await asyncio.to_thread(load, owner, payload.get("intent_id"))
    if intent["kind"] == "continue":
        from deerflow.mcp.tasks.models import TaskSubmitRequest
        from deerflow.mcp.tasks.runtime import get_mcp_task_submitter

        from .chat_sessions import ChatScope, ask_in_chat
        from .session_middleware import DEFAULT_PROFILES, journal

        expected = json.loads(intent["continuation_json"])
        current = await describe(owner, intent["topic_id"], intent["source_version"])
        if current != expected:
            raise PermissionError("The bound coding session changed")
        with gate(owner) as (db, _):
            topic = dict(topic_source(db, owner, intent["topic_id"]))
        result = await ask_in_chat(
            journal(),
            get_mcp_task_submitter(),
            TaskSubmitRequest,
            scope=ChatScope(owner, topic["thread_id"], topic["incarnation"]),
            profiles=DEFAULT_PROFILES,
            call_id=intent["id"],
            run_id="briefing:" + intent["id"],
            server=current["server"],
            message=intent["question"],
            explicit_task=current["head"],
        )
        return {"accepted": True, "tracking_id": result.get("tracking_id")}
    if context.agent_runs is None:
        raise PermissionError("Owned runtime admission is unavailable")
    if intent["kind"] == "new_topic":
        # Revalidate the canonical provider body as well as the Go reference.
        found = await asyncio.to_thread(runtime_memory().read, owner, [intent["fact_id"]])
        if len(found["items"]) != 1 or found["items"][0]["revision"] != intent["fact_revision"]:
            raise PermissionError("The canonical goal changed")
        await context.agent_runs.create_thread(thread_id=intent["thread_id"])
    run = await context.agent_runs.start(
        thread_id=intent["thread_id"],
        input={
            "messages": [
                {
                    "type": "human",
                    "id": "briefing-" + intent["id"],
                    "content": intent["question"],
                    "additional_kwargs": {
                        "deermate_briefing_intent": intent["id"],
                        "deermate_briefing_token": intent["admission_token"],
                    },
                }
            ]
        },
        idempotency_key=intent["id"],
    )
    return {"accepted": True, "run_id": run.run_id, "thread_id": run.thread_id}


async def describe_action(payload, context):
    from .memory import _owner

    return await describe(_owner(context), payload.get("topic_id"), payload.get("source_version"))


def install(registry, config):
    from deerflow_extension_api import BackendAction, PluginContribution

    if not registry.plugin(
        PluginContribution(
            namespace="deermate.briefing",
            title="Personal home",
            enabled=True,
            backend=(BackendAction("perform", perform), BackendAction("describe", describe_action)),
        )
    ):
        raise RuntimeError("Pinned home-action plugin support is required")
