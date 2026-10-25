import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .models import ACTIVE, Conflict, ResumeTask, State, SubmitTask, Task


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Store:
    """Single-process SQLite store; state changes and their events commit together."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, status TEXT NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS requests (
                key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, task_id TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
            CREATE TABLE IF NOT EXISTS events (
                cursor INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
            CREATE INDEX IF NOT EXISTS task_events ON events(task_id, cursor);
        """)
        self.db.execute(
            "INSERT OR IGNORE INTO metadata VALUES('instance_id', ?)", (uuid.uuid4().hex,)
        )
        value = self.db.execute("SELECT value FROM metadata WHERE key='instance_id'").fetchone()[0]
        try:
            if uuid.UUID(value).hex != value:
                raise ValueError("invalid instance identity")
        except (ValueError, AttributeError) as error:
            self.db.close()
            raise ValueError(
                "Worker instance identity is corrupt; restore its state explicitly"
            ) from error
        self.instance_id = value

    def close(self):
        self.db.close()

    def _existing(self, key: str, fingerprint: str) -> Task | None:
        row = self.db.execute("SELECT * FROM requests WHERE key=?", (key,)).fetchone()
        if row:
            if row["fingerprint"] != fingerprint:
                raise Conflict("idempotency key already used for a different request")
            return self.get(row["task_id"])
        return None

    def submit(self, request: SubmitTask, policy: dict | None = None) -> tuple[Task, bool]:
        fingerprint = digest({"operation": "submit", **request.model_dump()})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self._existing(request.idempotency_key, fingerprint)
            if previous:
                self.db.commit()
                return previous, False
            stamp = now()
            task = Task(
                task_id=uuid.uuid4().hex,
                project_id=request.project_id,
                prompt=request.prompt,
                status=State.QUEUED,
                created_at=stamp,
                updated_at=stamp,
                policy=policy or {},
            )
            self.db.execute(
                "INSERT INTO tasks VALUES(?,?,?,?)",
                (task.task_id, task.project_id, task.status, task.model_dump_json()),
            )
            self.db.execute(
                "INSERT INTO requests VALUES(?,?,?)",
                (request.idempotency_key, fingerprint, task.task_id),
            )
            self._event(task.task_id, "task.queued", {"attempt": 1})
            self.db.commit()
            return task, True
        except BaseException:
            self.db.rollback()
            raise

    def get(self, task_id: str) -> Task:
        row = self.db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        return Task.model_validate_json(row["data"])

    def list_tasks(self, limit: int = 100) -> list[Task]:
        rows = self.db.execute("SELECT data FROM tasks ORDER BY rowid DESC LIMIT ?", (limit,))
        return [Task.model_validate_json(row["data"]) for row in rows]

    def queued(self) -> list[Task]:
        return [
            Task.model_validate_json(r[0])
            for r in self.db.execute("SELECT data FROM tasks WHERE status='queued' ORDER BY rowid")
        ]

    def _event(self, task_id: str, kind: str, payload: dict):
        self.db.execute(
            "INSERT INTO events(task_id,type,payload,created_at) VALUES(?,?,?,?)",
            (task_id, kind, json.dumps(payload, ensure_ascii=False), now()),
        )

    def event(self, task_id: str, kind: str, payload: dict):
        self._event(task_id, kind, payload)

    def update(self, task_id: str, *, kind: str = "task.updated", **changes) -> Task:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            task = self.get(task_id).model_copy(update={**changes, "updated_at": now()})
            self.db.execute(
                "UPDATE tasks SET status=?,data=? WHERE id=?",
                (task.status, task.model_dump_json(), task_id),
            )
            self._event(task_id, kind, {"status": task.status, "attempt": task.attempt})
            self.db.commit()
            return task
        except BaseException:
            self.db.rollback()
            raise

    def resume(self, task_id: str, request: ResumeTask) -> Task:
        fingerprint = digest({"operation": "resume", "task_id": task_id, **request.model_dump()})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self._existing(request.idempotency_key, fingerprint)
            if previous:
                self.db.commit()
                return previous
            task = self.get(task_id)
            if task.status in ACTIVE or task.status == State.QUEUED:
                raise Conflict("task is already active; interrupt it or answer its pending input")
            if task.status == State.RECOVERY_REQUIRED and not request.confirm_recovery:
                raise Conflict(
                    "verify the old process has stopped, then confirm recovery explicitly"
                )
            if not task.session_id:
                raise Conflict("no native session was saved; create a new task explicitly")
            task = task.model_copy(
                update={
                    "status": State.QUEUED,
                    "prompt": request.message,
                    "attempt": task.attempt + 1,
                    "turn_id": None,
                    "result": None,
                    "error": None,
                    "updated_at": now(),
                }
            )
            self.db.execute(
                "UPDATE tasks SET status=?,data=? WHERE id=?",
                (task.status, task.model_dump_json(), task_id),
            )
            self.db.execute(
                "INSERT INTO requests VALUES(?,?,?)",
                (request.idempotency_key, fingerprint, task_id),
            )
            self._event(task_id, "task.resumed", {"attempt": task.attempt})
            self.db.commit()
            return task
        except BaseException:
            self.db.rollback()
            raise

    def recover(self):
        for task in self.list_tasks(limit=1_000_000):
            if task.status in ACTIVE:
                self.update(
                    task.task_id,
                    status=State.RECOVERY_REQUIRED,
                    kind="task.recovery_required",
                    error="Worker stopped during execution; outcome uncertain. "
                    "No replay performed.",
                )

    def events(self, task_id: str, after: int = 0, limit: int = 100) -> list[dict]:
        self.get(task_id)
        rows = self.db.execute(
            """SELECT * FROM events
            WHERE task_id=? AND cursor>? ORDER BY cursor LIMIT ?""",
            (task_id, after, limit),
        )
        return [
            {
                "cursor": r["cursor"],
                "type": r["type"],
                "payload": json.loads(r["payload"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
