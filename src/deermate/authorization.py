"""Locally confirmed remote grants. Local administrative API authority is unchanged."""

import json
import os
import stat
import time
from pathlib import Path

from .models import Conflict


def private_json(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("authorization state must be a private regular file")
        raw = source.read(256_001)
    if len(raw) > 256_000:
        raise ValueError("authorization state exceeds limit")
    return json.loads(raw)


def private_save(path: Path, value: dict):
    import tempfile

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".authorization-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def local_grant(state_dir: Path, grant_id: str, *, require_active=True) -> dict:
    try:
        state = private_json(state_dir / "remote-authorizations.json")
        grant = state["grants"][grant_id]
        active = grant["policy"]
        if grant.get("revoked"):
            raise Conflict("remote authorization revoked")
        if require_active:
            # Both clocks must agree with a recent local connector observation.
            issued = state["observed_at"]
            mono = state["observed_monotonic"]
            if not 0 <= time.time() - issued <= 90 or not 0 <= time.monotonic() - mono <= 90:
                raise Conflict("remote authorization observation is stale")
            observed_server = state.get("server_time", issued)
            trusted_now = max(time.time(), observed_server + time.monotonic() - mono)
            if active.get("expires_at") is not None and active["expires_at"] <= trusted_now:
                raise Conflict("remote authorization expired")
        return grant
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise Conflict("remote authorization unavailable; local confirmation required") from error


def admit_remote(settings, grant_id: str, operation: str, project: str | None = None):
    grant = local_grant(settings.state_dir, grant_id)
    policy = grant["policy"]
    if operation != "check" and operation not in policy["operations"]:
        raise Conflict("operation is outside the locally confirmed authorization")
    if project is not None and project not in policy["projects"]:
        raise Conflict("project is outside the locally confirmed authorization")
    return grant
