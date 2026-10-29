"""Bounded, versioned Worker capability contract; never echo arbitrary fields."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CAPABILITIES_LIMIT = 32_768


class ProtocolError(ValueError):
    def __init__(self, message: str, code: str = "invalid_response"):
        super().__init__(message)
        self.code = code


class WorkerCapabilities(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    protocol_version: Literal[1]
    instance_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    adapter: Literal["codex-app-server"]
    operations: list[Literal["submit", "status", "events", "cancel", "resume", "input"]] = Field(
        min_length=3, max_length=6
    )
    continuation: Literal["child-tasks-v1"] | None = None
    remote: Literal[False]

    @model_validator(mode="after")
    def required_operations(self):
        if len(set(self.operations)) != len(self.operations) or not {
            "submit",
            "status",
            "cancel",
        }.issubset(self.operations):
            raise ValueError("required operations missing or duplicated")
        return self


def parse_capabilities(content: bytes) -> WorkerCapabilities:
    if len(content) > CAPABILITIES_LIMIT:
        raise ProtocolError("Worker capabilities exceeded the response limit.")
    try:
        payload = json.loads(content)
        if isinstance(payload, dict):
            version = payload.get("protocol_version")
            if type(version) is int and version != 1:
                raise ProtocolError(
                    "Worker protocol version is unsupported.", "unsupported_protocol"
                )
            adapter = payload.get("adapter")
            if isinstance(adapter, str) and adapter != "codex-app-server":
                raise ProtocolError("Worker adapter is unsupported.", "unsupported_adapter")
        # Pydantic's Literal accepts True as 1; forbid that coercion explicitly.
        if not isinstance(payload, dict) or type(payload.get("protocol_version")) is not int:
            raise ValueError("invalid version")
        if type(payload.get("remote")) is not bool:
            raise ValueError("invalid boundary")
        return WorkerCapabilities.model_validate(payload)
    except (ValueError, RecursionError) as error:
        if isinstance(error, ProtocolError):
            raise
        raise ProtocolError("Worker returned invalid capabilities.") from error
