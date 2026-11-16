"""Snapshot integrity must fail before Docker/target writes; no real data or keys."""

import base64
import gzip
import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

from scripts import single_host_backup as backup

IDENTITY = "00000000-0000-4000-8000-000000000001"
UPSTREAM = "a1b89d0432de4e45adc59f512cb25bb386ea1e51"


def snapshot(
    path,
    *,
    missing=None,
    corrupt=None,
    extra=None,
    headers=None,
    manifest_edit=None,
    duplicate=False,
    files=None,
):
    payload = {name: b"synthetic state" for name in backup.REQUIRED}
    payload["bundle/runtime/config.yaml"] = b"extensions: {mcpServers: {}}\n"
    payload["bundle/bundle.json"] = json.dumps({"project": "source-fixture"}).encode()
    payload.update(files or {})
    metadata = {
        "format": backup.FORMAT,
        "snapshot_id": IDENTITY,
        "recovery_point": "2026-11-16T00:00:00+00:00",
        "upstream_commit": UPSTREAM,
        "source_project": "source-fixture",
        "source_home_volume": "source-fixture-home",
        "snapshot_tool": {"sha256": "b" * 64},
        "inflight_acknowledged": False,
        "inflight_inventory": {
            name: [] for name in ("operations", "tasks", "memory_operations", "memory_jobs", "runs")
        },
        "images": {
            name: "sha256:" + "a" * 64 for name in ("control", "gateway", "frontend", "nginx")
        },
        "files": {
            name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "mode": 0o600}
            for name, data in payload.items()
        },
    }
    if manifest_edit:
        manifest_edit(metadata)
    payload["manifest.json"] = json.dumps(metadata).encode()
    if missing:
        payload.pop(missing)
    if corrupt:
        payload[corrupt] = b"tampered contents"
    if extra:
        payload[extra] = b"unexpected"
    with tarfile.open(path, "w:gz") as tar:
        for name, data in payload.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            if name != "manifest.json":
                info.uid = info.gid = 1000
            for key, value in (headers or {}).get(name, {}).items():
                setattr(info, key, value)
            tar.addfile(info, io.BytesIO(data))
            if duplicate and name == "home/data/deerflow.db":
                tar.addfile(info, io.BytesIO(data))


def test_complete_synthetic_snapshot_verifies_without_docker(tmp_path):
    path = tmp_path / "snapshot.tar.gz"
    snapshot(path)
    assert backup.verify_snapshot(path)["snapshot_id"] == IDENTITY


@pytest.mark.parametrize(
    "change",
    [
        {"missing": "home/data/deerflow.db"},
        {"missing": "bundle/runtime.env"},
        {"corrupt": "home/data/deerflow.db"},
        {"extra": "../outside"},
        {"extra": "/absolute"},
        {"duplicate": True},
        {"files": {"home/parent": b"file", "home/parent/child": b"child"}},
        *[
            {"headers": {"home/data/deerflow.db": value}}
            for value in [
                {"mode": 0o777},
                {"mode": 0o4600},
                {"uid": 0},
                {"gid": 0},
                {"mtime": 123},
                {"uname": "unexpected"},
                {"gname": "unexpected"},
                {"linkname": "/outside"},
                {"type": tarfile.CONTTYPE},
                {"type": tarfile.LNKTYPE},
                {"pax_headers": {"comment": "unexpected"}},
            ]
        ],
        {"headers": {"manifest.json": {"mode": 0o644}}},
    ],
)
def test_bad_snapshot_is_rejected_before_any_target_side_effect(tmp_path, monkeypatch, change):
    path = tmp_path / "snapshot.tar.gz"
    snapshot(path, **change)

    def no_docker(*args, **kwargs):
        pytest.fail("Invalid snapshot reached Docker")

    monkeypatch.setattr(backup, "command", no_docker)
    output = tmp_path / "new-bundle"
    with pytest.raises(backup.SnapshotError):
        backup.restore(path, output, "restore-test", 12028)
    assert not output.exists()


@pytest.mark.parametrize(
    "field",
    [
        "recovery_point",
        "snapshot_tool",
        "inflight_inventory",
        "source_home_volume",
        "upstream_commit",
        "images",
    ],
)
def test_missing_manifest_contract_is_rejected_before_docker(tmp_path, monkeypatch, field):
    path = tmp_path / "missing-metadata.tar.gz"
    snapshot(path, manifest_edit=lambda value: value.pop(field))
    monkeypatch.setattr(backup, "command", lambda *a, **kw: pytest.fail("Reached Docker"))
    output = tmp_path / "target"
    with pytest.raises(backup.SnapshotError):
        backup.restore(path, output, "restore-test", 12028)
    assert not output.exists()


@pytest.mark.parametrize("offset", [329, 337])
def test_raw_device_metadata_is_not_silently_normalized(tmp_path, monkeypatch, offset):
    path = tmp_path / "raw-metadata.tar.gz"
    snapshot(path)
    with tarfile.open(path, "r:gz") as archive:
        start = archive.getmember("home/data/deerflow.db").offset_data - tarfile.BLOCKSIZE
    blob = bytearray(gzip.decompress(path.read_bytes()))
    header = blob[start : start + tarfile.BLOCKSIZE]
    header[offset : offset + 8] = b"0000001\x00"
    header[148:156] = b" " * 8
    header[148:156] = f"{sum(header):06o}\0 ".encode()
    blob[start : start + tarfile.BLOCKSIZE] = header
    path.write_bytes(gzip.compress(blob))
    # TarInfo's writer omits device fields for regular files, so the fixture
    # edits the actual header and recomputes its checksum rather than a no-op attribute.
    with tarfile.open(path, "r:gz") as archive:
        member = archive.getmember("home/data/deerflow.db")
        assert (member.devmajor if offset == 329 else member.devminor) == 1
    monkeypatch.setattr(backup, "command", lambda *a, **kw: pytest.fail("Reached Docker"))
    output = tmp_path / "target"
    with pytest.raises(backup.SnapshotError, match="raw tar metadata"):
        backup.restore(path, output, "restore-test", 12028)
    assert not output.exists()


