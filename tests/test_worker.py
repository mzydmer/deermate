import asyncio
import json
import sys

import pytest

from deermate.models import ResumeTask, State, SubmitTask
from deermate.worker import Worker


async def wait_for(worker, task_id, states):
    async with asyncio.timeout(10):
        while True:
            task = worker.store.get(task_id)
            if task.status in states:
                return task
            await asyncio.sleep(0.02)


def submit(worker, prompt="fix", key="first"):
    return worker.store.submit(
        SubmitTask(project_id="demo", prompt=prompt, idempotency_key=key),
        worker.settings.policy("demo"),
    )[0]


async def test_patch_and_configured_test_receipt(settings):
    worker = Worker(settings)
    await worker.start()
    try:
        task = submit(worker)
        result = await wait_for(worker, task.task_id, {State.COMPLETED, State.FAILED})
        assert result.status == State.COMPLETED, result.error
        assert result.result["validation"]["exit_code"] == 0
        assert "Ran 1 test" in result.result["validation"]["stderr"]
        assert "return a + b" in result.result["diff"]
        assert "notes.txt" in result.result["diff"]  # includes untracked files
        assert "return a - b" in (settings.projects["demo"].root / "answer.py").read_text()
        assert result.session_id and result.turn_id
        events = worker.store.events(task.task_id)
        assert all(a["cursor"] < b["cursor"] for a, b in zip(events, events[1:], strict=False))
    finally:
        await worker.close()


async def test_test_failure_is_not_success(settings):
    worker = Worker(settings)
    await worker.start()
    try:
        task = submit(worker, "bad-fix")
        result = await wait_for(worker, task.task_id, {State.COMPLETED, State.FAILED})
        assert result.status == State.FAILED
        assert result.result["validation_status"] == "failed"
        assert "AssertionError" in result.result["validation"]["stderr"]
    finally:
        await worker.close()


async def test_missing_validator_requires_review(settings):
    settings.projects["demo"].test_command = None
    worker = Worker(settings)
    await worker.start()
    try:
        task = submit(worker)
        result = await wait_for(worker, task.task_id, {State.NEEDS_REVIEW, State.FAILED})
        assert result.status == State.NEEDS_REVIEW, result.error
        assert result.result["validation_status"] == "not_run"
    finally:
        await worker.close()


async def test_cancel_then_resume_uses_same_session(settings):
    worker = Worker(settings)
    await worker.start()
    try:
        task = submit(worker, "slow")
        running = await wait_for(worker, task.task_id, {State.RUNNING})
        await worker.cancel(task.task_id)
        cancelled = await wait_for(worker, task.task_id, {State.CANCELLED})
        assert cancelled.session_id == running.session_id
        worker.store.resume(task.task_id, ResumeTask(message="fix", idempotency_key="resume"))
        result = await wait_for(worker, task.task_id, {State.COMPLETED, State.FAILED})
        assert result.status == State.COMPLETED, result.error
        assert result.session_id == running.session_id and result.attempt == 2
        trace = [
            json.loads(x)
            for x in (settings.state_dir.parent / "native/trace.jsonl").read_text().splitlines()
        ]
        assert len([x for x in trace if x.get("method") == "thread/start"]) == 1
        assert len([x for x in trace if x.get("method") == "thread/resume"]) == 1
        assert len([x for x in trace if x.get("method") == "turn/start"]) == 2
        turns = [x for x in trace if x.get("method") == "turn/start"]
        assert all(x["params"]["sandboxPolicy"]["networkAccess"] is False for x in turns)
    finally:
        await worker.close()


async def test_input_required_can_be_answered(settings):
    worker = Worker(settings)
    await worker.start()
    try:
        task = submit(worker, "question then fix")
        await wait_for(worker, task.task_id, {State.INPUT_REQUIRED})
        await worker.answer(task.task_id, {"choice": ["yes"]})
        result = await wait_for(worker, task.task_id, {State.COMPLETED, State.FAILED})
        assert result.status == State.COMPLETED, result.error
    finally:
        await worker.close()


async def test_restart_preserves_task_and_requires_explicit_recovery(settings):
    worker = Worker(settings)
    await worker.start()
    task = submit(worker, "slow")
    running = await wait_for(worker, task.task_id, {State.RUNNING})
    await worker.close()
    worker = Worker(settings)
    await worker.start()
    try:
        saved = worker.store.get(task.task_id)
        assert saved.session_id == running.session_id
        assert saved.status == State.RECOVERY_REQUIRED
        assert not worker.store.queued()
        worker.store.resume(
            task.task_id,
            ResumeTask(message="fix", idempotency_key="recover", confirm_recovery=True),
        )
        result = await wait_for(worker, task.task_id, {State.COMPLETED, State.FAILED})
        assert result.status == State.COMPLETED, result.error
        assert result.session_id == saved.session_id
    finally:
        await worker.close()


async def test_single_owner_and_queued_cancel(settings):
    worker = Worker(settings)
    try:
        with pytest.raises(RuntimeError, match="another worker"):
            Worker(settings)
        task = submit(worker)
        result = await worker.cancel(task.task_id)
        assert result.status == State.CANCELLED and result.session_id is None
    finally:
        await worker.close()


async def test_changed_policy_rejected(settings):
    worker = Worker(settings)
    task = submit(worker)
    settings.projects["demo"].allow_write = False
    await worker.start()
    try:
        result = await wait_for(worker, task.task_id, {State.FAILED})
        assert "policy changed" in result.error and result.session_id is None
    finally:
        await worker.close()


async def test_permission_escalation_is_denied_and_needs_review(settings):
    worker = Worker(settings)
    await worker.start()
    try:
        task = submit(worker, "approval then fix")
        result = await wait_for(worker, task.task_id, {State.NEEDS_REVIEW, State.FAILED})
        assert result.status == State.NEEDS_REVIEW, result.error
        trace = [
            json.loads(line)
            for line in (settings.state_dir.parent / "native/trace.jsonl").read_text().splitlines()
        ]
        denial = next(row for row in trace if row.get("id") == 999)
        assert denial["result"]["decision"] == "decline"
    finally:
        await worker.close()


async def test_cancellation_stops_validation_process(settings):
    settings.projects["demo"].test_command = [sys.executable, "-c", "import time;time.sleep(30)"]
    worker = Worker(settings)
    await worker.start()
    try:
        task = submit(worker)
        async with asyncio.timeout(5):
            while task.task_id not in worker.validating:  # noqa: ASYNC110 - observe worker state
                await asyncio.sleep(0.02)
        await worker.cancel(task.task_id)
        stopped = await wait_for(worker, task.task_id, {State.CANCELLED})
        assert stopped.result is None
        assert "owned process stopped" in stopped.error
    finally:
        await worker.close()


async def test_deadline_does_not_report_success(settings):
    settings.task_timeout_seconds = 5
    worker = Worker(settings)
    await worker.start()
    try:
        task = submit(worker, "slow")
        failed = await wait_for(worker, task.task_id, {State.FAILED})
        assert "deadline exceeded" in failed.error
    finally:
        await worker.close()
