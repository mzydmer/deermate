#!/usr/bin/env python3
"""Opt-in live Codex smoke check. Uses local Codex login and consumes model quota."""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from deermate.config import Project, Settings
from deermate.models import ACTIVE, ResumeTask, State, SubmitTask
from deermate.worker import Worker


async def await_state(worker, task_id, states):
    async with asyncio.timeout(200):
        while True:
            task = worker.store.get(task_id)
            if task.status in states:
                return task
            if task.status in {State.FAILED, State.RECOVERY_REQUIRED}:
                raise RuntimeError(task.error)
            await asyncio.sleep(0.1)


async def smoke(model: str | None, lifecycle: bool):
    with tempfile.TemporaryDirectory(prefix="deermate-smoke-") as folder:
        root = await asyncio.to_thread(Path(folder).resolve)
        repo = root / "repo"
        repo.mkdir()
        (repo / "answer.py").write_text("def add(a, b):\n    return a - b\n")
        (repo / "tests").mkdir()
        (repo / "tests/test_answer.py").write_text(
            "import unittest\nfrom answer import add\n"
            "class Addition(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
        )
        (repo / ".gitignore").write_text("__pycache__/\n")
        for args in [
            ["init", "-q"],
            ["add", "."],
            [
                "-c",
                "user.name=DeerMate smoke",
                "-c",
                "user.email=smoke@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
        ]:
            await asyncio.to_thread(subprocess.run, ["git", "-C", str(repo), *args], check=True)
        settings = Settings(
            state_dir=root / "state",
            model=model,
            task_timeout_seconds=180,
            projects={
                "demo": Project(
                    root=repo,
                    allow_write=True,
                    test_command=[
                        sys.executable,
                        "-m",
                        "unittest",
                        "discover",
                        "-s",
                        "tests",
                        "-v",
                    ],
                )
            },
        )
        worker = Worker(settings)
        await worker.start()
        try:
            task, _ = worker.store.submit(
                SubmitTask(
                    project_id="demo",
                    idempotency_key="live-1",
                    prompt="Fix only answer.py so add(a, b) returns a + b. Do not change tests. "
                    "Do not use network or external tools. Do not run tests: the worker will run "
                    "them separately. Make the one-line change and finish.",
                ),
                settings.policy("demo"),
            )
            prior = None
            async with asyncio.timeout(200):
                while True:
                    task = worker.store.get(task.task_id)
                    if task.status != prior:
                        print(f"state={task.status}", flush=True)
                        prior = task.status
                    if task.status not in ACTIVE | {State.QUEUED}:
                        break
                    await asyncio.sleep(0.2)
            print(
                json.dumps(
                    {"status": task.status, "error": task.error, "result": task.result},
                    ensure_ascii=False,
                    indent=2,
                ),
                flush=True,
            )
            if task.status != State.COMPLETED:
                raise RuntimeError("live smoke task did not meet configured validation")
            if lifecycle:
                session_id = task.session_id
                worker.store.resume(
                    task.task_id,
                    ResumeTask(
                        message="Read answer.py and summarize its current behavior. "
                        "Do not change files.",
                        idempotency_key="live-interrupt",
                    ),
                )
                await await_state(worker, task.task_id, {State.RUNNING})
                await worker.cancel(task.task_id)
                cancelled = await await_state(worker, task.task_id, {State.CANCELLED})
                assert cancelled.session_id == session_id
                worker.store.resume(
                    task.task_id,
                    ResumeTask(
                        message="Confirm that add implements addition and finish. "
                        "Do not change files or run tests; the worker will validate independently.",
                        idempotency_key="live-continue",
                    ),
                )
                resumed = await await_state(worker, task.task_id, {State.COMPLETED})
                assert resumed.session_id == session_id and resumed.attempt == 3
                print(
                    "Live interrupt/resume passed; native session identity preserved.", flush=True
                )
        finally:
            await worker.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="acknowledge this calls your logged-in Codex and consumes quota",
    )
    parser.add_argument("--model", help="optional model available to your Codex account")
    parser.add_argument(
        "--lifecycle",
        action="store_true",
        help="also verify a native interrupt and subsequent session continuation",
    )
    args = parser.parse_args()
    asyncio.run(smoke(args.model, args.lifecycle))
