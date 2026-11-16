"""Initialize an evaluation record with actual source and supplied artifact identities."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

if __package__:
    from .deerflow_lock import read_revision
else:
    from deerflow_lock import read_revision

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def artifact(path, version):
    if (path is None) != (version is None) or (version is not None and not version.strip()):
        raise ValueError("Supply an artifact file and a nonempty version together")
    if path is None:
        return {"version": None, "artifact": None, "sha256": None}
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {
        "version": version,
        "artifact": path.name,
        "sha256": digest,
    }


def create_record(
    root=ROOT, *, dataset=None, dataset_version=None, results=None, results_version=None
):
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Commit source changes before recording an exact source revision")
    revision = git(root, "rev-parse", "HEAD")
    record = json.loads((root / "docs/research/evaluation-record.template.json").read_text())
    record["software"].update(
        code_revision=revision,
        permanent_source_url=record["software"]["repository"] + "/tree/" + revision,
        deerflow_revision=read_revision(root / "deploy/deerflow.lock"),
    )
    record["dataset"] = artifact(dataset, dataset_version)
    result = artifact(results, results_version)
    if results is not None and dataset is None:
        raise ValueError("Result identities must be associated with a dataset artifact/version")
    record["results"] = {
        **result,
        "provenance_status": "unverified" if results is not None else "not_provided",
        "software_revision": None,
        "dataset_sha256": None,
    }
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--dataset-version")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--results-version")
    args = parser.parse_args()
    try:
        record = create_record(
            dataset=args.dataset,
            dataset_version=args.dataset_version,
            results=args.results,
            results_version=args.results_version,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as output:
            output.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Evaluation record not created: {error}\n")
    print("Evaluation record initialized with the actual source SHA; no experiment was run.")


if __name__ == "__main__":
    main()
