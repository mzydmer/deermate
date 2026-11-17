"""Release identity, integrity, actual API proof shape and publication refusal contracts."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from scripts import release_artifacts as artifacts
from scripts import release_publish as publication


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    (root / "releases").mkdir(parents=True)
    (root / "deploy").mkdir()
    stamp = datetime.now(UTC).date().isoformat()
    policy = {
        "schema_version": 1,
        "tag": "v0.1.0-alpha.1",
        "version": "0.1.0-alpha.1",
        "worker_version": "0.1.0a1",
        "release_date_utc": stamp,
        "prerelease": True,
        "public_oci_images": [],
        "source_build_platforms": ["linux/amd64"],
    }
    (root / "releases/alpha.json").write_text(json.dumps(policy))
    (root / "pyproject.toml").write_text('[project]\nversion="0.1.0a1"\n')
    (root / "CITATION.cff").write_text(
        yaml.safe_dump({"version": "0.1.0-alpha.1", "date-released": stamp})
    )
    (root / "deploy/deerflow.lock").write_text("a" * 40 + "\n")
    for args in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Release fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    return root


@pytest.fixture
def distributions(tmp_path):
    directory = tmp_path / "dist"
    directory.mkdir()
    (directory / "deermate-0.1.0a1-py3-none-any.whl").write_bytes(b"wheel fixture")
    (directory / "deermate-0.1.0a1.tar.gz").write_bytes(b"sdist fixture")
    return directory


def api_shape(revision):
    # Real REST run/job shapes, deliberately not a prebuilt proof dictionary.
    run = {
        "id": 1234,
        "head_sha": revision,
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "path": ".github/workflows/ci.yml",
        "html_url": "https://github.com/mzydmer/deermate/actions/runs/1234",
    }
    jobs = [
        {"id": index, "name": name, "status": "completed", "conclusion": "success"}
        for index, name in enumerate(sorted(publication.EXPECTED_JOBS), 1)
    ]
    return run, jobs


def test_actual_api_proof_shape_is_shared_by_prepare_and_publish(
    source, distributions, monkeypatch
):
    revision = artifacts.clean_source(source)
    run, jobs = api_shape(revision)
    calls = []

    def api(method, path, *_args, **_kwargs):
        calls.append((method, path))
        assert method == "GET", "preparing a CI proof must never publish"
        return {"jobs": jobs} if path.endswith("jobs?per_page=100") else run

    monkeypatch.setattr(publication, "api", api)
    prepared = artifacts.prepare(distributions, ci_run_id=1234, root=source)
    server = publication.successful_ci(revision, 1234)
    assert prepared["ci"] == server
    assert len(server["jobs"]) == 13
    assert artifacts.verify(distributions, root=source, require_ci=True)["ci"] == server
    assert calls


@pytest.mark.parametrize("change", ["wrong_sha", "failed_job", "missing_job", "cancelled_run"])
def test_ci_cannot_be_inferred_from_a_run_id(change):
    run, jobs = api_shape("a" * 40)
    if change == "wrong_sha":
        run["head_sha"] = "b" * 40
    elif change == "failed_job":
        jobs[0]["conclusion"] = "failure"
    elif change == "missing_job":
        jobs.pop()
    else:
        run["conclusion"] = "cancelled"
    with pytest.raises(ValueError):
        publication.validate_ci(run, jobs, "a" * 40)


def test_candidate_is_not_a_verified_published_release(source, distributions):
    result = artifacts.prepare(distributions, root=source)
    assert result["ci"]["verified_success"] is False
    assert result["publication_status"] == "candidate_not_published"
    with pytest.raises(ValueError, match="successful CI"):
        artifacts.verify(distributions, root=source, require_ci=True)
    with pytest.raises(FileExistsError):
        artifacts.prepare(distributions, root=source)


@pytest.mark.parametrize("change", ["wheel", "sdist", "manifest", "missing_sum", "duplicate_sum"])
def test_modified_or_missing_assets_and_checksums_are_rejected(source, distributions, change):
    artifacts.prepare(distributions, root=source)
    if change == "wheel":
        (distributions / "deermate-0.1.0a1-py3-none-any.whl").write_bytes(b"changed")
    elif change == "sdist":
        (distributions / "deermate-0.1.0a1.tar.gz").unlink()
    elif change == "manifest":
        p = distributions / "manifest.json"
        p.write_text(p.read_text() + " ")
    else:
        p = distributions / "SHA256SUMS"
        lines = p.read_text().splitlines(keepends=True)
        p.write_text("".join(lines[1:] if change == "missing_sum" else lines + lines[:1]))
    with pytest.raises(ValueError):
        artifacts.verify(distributions, root=source)


def test_dirty_source_and_wrong_tag_are_rejected(source, distributions):
    with pytest.raises(ValueError):
        artifacts.metadata(source, tag="v0.2.0-alpha.1")
    (source / "uncommitted.txt").write_text("fixture")
    with pytest.raises(ValueError, match="clean"):
        artifacts.prepare(distributions, root=source)


def test_cff_package_date_and_unassigned_paper_metadata_gates(source):
    source_date = datetime.now(UTC).date()
    assert artifacts.metadata(source, publishing=True)["release_date_utc"] == str(source_date)
    with pytest.raises(ValueError, match="actual UTC date"):
        artifacts.metadata(source, publishing=True, today=source_date + timedelta(days=1))
    path = source / "CITATION.cff"
    original = yaml.safe_load(path.read_text())
    for value in [
        {**original, "version": "0.2.0"},
        {**original, "date-released": str(source_date - timedelta(days=1))},
        {**original, "doi": "unassigned-fixture"},
    ]:
        path.write_text(yaml.safe_dump(value))
        with pytest.raises(ValueError):
            artifacts.metadata(source)


def test_publication_is_refused_before_any_mutation_outside_tag_actions(source, monkeypatch):
    calls = []
    monkeypatch.setattr(publication, "api", lambda *args, **kwargs: calls.append(args))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(PermissionError):
        publication.publish(Path("nonexistent"), "v0.1.0-alpha.1", Path("none"), root=source)
    assert not calls


def test_release_day_cannot_be_a_future_date(source):
    stamp = datetime.now(UTC).date() + timedelta(days=1)
    policy = json.loads((source / "releases/alpha.json").read_text())
    policy["release_date_utc"] = str(stamp)
    (source / "releases/alpha.json").write_text(json.dumps(policy))
    cff = {"version": policy["version"], "date-released": str(stamp)}
    (source / "CITATION.cff").write_text(yaml.safe_dump(cff))
    with pytest.raises(ValueError, match="actual UTC date"):
        artifacts.metadata(source)


@pytest.mark.parametrize("bad_upload", [False, True])
def test_draft_publication_requires_all_server_digests_before_final_patch(
    source, distributions, monkeypatch, bad_upload
):
    import hashlib
    import urllib.error
    import urllib.parse

    revision = artifacts.clean_source(source)
    run, jobs = api_shape(revision)
    subprocess.run(["git", "-C", str(source), "tag", "v0.1.0-alpha.1"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "update-ref", "refs/remotes/origin/main", revision], check=True
    )
    for name, value in {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REPOSITORY": "mzydmer/deermate",
        "GITHUB_REF": "refs/tags/v0.1.0-alpha.1",
        "GITHUB_SHA": revision,
        "GITHUB_TOKEN": "test-fixture-token",
    }.items():
        monkeypatch.setenv(name, value)
    uploads, patches = [], []

    def api(method, path, body=None, *, binary=None):
        if path.startswith("/actions/runs/"):
            return {"jobs": jobs} if "/jobs?" in path else run
        if method == "GET" and path.startswith("/releases/tags/"):
            raise urllib.error.HTTPError(
                "https://api.github.com/fixture", 404, "not found", {}, None
            )
        if method == "POST" and path == "/releases":
            assert body["draft"] is True and body["prerelease"] is True
            return {
                "id": 55,
                "upload_url": "https://uploads.github.com/repos/mzydmer/deermate/releases/55/assets{?name}",
            }
        if binary is not None:
            name = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)["name"][0]
            uploads.append(name)
            return {
                "name": name,
                "size": len(binary),
                "digest": "sha256:"
                + ("0" * 64 if bad_upload else hashlib.sha256(binary).hexdigest()),
            }
        if method == "GET" and path.startswith("/releases/55/assets"):
            return [{"name": v} for v in uploads]
        if method == "PATCH":
            patches.append(body)
            return {
                "published_at": json.loads((source / "releases/alpha.json").read_text())[
                    "release_date_utc"
                ]
                + "T12:00:00Z",
                "draft": False,
                "prerelease": True,
                "html_url": "https://github.com/mzydmer/deermate/releases/tag/v0.1.0-alpha.1",
            }
        pytest.fail("Unexpected publication API operation")

    monkeypatch.setattr(publication, "api", api)
    artifacts.prepare(distributions, ci_run_id=1234, root=source)
    notes = source.parent / "notes.md"
    notes.write_text("Synthetic release fixture")
    if bad_upload:
        with pytest.raises(ValueError, match="digest"):
            publication.publish(distributions, "v0.1.0-alpha.1", notes, root=source)
        assert not patches
    else:
        result = publication.publish(distributions, "v0.1.0-alpha.1", notes, root=source)
        assert len(result["asset_names"]) == len(uploads) == 4
        assert patches == [{"draft": False, "prerelease": True, "make_latest": "false"}]


@pytest.mark.parametrize("invalid", ["pr", "sha", "failed", "expired"])
def test_main_candidate_lookup_rejects_wrong_origin_and_expired_artifact(monkeypatch, invalid):
    revision = "a" * 40
    run = {
        "id": 5678,
        "head_sha": revision,
        "head_branch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
    }
    artifact = {"name": "alpha-candidate-" + revision, "expired": False}
    if invalid == "pr":
        run["event"] = "pull_request"
    elif invalid == "sha":
        run["head_sha"] = "b" * 40
    elif invalid == "failed":
        run["conclusion"] = "failure"
    else:
        artifact["expired"] = True

    def api(method, path, **kwargs):
        assert method == "GET"
        return {"artifacts": [artifact]} if "/artifacts?" in path else {"workflow_runs": [run]}

    monkeypatch.setattr(publication, "api", api)
    with pytest.raises(ValueError, match="successful main candidate"):
        publication.successful_candidate(revision)


@pytest.mark.parametrize("invalid", [None, "source", "install", "workspace", "wheel"])
def test_promotion_binds_source_smokes_wheel_and_original_build(
    source, distributions, monkeypatch, invalid
):
    import hashlib

    monkeypatch.setenv("GITHUB_RUN_ID", "5678")
    candidate = artifacts.prepare(distributions, root=source)
    revision = candidate["source_sha"]
    run, jobs = api_shape(revision)
    main_run = {
        "id": 5678,
        "head_sha": revision,
        "head_branch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
    }

    def api(method, path, **kwargs):
        assert method == "GET"
        if "/actions/workflows/release.yml/" in path:
            return {"workflow_runs": [main_run]}
        if "/artifacts?" in path:
            return {"artifacts": [{"name": "alpha-candidate-" + revision, "expired": False}]}
        return {"jobs": jobs} if "/jobs?" in path else run

    monkeypatch.setattr(publication, "api", api)
    proof = publication.successful_ci(revision, 1234)
    wheel = next(v for v in candidate["artifacts"] if v["name"].endswith(".whl"))
    install = {"passed": True, "source_sha": revision, "wheel_sha256": wheel["sha256"]}
    workspace = {
        "passed": True,
        "source_sha": revision,
        "platform": "linux/amd64",
        "database_counts": {"users": 0, "runs": 0, "mcp_tasks": 0},
    }
    if invalid == "source":
        candidate["source_sha"] = "b" * 40
        (distributions / "manifest.json").write_text(json.dumps(candidate))
        sums = [distributions / v["name"] for v in candidate["artifacts"]]
        sums.append(distributions / "manifest.json")
        (distributions / "SHA256SUMS").write_text(
            "".join(
                hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
                for p in sorted(sums)
            )
        )
    elif invalid == "install":
        install["passed"] = False
    elif invalid == "workspace":
        workspace["source_sha"] = "b" * 40
    elif invalid == "wheel":
        install["wheel_sha256"] = "0" * 64
    (distributions / "install-smoke.json").write_text(json.dumps(install))
    (distributions / "workspace-smoke.json").write_text(json.dumps(workspace))
    monkeypatch.setenv("GITHUB_RUN_ID", "9999")
    destination = distributions.parent / "promoted"
    if invalid:
        with pytest.raises(ValueError):
            publication.promote(distributions, destination, proof, root=source)
        assert not destination.exists()
    else:
        result = publication.promote(distributions, destination, proof, root=source)
        assert result["build_run_id"] == "5678" and result["publication_run_id"] == "9999"
        assert result["artifacts"] == candidate["artifacts"]
        for item in result["artifacts"]:
            assert (destination / item["name"]).read_bytes() == (
                distributions / item["name"]
            ).read_bytes()
