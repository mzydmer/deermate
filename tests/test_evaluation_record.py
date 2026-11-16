"""Record initialization captures real identities without inventing result provenance."""

import hashlib
import json
import shutil
import subprocess

import pytest

from scripts import evaluation_record as records


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for name in ["docs/research/evaluation-record.template.json", "deploy/deerflow.lock"]:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(records.ROOT / name, target)
    (root / "code.py").write_text("# source fixture\n")
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        check=True,
    )
    return root


def test_source_revision_and_lock_are_actual_checkout_values(repo):
    record = records.create_record(repo)
    assert record["software"]["code_revision"] == records.git(repo, "rev-parse", "HEAD")
    assert len(record["software"]["code_revision"]) == 40
    assert record["software"]["permanent_source_url"].endswith(record["software"]["code_revision"])
    assert (
        record["software"]["deerflow_revision"]
        == (repo / "deploy/deerflow.lock").read_text().strip()
    )
    assert record["software"]["identity_scope"] == "record_initialization_checkout"
    assert record["template_only"] and record["experiment"]["status"] == "not_run"
    assert record["results"]["software_revision"] is None


def test_dirty_source_cannot_be_recorded_as_a_clean_commit(repo):
    (repo / "code.py").write_text("# changed source\n")
    with pytest.raises(ValueError, match="Commit source changes"):
        records.create_record(repo)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dataset_version": "v1"},
        {"dataset_version": ""},
        {"results_version": "v1"},
    ],
)
def test_unpaired_or_empty_versions_are_rejected(repo, kwargs):
    with pytest.raises(ValueError, match="artifact file and a nonempty version"):
        records.create_record(repo, **kwargs)


def test_existing_results_are_not_assigned_to_a_newer_source_commit(repo, tmp_path):
    producing_revision = records.git(repo, "rev-parse", "HEAD")
    (repo / "code.py").write_text("# newer source\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "newer",
        ],
        check=True,
    )
    current_revision = records.git(repo, "rev-parse", "HEAD")
    assert producing_revision != current_revision
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text('{"fixture":true}\n')
    result = tmp_path / "results.json"
    result.write_text(json.dumps({"software_revision": producing_revision, "fixture": True}))
    record = records.create_record(
        repo,
        dataset=dataset,
        dataset_version="fixture-v1",
        results=result,
        results_version="fixture-results-v1",
    )
    assert record["software"]["code_revision"] == current_revision
    assert record["dataset"]["sha256"] == hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert record["results"]["sha256"] == hashlib.sha256(result.read_bytes()).hexdigest()
    assert record["results"]["provenance_status"] == "unverified"
    assert record["results"]["software_revision"] is None
    assert record["results"]["dataset_sha256"] is None
    assert json.loads(result.read_text())["software_revision"] == producing_revision


def test_result_file_requires_a_dataset_identity(repo, tmp_path):
    result = tmp_path / "result.json"
    result.write_text('{"fixture":true}\n')
    with pytest.raises(ValueError, match="associated with a dataset"):
        records.create_record(repo, results=result, results_version="fixture-v1")
