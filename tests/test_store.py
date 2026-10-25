import pytest

from deermate.models import Conflict, ResumeTask, State, SubmitTask
from deermate.store import Store


def test_idempotency_survives_restart_and_conflicts(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = Store(path)
    request = SubmitTask(project_id="demo", prompt="fix", idempotency_key="request-1")
    task, created = store.submit(request)
    assert created
    store.close()
    store = Store(path)
    again, created = store.submit(request)
    assert not created and again.task_id == task.task_id
    with pytest.raises(Conflict):
        store.submit(request.model_copy(update={"prompt": "a different action"}))
    store.close()


def test_recovery_does_not_replay_active_work(tmp_path):
    store = Store(tmp_path / "tasks.sqlite3")
    task, _ = store.submit(SubmitTask(project_id="demo", prompt="fix", idempotency_key="1"))
    store.update(task.task_id, status=State.RUNNING, session_id="native-123")
    cursor = store.events(task.task_id)[-1]["cursor"]
    store.recover()
    assert not store.queued()
    assert store.get(task.task_id).status == State.RECOVERY_REQUIRED
    assert store.events(task.task_id, after=cursor)[0]["type"] == "task.recovery_required"
    resume = ResumeTask(message="continue", idempotency_key="resume-1")
    with pytest.raises(Conflict):
        store.resume(task.task_id, resume)
    resumed = store.resume(task.task_id, resume.model_copy(update={"confirm_recovery": True}))
    assert resumed.session_id == "native-123" and resumed.attempt == 2
    again = store.resume(task.task_id, resume.model_copy(update={"confirm_recovery": True}))
    assert again.attempt == 2
    store.close()
