import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: Path
    allow_write: bool = False
    test_command: list[str] | None = None

    @field_validator("root")
    @classmethod
    def root_exists(cls, value: Path) -> Path:
        value = value.expanduser().resolve()
        if not value.is_dir():
            raise ValueError("project root must be an existing directory")
        return value

    @field_validator("test_command")
    @classmethod
    def valid_command(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (not value or not value[0] or any("\0" in x for x in value)):
            raise ValueError("test_command must be a non-empty argv array without NUL bytes")
        return value


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state_dir: Path = Path(".deermate")
    codex_command: list[str] = Field(default_factory=lambda: ["codex", "app-server"])
    model: str | None = None
    task_timeout_seconds: int = Field(default=1800, ge=5, le=7200)
    test_timeout_seconds: int = Field(default=120, ge=1, le=1800)
    max_concurrent_tasks: int = Field(default=1, ge=1, le=8)
    projects: dict[str, Project]

    @field_validator("state_dir")
    @classmethod
    def absolute_state_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("codex_command")
    @classmethod
    def valid_codex(cls, value: list[str]) -> list[str]:
        if not value or any(not x or "\0" in x for x in value):
            raise ValueError("codex_command must be a non-empty argv array")
        return value

    @field_validator("projects")
    @classmethod
    def have_projects(cls, value: dict[str, Project]) -> dict[str, Project]:
        if not value:
            raise ValueError("at least one administrator-configured project is required")
        return value

    def policy(self, project_id: str) -> dict:
        return {
            "project": self.projects[project_id].model_dump(mode="json"),
            "codex_command": self.codex_command,
            "model": self.model,
            "task_timeout_seconds": self.task_timeout_seconds,
            "test_timeout_seconds": self.test_timeout_seconds,
        }


def load_settings(path: Path) -> Settings:
    with path.open("rb") as source:
        return Settings.model_validate(tomllib.load(source))