def test_utf8_long_paths_have_validated_pax_metadata(tmp_path):
    path = tmp_path / "utf8.tar.gz"
    name = "home/" + "资料/" * 40 + "fact.md"
    snapshot(path, files={name: b"synthetic fact"})
    assert name in backup.verify_snapshot(path)["files"]


def test_restore_uses_frozen_input_after_original_path_is_replaced(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.tar.gz"
    snapshot(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sent = []

    def docker_command(argv, **kwargs):
        if argv[:3] == ["docker", "image", "inspect"]:
            path.write_bytes(b"original path replaced after validation")
            return b"[]"
        if argv[:2] == ["docker", "run"]:
            return b'{"capabilities":["restore-quarantine-v1"]}'
        return b""

    def docker_run(argv, **kwargs):
        if "stdin" in kwargs:
            sent.append(hashlib.sha256(kwargs["stdin"].read()).hexdigest())
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(backup, "command", docker_command)
    monkeypatch.setattr(backup.subprocess, "run", docker_run)
    output = tmp_path / "target"
    result = backup.restore(path, output, "restore-test", 12028)
    assert result["snapshot_id"] == IDENTITY
    assert sent == [digest]
    assert path.read_bytes() == b"original path replaced after validation"
    compose = (output / "compose.yaml").read_text()
    assert "DEERMATE_RESTORE_QUARANTINE" in compose
    assert "internal: true" in compose


def test_real_cli_rejects_tar_mode_without_creating_target(tmp_path):
    path = tmp_path / "wrong-mode.tar.gz"
    snapshot(path, headers={"home/data/deerflow.db": {"mode": 0o777}})
    output = tmp_path / "target"
    result = subprocess.run(
        [
            sys.executable,
            str(backup.ROOT / "scripts/single_host_backup.py"),
            "restore",
            "--snapshot",
            str(path),
            "--output",
            str(output),
            "--project",
            "restore-test",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Snapshot tar metadata mismatch" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "name",
    [
        "home/../outside",
        "bundle/../../outside",
        "/home/file",
        "home\\file",
        "other/file",
    ],
)
def test_archive_path_policy_rejects_escape(name):
    with pytest.raises(backup.SnapshotError):
        backup.safe_member(name)


def test_unsupported_links_never_pass_integrity_preflight(tmp_path):
    path = tmp_path / "snapshot.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("home/linked")
        info.type = tarfile.SYMTYPE
        info.linkname = "/outside"
        tar.addfile(info)
    with pytest.raises(backup.SnapshotError, match="regular"):
        backup.verify_snapshot(path)


@pytest.mark.parametrize("acknowledged", [False, True])
def test_export_worker_preserves_unknown_identity_and_keeps_secrets_out_of_manifest(
    tmp_path,
    acknowledged,
):
    state = tmp_path / "state"
    (state / "data").mkdir(parents=True)
    database = state / "data/deerflow.db"
    cache = state / "deermate/.cache/uv"
    cache.mkdir(parents=True)
    (cache / "rebuildable-link").symlink_to("/not-part-of-the-snapshot")
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE deermate_work_records(id TEXT,kind TEXT,state TEXT);
            INSERT INTO deermate_work_records VALUES('original-operation','operation','uncertain');
            CREATE TABLE mcp_tasks(id TEXT,status TEXT);
        """)
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    configuration = {
        name.removeprefix("bundle/"): {
            "data": base64.b64encode(b"synthetic-private-key").decode(),
            "mode": 0o600,
        }
        for name in backup.REQUIRED
        if name.startswith("bundle/")
    }
    request = {
        "format": backup.FORMAT,
        "snapshot_id": IDENTITY,
        "recovery_point": "2026-11-16T00:00:00+00:00",
        "upstream_commit": UPSTREAM,
        "source_project": "source-fixture",
        "source_home_volume": "source-fixture-home",
        "snapshot_tool": {"sha256": "b" * 64},
        "images": {
            name: "sha256:" + "a" * 64 for name in ("control", "gateway", "frontend", "nginx")
        },
        "configuration": configuration,
        "inflight_acknowledged": acknowledged,
    }
    code = backup.SNAPSHOT_WORKER.replace("home=Path('/state')", f"home=Path({str(state)!r})")
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(request).encode(),
        capture_output=True,
    )
    assert hashlib.sha256(database.read_bytes()).hexdigest() == digest
    if not acknowledged:
        assert result.returncode != 0 and result.stdout == b""
        return
    assert result.returncode == 0, result.stderr
    archive = tmp_path / "export.tar.gz"
    archive.write_bytes(result.stdout)
    manifest = backup.verify_snapshot(archive)
    assert "synthetic-private-key" not in json.dumps(manifest)
    assert "configuration" not in manifest
    assert not any(".cache/uv" in name for name in manifest["files"])
    assert manifest["inflight_inventory"]["operations"] == [
        {"id": "original-operation", "state": "uncertain"},
    ]
