from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class State(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    INPUT_REQUIRED = "input_required"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    RECOVERY_REQUIRED = "recovery_required"


ACTIVE = {State.STARTING, State.RUNNING, State.INPUT_REQUIRED, State.CANCELLING}


class SubmitTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    prompt: str = Field(min_length=1, max_length=32_000)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ResumeTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=32_000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirm_recovery: bool = False


class AnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, list[str]]


class Task(BaseModel):
    task_id: str
    project_id: str
    status: State
    prompt: str
    created_at: str
    updated_at: str
    attempt: int = 1
    session_id: str | None = None
    turn_id: str | None = None
    workspace: str | None = None
    base_commit: str | None = None
    error: str | None = None
    result: dict | None = None
    policy: dict = Field(default_factory=dict)


class Conflict(ValueError):
    """The requested state transition or idempotency key conflicts."""
