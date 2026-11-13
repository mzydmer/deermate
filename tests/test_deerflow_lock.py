"""Single version input, checkout preservation and pre-side-effect failure contracts."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts import ack_deploy as ack
from scripts import ack_image_smoke, deerflow_lock, frontend_dev, single_host
from scripts import verify_deerflow_gateway as gateway

ROOT = Path(__file__).resolve().parents[1]


def git(checkout, *args):
    return subprocess.check_output(
        ["git", "-C", str(checkout), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def commit(checkout):
    git(checkout, "add", ".")
    git(
        checkout,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    return git(checkout, "rev-parse", "HEAD")


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    repo = tmp_path / "existing" / "deer-flow"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    (repo / "backend").mkdir()
    (repo / "backend/app.py").write_text("original = True\n")
    (repo / "frontend").mkdir()
    (repo / "frontend/index.ts").write_text("export const original = true;\n")
    (repo / ".gitignore").write_text("backend/.venv/\n")
    revision = commit(repo)
    lock = tmp_path / "deerflow.lock"
    lock.write_text(revision + "\n")
    monkeypatch.setattr(deerflow_lock, "LOCK_PATH", lock)
    return repo, revision, lock


@pytest.mark.parametrize("newline", ["", "\n"])
def test_valid_lock_cli_exports_same_revision_without_dependencies(tmp_path, newline):
    revision = deerflow_lock.read_revision()
    lock = tmp_path / "upstream.lock"
    lock.write_text(revision + newline)
    output = tmp_path / "github-output"
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "scripts/deerflow_lock.py"),
            "--lock",
            str(lock),
            "--github-output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == revision
    assert output.read_text() == f"revision={revision}\n"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "",
        "main\n",
        "v2.2.0\n",
        "a" * 7,
        "A" * 40,
        "0" * 40,
        "g" * 40,
        "a" * 41,
        " " + "a" * 40,
        "a" * 40 + "\n\n",
        "a" * 40 + "\nrevision=main\n",
        "\udcff",
    ],
)
def test_invalid_lock_never_exports_checkout_input(tmp_path, content):
    lock = tmp_path / "bad.lock"
    if content is not None:
        lock.write_bytes(content.encode("utf-8", errors="surrogateescape"))
    output = tmp_path / "github-output"
    output.write_text("existing=value\n")
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "scripts/deerflow_lock.py"),
            "--lock",
            str(lock),
            "--github-output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "DeerFlow lock" in result.stderr
    assert output.read_text() == "existing=value\n"


def test_clean_checkout_reports_actual_revision_and_ignores_runtime_venv(checkout):
    repo, revision, _ = checkout
    (repo / "backend/.venv").mkdir()
    (repo / "backend/.venv/ignored").write_text("runtime cache")
    assert deerflow_lock.verify_checkout(repo) == revision
    assert gateway.verify_checkout(repo) == revision


@pytest.mark.parametrize("state", ["unstaged", "staged", "untracked"])
def test_required_backend_changes_are_rejected_and_preserved(checkout, state):
    repo, revision, _ = checkout
    path = repo / ("backend/new.py" if state == "untracked" else "backend/app.py")
    path.write_text("local_changes = True\n")
    if state == "staged":
        git(repo, "add", "backend")
    before = git(repo, "status", "--porcelain")
    with pytest.raises(deerflow_lock.DeerFlowLockError, match="must be clean") as caught:
        gateway.verify_checkout(repo)
    assert f"expected: {revision}; actual: {revision}" in str(caught.value)
    assert path.read_text() == "local_changes = True\n"
    assert git(repo, "status", "--porcelain") == before


def test_gateway_checks_its_backend_scope_while_build_requires_whole_checkout(checkout):
    repo, revision, _ = checkout
    (repo / "frontend/index.ts").write_text("local frontend change")
    assert gateway.verify_checkout(repo) == revision
    with pytest.raises(ack.DeploymentError, match="must be clean"):
        ack.prepare(repo.parent)


def test_wrong_head_fails_before_docker_or_gateway_start_and_preserves_repo(
    checkout,
    tmp_path,
    monkeypatch,
):
    repo, expected, _ = checkout
    (repo / "backend/app.py").write_text("different = True\n")
    actual = commit(repo)

    def forbidden(*args, **kwargs):
        pytest.fail("Build/service side effects must follow checkout validation")

    monkeypatch.setattr(ack, "build_control", forbidden)
    monkeypatch.setattr(ack, "check_design_tokens", forbidden)
    monkeypatch.setattr(gateway, "port_number", forbidden)
    for operation, error in [
        (lambda: ack.build({}, repo.parent / "config.yaml", False), ack.DeploymentError),
        (
            lambda: gateway.run(repo, Path("unused"), tmp_path / "receipt.json", tmp_path),
            deerflow_lock.DeerFlowLockError,
        ),
    ]:
        with pytest.raises(error) as caught:
            operation()
        assert f"expected: {expected}; actual: {actual}" in str(caught.value)
    assert git(repo, "rev-parse", "HEAD") == actual
    assert git(repo, "status", "--porcelain") == ""
    assert not (tmp_path / "receipt.json").exists()
    assert not (repo.parent / "build-receipt.json").exists()


def test_missing_lock_fails_before_checkout_creation_or_control_build(tmp_path, monkeypatch):
    monkeypatch.setattr(deerflow_lock, "LOCK_PATH", tmp_path / "missing.lock")

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid lock must fail before any external command")

    monkeypatch.setattr(ack, "command", forbidden)
    monkeypatch.setattr(ack, "build_control", forbidden)
    with pytest.raises(deerflow_lock.DeerFlowLockError, match="Cannot read DeerFlow lock"):
        ack.build({}, tmp_path / "config.yaml", False)
    assert not (tmp_path / "deer-flow").exists()


def test_prepare_fetches_lock_and_never_resets_existing_checkout(checkout, tmp_path, monkeypatch):
    source, first, lock = checkout
    (source / "backend/app.py").write_text("updated = True\n")
    second = commit(source)
    original = ack.command
    fetched = []

    def local_git(argv, **kwargs):
        argv = list(argv)
        if argv[-2:] == ["origin", "https://github.com/bytedance/deer-flow.git"]:
            argv[-1] = source
        if "fetch" in argv:
            fetched.append(argv[-1])
        return original(argv, **kwargs)

    monkeypatch.setattr(ack, "command", local_git)
    before = tmp_path / "first-build"
    before.mkdir()
    prepared = ack.prepare(before)
    assert fetched == [first]
    assert git(prepared, "rev-parse", "HEAD") == first
    lock.write_text(second + "\n")
    with pytest.raises(ack.DeploymentError, match=f"expected: {second}; actual: {first}"):
        ack.prepare(before)
    assert fetched == [first]
    assert git(prepared, "rev-parse", "HEAD") == first
    after = tmp_path / "upgraded-build"
    after.mkdir()
    assert git(ack.prepare(after), "rev-parse", "HEAD") == second
    assert fetched == [first, second]
    assert gateway.verify_checkout(after / "deer-flow") == second


def test_frontend_rejects_wrong_head_before_archive_or_overlay(checkout, tmp_path, monkeypatch):
    repo, expected, _ = checkout
    (repo / "frontend/index.ts").write_text("changed")
    actual = commit(repo)
    output = tmp_path / "frontend-build"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "frontend_dev.py",
            "--mode",
            "prepare",
            "--upstream",
            str(repo),
            "--output",
            str(output),
            "--node",
            sys.executable,
        ],
    )
    with pytest.raises(SystemExit) as caught:
        frontend_dev.main()
    assert caught.value.code != 0
    assert not (output / "frontend").exists()
    assert not (output / "upstream.json").exists()
    assert git(repo, "rev-parse", "HEAD") == actual != expected


def test_single_host_rejects_wrong_checkout_before_generating_secrets(
    checkout,
    tmp_path,
    monkeypatch,
):
    repo, expected, lock = checkout
    lock.write_text("f" * 40 + "\n")
    monkeypatch.setattr(ack, "load", lambda _: {})
    output = tmp_path / "bundle"
    with pytest.raises(ack.DeploymentError, match=f"actual: {expected}"):
        single_host.prepare(repo.parent / "config.yaml", output, "test-project", 2027)
    assert not output.exists()


@pytest.mark.parametrize("label", [None, "f" * 40])
def test_image_mismatch_rejected_before_container_launch(tmp_path, monkeypatch, label):
    calls = []

    def inspect_only(argv, **kwargs):
        assert argv[:3] == ["docker", "image", "inspect"]
        calls.append(argv)
        return json.dumps({deerflow_lock.IMAGE_LABEL: label} if label else {})

    monkeypatch.setattr(ack_image_smoke, "command", inspect_only)
    with pytest.raises(deerflow_lock.DeerFlowLockError, match="image mismatch"):
        ack_image_smoke.run("fixture:local", {}, tmp_path / "receipt.json")
    assert len(calls) == 1
    assert not (tmp_path / "receipt.json").exists()


def test_ci_validates_lock_before_each_upstream_checkout():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = []
    for name, job in workflow["jobs"].items():
        steps = job["steps"]
        for index, step in enumerate(steps):
            if step.get("with", {}).get("repository") != "bytedance/deer-flow":
                continue
            jobs.append(name)
            assert step["with"]["ref"] == "${{ steps.deerflow.outputs.revision }}"
            reader = next(s for s in steps[:index] if s.get("id") == "deerflow")
            assert reader["run"] == (
                'python scripts/deerflow_lock.py --github-output "$GITHUB_OUTPUT"'
            )
    assert set(jobs) == {"deerflow-contract", "deerflow-gateway"}
