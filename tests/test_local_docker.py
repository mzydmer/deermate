"""Local deployment safety invariants; no Docker or live model required."""

import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts import ack_deploy as ack
from scripts import local_docker as local

ROOT = Path(__file__).resolve().parents[1]


def test_local_stack_keeps_host_authority_narrow():
    stack = yaml.safe_load((ROOT / "deploy/local/compose.yaml").read_text())
    services = stack["services"]
    assert services["nginx"]["ports"] == ["127.0.0.1:2026:2026"]
    for name, service in services.items():
        assert not service.get("privileged")
        assert "docker.sock" not in json.dumps(service)
        assert "host" != service.get("network_mode")
        if name != "nginx":
            assert not service.get("ports")
        if name != "init":
            assert service["user"] != "0:0"
            assert service["cap_drop"] == ["ALL"]
            assert not service.get("cap_add")
    assert services["init"]["network_mode"] == "none"
    assert services["frontend"]["entrypoint"][0] == "node"
    assert services["frontend"]["env_file"] != services["gateway"]["env_file"]
    assert all(
        ".codex" not in mount and "/Users:/" not in mount
        for service in services.values()
        for mount in service.get("volumes", [])
    )
    assert all(
        "${DEERMATE_STATE_DIR}" not in mount
        for service in services.values()
        for mount in service.get("volumes", [])
    )


def test_unknown_submit_outcome_reuses_saved_intent(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "STATE", tmp_path)
    first = local.pending_submission()
    second = local.pending_submission()
    assert second == first
    assert (tmp_path / "pending-verification.json").stat().st_mode & 0o777 == 0o600
    assert first["prompt"] == local.PROMPT


def test_stage_archive_excludes_host_account_and_runtime_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "STATE", tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    for name in (
        "config.yaml",
        "controller.toml",
        "extensions_config.json",
        "nginx.conf",
        "empty.env",
    ):
        (config / name).write_text("generated configuration")
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    for name in ("client.key", "known_hosts", "api.token"):
        ack.private_write(credentials / name, "generated fixture credential")
    for name in ("admin.json", "runtime.env", "frontend.env", "auth.json"):
        ack.private_write(tmp_path / name, "must never be staged")
    (config / "unrelated-private-file").write_text("must never be staged")
    with tarfile.open(fileobj=io.BytesIO(local.stage_archive())) as archive:
        members = {item.name: item for item in archive.getmembers()}
        assert set(members) == {
            "config.yaml",
            "controller.toml",
            "extensions_config.json",
            "nginx.conf",
            "empty.env",
            "local_gateway.py",
            "local_container_init.py",
            "credentials",
            "credentials/client.key",
            "credentials/known_hosts",
            "credentials/api.token",
        }
        assert members["credentials"].mode == 0o700
        assert all(
            item.mode == 0o600 for name, item in members.items() if name.startswith("credentials/")
        )
        assert all(item.isfile() or item.isdir() for item in members.values())


def test_native_pid_reuse_does_not_stop_another_process(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "STATE", tmp_path)
    (tmp_path / "worker.process.json").write_text(json.dumps({"pid": 4321, "started": "old start"}))
    monkeypatch.setattr(
        local.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="unrelated process"),
    )
    monkeypatch.setattr(local.os, "kill", lambda *args: pytest.fail("must not signal a reused PID"))
    local.native_stop("worker")
    assert not (tmp_path / "worker.process.json").exists()


def test_network_hardening_refuses_unknown_upstream_structure():
    with pytest.raises(ack.DeploymentError, match="Unexpected pinned"):
        ack.gateway_dockerfile("FROM unexpected-image\n", "RUN true\n")
