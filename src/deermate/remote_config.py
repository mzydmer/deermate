"""Administrator-owned SSH enrollment. No model-selected connection parameters."""

import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator

from .bridge import BridgeError


class SSHWorker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(min_length=1, max_length=253, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9.:-]*$")
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z_][a-zA-Z0-9_.-]*$")
    known_hosts: Path
    client_key: Path
    token_file: Path
    expected_instance_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expires_at: AwareDatetime
    enabled: bool = True
    worker_port: int = Field(default=18777, ge=1, le=65535)
    connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    max_connection_age_seconds: int = Field(default=60, ge=5, le=300)
    passphrase_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]{0,127}$")

    @field_validator("known_hosts", "client_key", "token_file")
    @classmethod
    def absolute_file(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError("enrollment file references must be absolute")
        return value

    def admit(self):
        if not self.enabled:
            raise BridgeError("SSH worker grant is disabled; work is not confirmed stopped.")
        if self.expires_at <= datetime.now(UTC):
            raise BridgeError("SSH worker grant expired; work is not confirmed stopped.")


class ControllerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workers: dict[str, SSHWorker]

    @field_validator("workers")
    @classmethod
    def worker_names(cls, value):
        if not value or any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", name) for name in value):
            raise ValueError("at least one valid worker ID is required")
        return value


def enrolled_worker(path: Path, worker_id: str) -> SSHWorker:
    try:
        if path.stat().st_size > 64_000:
            raise ValueError("oversized configuration")
        with path.open("rb") as source:
            settings = ControllerSettings.model_validate(tomllib.load(source))
    except (OSError, ValueError, ValidationError) as error:
        raise BridgeError("SSH controller configuration is unavailable or invalid.") from error
    if worker_id not in settings.workers:
        raise BridgeError("SSH worker is not registered or its grant was removed.")
    return settings.workers[worker_id]
