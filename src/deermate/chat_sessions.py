"""Durable single-coding-session admission, independent of the DeerFlow runtime."""

import asyncio
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .conversation import HISTORY_LIMIT, ConversationError, select_parent
from .models import ContinueTask, SubmitTask
from .store import digest


class SessionUnknown(ConversationError):
    pass


@dataclass(frozen=True)
class ChatScope:
    user_id: str
    thread_id: str
    incarnation: str | None

    @property
    def key(self):
        if not all(isinstance(v, str) and v for v in (self.user_id, self.thread_id)) or (
            self.incarnation is not None
            and (not isinstance(self.incarnation, str) or not self.incarnation)
        ):
            raise ConversationError("Authenticated chat incarnation is required.")
        return digest(vars(self))

    def query(self):
        return {
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "thread_incarnation": self.incarnation,
        }


class SessionJournal:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS bindings (
                    scope TEXT PRIMARY KEY, user_id TEXT NOT NULL, thread_id TEXT NOT NULL,
                    incarnation TEXT, executor TEXT NOT NULL, server TEXT NOT NULL,
                    project TEXT, head TEXT, native TEXT, round INTEGER NOT NULL DEFAULT 0,
                    pending TEXT, UNIQUE(executor,native)
                );
                CREATE TABLE IF NOT EXISTS turns (
                    scope TEXT NOT NULL REFERENCES bindings(scope), call_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL, tracking_id TEXT NOT NULL UNIQUE,
                    confirmed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(scope,call_id)
                );
            """)
        path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
        finally:
            db.close()

    def binding(self, scope):
        with self.db() as db:
            row = db.execute("SELECT * FROM bindings WHERE scope=?", (scope.key,)).fetchone()
            return dict(row) if row else None

    def turn(self, scope, call):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM turns WHERE scope=? AND call_id=?", (scope.key, call)
            ).fetchone()
            return dict(row) if row else None

    def owned_binding(self, key, user_id, thread_id):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM bindings WHERE scope=? AND user_id=? AND thread_id=?",
                (key, user_id, thread_id),
            ).fetchone()
            return dict(row) if row else None

    def reserve(self, scope, call, fingerprint, *, executor, server, project, expected, seed):
        if executor not in {"codex", "claude"}:
            raise ConversationError("Unsupported coding executor.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM bindings WHERE scope=?", (scope.key,)).fetchone()
            if current is None:
                db.execute(
                    "INSERT INTO bindings VALUES(?,?,?,?,?,?,?,?,?,?,NULL)",
                    (
                        scope.key,
                        scope.user_id,
                        scope.thread_id,
                        scope.incarnation,
                        executor,
                        server,
                        project,
                        seed.get("head"),
                        seed.get("native"),
                        seed.get("round", 0),
                    ),
                )
                current = db.execute(
                    "SELECT * FROM bindings WHERE scope=?", (scope.key,)
                ).fetchone()
            if current["pending"]:
                raise SessionUnknown(
                    "A coding admission is pending; reconcile it before continuing."
                )
            if (current["executor"], current["server"], current["project"], current["head"]) != (
                executor,
                server,
                project,
                expected,
            ):
                raise ConversationError("Chat binding changed; refresh its latest task.")
            tracking = "mcp-task-" + digest({"scope": scope.key, "call": call})[:32]
            db.execute(
                "INSERT INTO turns VALUES(?,?,?,?,0)", (scope.key, call, fingerprint, tracking)
            )
            db.execute("UPDATE bindings SET pending=? WHERE scope=?", (call, scope.key))
            db.commit()
            return tracking

    def confirm(self, scope, call, record):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            turn = db.execute(
                "SELECT * FROM turns WHERE scope=? AND call_id=?", (scope.key, call)
            ).fetchone()
            binding = db.execute("SELECT * FROM bindings WHERE scope=?", (scope.key,)).fetchone()
            if not turn or record["id"] != turn["tracking_id"]:
                raise SessionUnknown("Tracked coding admission does not match its saved intent.")
            if turn["confirmed"]:
                return
            if binding["pending"] != call:
                raise SessionUnknown("Coding admission lost its reservation; inspect task state.")
            native = (record.get("result") or {}).get("session_id")
            if native and binding["native"] and native != binding["native"]:
                raise SessionUnknown("Executor session changed unexpectedly; do not replace it.")
            db.execute(
                "UPDATE bindings SET head=?,native=COALESCE(?,native),"
                "round=round+1,pending=NULL WHERE scope=?",
                (record["id"], native, scope.key),
            )
            db.execute(
                "UPDATE turns SET confirmed=1 WHERE scope=? AND call_id=?", (scope.key, call)
            )
            db.commit()

    def observe(self, scope, head):
        native = (head.get("result") or {}).get("session_id")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM bindings WHERE scope=?", (scope.key,)).fetchone()
            if row and row["head"] == head["id"]:
                if row["native"] and native and row["native"] != native:
                    raise SessionUnknown("Executor session changed unexpectedly; inspect the task.")
                if native:
                    db.execute("UPDATE bindings SET native=? WHERE scope=?", (native, scope.key))
            db.commit()


def coding_records(records, scope, profiles):
    return [
        r
        for r in records
        if r.get("user_id") == scope.user_id
        and r.get("thread_id") == scope.thread_id
        and r.get("server_name") in profiles
        and r.get("driver_name") == "ordinary-tools"
        and (r.get("driver_data") or {}).get("submit_tool") in {"submit_task", "continue_task"}
    ]


def checked_record(record, scope, tracking, fingerprint=None):
    if not record or (record.get("user_id"), record.get("thread_id"), record.get("id")) != (
        scope.user_id,
        scope.thread_id,
        tracking,
    ):
        raise SessionUnknown("Saved coding task is unavailable in this chat; do not resubmit.")
    if "_thread_incarnation" in record and record["_thread_incarnation"] != scope.incarnation:
        raise SessionUnknown("Saved coding task belongs to another chat incarnation.")
    marker = (record.get("driver_data") or {}).get("deermate_session") or {}
    if fingerprint is not None and marker != {"scope": scope.key, "request": fingerprint}:
        raise SessionUnknown("Coding task identity differs from the saved admission.")
    return record


def response(binding, record, *, reconciled=False):
    return {
        "task_id": record["id"],
        "status": record["status"],
        "binding_id": binding["scope"],
        "executor": binding["executor"],
        "conversation_round": binding["round"],
        "reconciled": reconciled,
        "message": "This chat keeps one coding session. Follow-ups use the same native "
        "session and workspace; start a new chat to change executor or project.",
    }


async def ask_in_chat(
    journal,
    submitter,
    request_factory,
    *,
    scope,
    profiles,
    call_id,
    run_id,
    server,
    message,
    project=None,
    explicit_task=None,
    remote_parent=None,
    root_task_name="coding-session",
):
    scope_key = scope.key  # Validate identity before any admission or runtime lookup.
    if not all(isinstance(v, str) and v for v in (call_id, run_id)) or server not in profiles:
        raise ConversationError(
            "A registered coding tool and host tool-call identity are required."
        )
    operation = digest({"run": run_id, "call": call_id})
    fingerprint = digest(
        {
            "server": server,
            "message": message,
            "project": project,
            "explicit_task": explicit_task,
            "remote_parent": remote_parent,
        }
    )
    records = await submitter.list_tasks(**scope.query(), limit=HISTORY_LIMIT, active_only=False)
    previous = await asyncio.to_thread(journal.turn, scope, operation)
    if previous:
        if previous["request_digest"] != fingerprint:
            raise ConversationError("Tool-call identity conflicts with its saved coding request.")
        record = checked_record(
            next((r for r in records if r["id"] == previous["tracking_id"]), None),
            scope,
            previous["tracking_id"],
            fingerprint,
        )
        await asyncio.to_thread(journal.confirm, scope, operation, record)
        return response(await asyncio.to_thread(journal.binding, scope), record, reconciled=True)

    binding = await asyncio.to_thread(journal.binding, scope)
    legacy = coding_records(records, scope, profiles)
    parent, seed = None, {}
    executor = profiles[server]
    if binding:
        if binding["pending"]:
            raise SessionUnknown("A previous coding admission is unconfirmed; inspect it first.")
        if (binding["server"], binding["executor"]) != (server, executor):
            raise ConversationError("This chat already has an executor. Use a new chat to switch.")
        identities = {
            (r["server_name"], (r.get("result") or {}).get("session_id"))
            for r in legacy
            if (r.get("result") or {}).get("session_id")
        }
        if len(identities) > 1 or any(s != server for s, _ in identities):
            raise SessionUnknown(
                "Several executor sessions exist in this chat; inspect its history."
            )
        if project is not None and binding["project"] != project:
            raise ConversationError(
                "This chat is bound to another or legacy project. "
                "Use its continuation tool or start a new chat."
            )
        parent = checked_record(
            next((r for r in records if r["id"] == binding["head"]), None), scope, binding["head"]
        )
        await asyncio.to_thread(journal.observe, scope, parent)
        parent = select_parent(
            [parent], parent["id"], user_id=scope.user_id, thread_id=scope.thread_id
        )
        project = binding["project"]
    elif legacy:
        if len(records) >= HISTORY_LIMIT:
            raise ConversationError("Legacy history is incomplete; do not create another session.")
        parent = select_parent(legacy, None, user_id=scope.user_id, thread_id=scope.thread_id)
        if parent["server_name"] != server:
            raise ConversationError("Use the existing chat's executor or start a new chat.")
        if project is not None:
            raise ConversationError("Legacy project is unconfirmed. Use continue_codex first.")
        seed = {
            "head": parent["id"],
            "native": parent["result"]["session_id"],
            "round": parent["result"].get("conversation_round", len(legacy)),
        }
    elif len(records) >= HISTORY_LIMIT:
        raise ConversationError(
            "Chat history is incomplete; cannot prove no coding session exists."
        )

    if explicit_task is not None and (parent is None or explicit_task != parent["id"]):
        raise ConversationError("Only the latest bound task in this chat may continue.")
    if remote_parent is not None and (parent is None or remote_parent != parent["remote_task_id"]):
        raise ConversationError("The supplied native task is not this chat's current bound task.")
    key = "chat-session-" + digest({"scope": scope_key, "call": operation})
    if parent:
        body = ContinueTask(message=message, idempotency_key=key)
        arguments = {"task_id": parent["remote_task_id"], **body.model_dump()}
        data = {
            **parent["driver_data"],
            "submit_tool": "continue_task",
            "status_tool": "get_continuation_status",
            "cancel_tool": "cancel_continuation_task",
        }
        task_name = parent["task_name"]
    else:
        if project is None:
            raise ConversationError("No coding session yet; submit a registered project first.")
        body = SubmitTask(project_id=project, prompt=message, idempotency_key=key)
        arguments = body.model_dump()
        data = {
            "submit_tool": "submit_task",
            "status_tool": "get_task_status",
            "cancel_tool": "cancel_task",
            "connection_scope": "deployment",
        }
        task_name = root_task_name
    data["deermate_session"] = {"scope": scope.key, "request": fingerprint}
    tracking = await asyncio.to_thread(
        journal.reserve,
        scope,
        operation,
        fingerprint,
        executor=executor,
        server=server,
        project=project,
        expected=parent["id"] if parent else None,
        seed=seed,
    )
    # No retries: an exception/cancellation after this reservation is an uncertain admission.
    try:
        created = await submitter.submit(
            driver_name="ordinary-tools",
            request=request_factory(
                **scope.query(),
                tool_call_id=call_id,
                run_id=run_id,
                server_name=server,
                task_name=task_name,
                arguments=arguments,
                driver_data=data,
                local_task_id=tracking,
            ),
        )
        checked_record(created, scope, tracking, fingerprint)
        await asyncio.to_thread(journal.confirm, scope, operation, created)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        raise SessionUnknown(
            "Coding admission could not be confirmed. Inspect the tracked task; "
            "do not submit another session or replay the request."
        ) from error
    return response(await asyncio.to_thread(journal.binding, scope), created)


def title_from_messages(messages):
    for message in messages:
        kind = (
            message.get("role", message.get("type"))
            if isinstance(message, dict)
            else getattr(message, "type", None)
        )
        if kind not in {"user", "human"}:
            continue
        content = message.get("content", "") if isinstance(message, dict) else message.content
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and isinstance(p.get("text"), str)
            )
        if not isinstance(content, str):
            content = ""
        content = re.sub(r"[\x00-\x1f\x7f]", " ", content)
        content = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", content)
        content = re.sub(r"\s+", " ", content).strip(" #*`-_")
        content = re.sub(r"^(?:请帮我|麻烦帮我|帮我|请你|麻烦你|请)\s*", "", content)
        content = re.split(r"[。！？!?]|\.(?:\s|$)", content, maxsplit=1)[0].strip()
        return (content[:32] + ("…" if len(content) > 32 else "")) if content else "附件会话"
    return None
