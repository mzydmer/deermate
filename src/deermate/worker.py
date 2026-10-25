import asyncio
import contextlib
import fcntl
import os
from pathlib import Path

from .codex import CodexAdapter
from .config import Settings
from .models import ACTIVE, Conflict, State
from .rpc import RpcError
from .store import Store
from .workspace import collect, prepare


class Worker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(settings.state_dir, 0o700)
        self.lock = (settings.state_dir / "worker.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.lock.close()
            raise RuntimeError("another worker owns this state directory") from error
        self.store = Store(settings.state_dir / "tasks.sqlite3")
        self.running: dict[str, asyncio.Task] = {}
        self.adapters: dict[str, CodexAdapter] = {}
        self.validating: set[str] = set()
        self.loop_task: asyncio.Task | None = None
        self.stopping = False

    async def start(self):
        self.store.recover()
        self.loop_task = asyncio.create_task(self._dispatch())

    async def _dispatch(self):
        while not self.stopping:
            busy = {self.store.get(tid).project_id for tid in self.running}
            for task in self.store.queued():
                if len(self.running) >= self.settings.max_concurrent_tasks:
                    break
                if task.project_id in busy:
                    continue
                busy.add(task.project_id)
                self.store.update(task.task_id, status=State.STARTING)
                job = asyncio.create_task(self._execute(task.task_id))
                self.running[task.task_id] = job
                job.add_done_callback(lambda _, tid=task.task_id: self.running.pop(tid, None))
            await asyncio.sleep(0.05)

    async def _record(self, task_id: str, kind: str, payload: dict):
        changes = {}
        if kind == "session.ready":
            changes = {"session_id": payload["session_id"]}
        elif kind == "turn.ready":
            changes = {"turn_id": payload["turn_id"]}
        elif kind == "input.required":
            changes = {"status": State.INPUT_REQUIRED}
        if changes:
            self.store.update(task_id, kind=kind, **changes)
        self.store.event(task_id, kind + ".detail", payload)

    async def _execute(self, task_id: str):
        adapter = None
        try:
            task = self.store.get(task_id)
            if task.policy != self.settings.policy(task.project_id):
                raise Conflict(
                    "project or runtime policy changed since admission; submit a new task"
                )
            project = self.settings.projects[task.project_id]
            if not task.workspace:
                workspace = self.settings.state_dir / "workspaces" / task_id
                base = await prepare(project.root, workspace)
                task = self.store.update(task_id, workspace=str(workspace), base_commit=base)
            elif not await asyncio.to_thread(workspace_is_valid, Path(task.workspace)):
                raise Conflict("saved workspace is missing or was replaced")
            if self.store.get(task_id).status == State.CANCELLING:
                self.store.update(task_id, status=State.CANCELLED)
                return
            adapter = CodexAdapter(
                self.settings, task, lambda kind, payload: self._record(task_id, kind, payload)
            )
            self.adapters[task_id] = adapter
            async with asyncio.timeout(self.settings.task_timeout_seconds):
                await adapter.start()
                if self.store.get(task_id).status == State.CANCELLING:
                    await adapter.interrupt()
                else:
                    self.store.update(task_id, status=State.RUNNING)
                outcome = await adapter.run()
                if outcome == "interrupted":
                    self.store.update(task_id, status=State.CANCELLED, kind="task.cancelled")
                    return
                # Native completion must win a race with an unacknowledged cancel honestly.
                if self.store.get(task_id).status == State.CANCELLING:
                    self.store.event(task_id, "cancel.too_late", {})
                    self.store.update(
                        task_id,
                        status=State.NEEDS_REVIEW,
                        error="Native turn finished before interruption; "
                        "validation was not started.",
                    )
                    return
                self.validating.add(task_id)
                receipt = (
                    await adapter.validate(project.test_command) if project.test_command else None
                )
                patch = await collect(Path(task.workspace), task.base_commit)
                result = {
                    "summary": adapter.summary,
                    "validation": receipt,
                    "validation_status": "not_run"
                    if receipt is None
                    else "passed"
                    if receipt["exit_code"] == 0
                    else "failed",
                    "diff": patch,
                    "attempt": task.attempt,
                    "acceptance": "Configured command exit status; not a correctness guarantee.",
                }
                state = (
                    State.NEEDS_REVIEW
                    if receipt is None or adapter.policy_denied
                    else State.COMPLETED
                    if receipt["exit_code"] == 0
                    else State.FAILED
                )
                self.store.update(task_id, status=state, result=result, kind="task.finished")
        except asyncio.CancelledError:
            if adapter:
                await adapter.close()
                adapter = None
            requested = self.store.get(task_id).status == State.CANCELLING and not self.stopping
            self.store.update(
                task_id,
                status=State.CANCELLED if requested else State.RECOVERY_REQUIRED,
                error="Validation interrupted; owned process stopped."
                if requested
                else "Worker shutdown interrupted execution; verify before continuing.",
            )
            raise
        except TimeoutError:
            # Closing the owned app-server below prevents unattended continued work.
            self.store.update(task_id, status=State.FAILED, error="task deadline exceeded")
        except (RpcError, OSError, ValueError, KeyError, RuntimeError) as error:
            self.store.update(task_id, status=State.FAILED, error=str(error)[:2000])
        except Exception as error:
            # A malformed adapter payload or internal bug must not strand an active task.
            self.store.update(
                task_id,
                status=State.FAILED,
                error=f"{type(error).__name__}: {str(error)[:1800]}",
                kind="task.internal_error",
            )
        finally:
            if adapter:
                await adapter.close()
            self.adapters.pop(task_id, None)
            self.validating.discard(task_id)

    async def cancel(self, task_id: str):
        task = self.store.get(task_id)
        if task.status == State.QUEUED:
            return self.store.update(task_id, status=State.CANCELLED)
        if task.status not in ACTIVE:
            return task
        self.store.update(task_id, status=State.CANCELLING, kind="cancel.requested")
        if task_id in self.validating:
            self.running[task_id].cancel()
            return self.store.get(task_id)
        adapter = self.adapters.get(task_id)
        if adapter and adapter.turn_id:
            try:
                await adapter.interrupt()
            except (RpcError, TimeoutError, OSError):
                self.store.event(task_id, "cancel.unconfirmed", {})
        return self.store.get(task_id)

    async def answer(self, task_id: str, answers: dict[str, list[str]]):
        if task_id not in self.adapters:
            raise Conflict("no live adapter; recovery may be required")
        await self.adapters[task_id].answer(answers)
        return self.store.update(task_id, status=State.RUNNING, kind="input.answered")

    async def close(self):
        self.stopping = True
        if self.loop_task:
            self.loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.loop_task
        jobs = list(self.running.values())
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        self.store.close()
        self.lock.close()


def workspace_is_valid(path: Path) -> bool:
    return not path.is_symlink() and path.is_dir()
