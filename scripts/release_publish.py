"""Publish only an approved main-line tag with exact-source green CI and checked assets."""

import argparse
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

if __package__:
    from . import release_artifacts as artifacts
else:
    import release_artifacts as artifacts

REPOSITORY = "mzydmer/deermate"
API = "https://api.github.com/repos/" + REPOSITORY
EXPECTED_JOBS = {
    "software-citation",
    "design-system",
    "product-docs",
    "frontend-intents",
    "frontend-ui",
    "go-control",
    "worker (ubuntu-latest, 3.11)",
    "worker (macos-latest, 3.12)",
    "ack-package",
    "deerflow-contract",
    "observability",
    "deerflow-gateway (local)",
    "deerflow-gateway (ssh)",
}


def api(method, path, body=None, *, binary=None):
    token = os.environ.get("GITHUB_TOKEN")
    url = path if path.startswith("https://uploads.github.com/") else API + path
    if not (
        url.startswith(API + "/")
        or url.startswith("https://uploads.github.com/repos/" + REPOSITORY + "/releases/")
    ):
        raise ValueError("Release API destination is outside this repository")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = (
        binary if binary is not None else (json.dumps(body).encode() if body is not None else None)
    )
    if data is not None:
        headers["Content-Type"] = (
            "application/octet-stream" if binary is not None else "application/json"
        )
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def validate_ci(run, jobs, revision):
    if not (
        run["head_sha"] == revision
        and run["status"] == "completed"
        and run["conclusion"] == "success"
        and run["event"] == "push"
        and run["path"] == ".github/workflows/ci.yml"
    ):
        raise ValueError("CI must be a successful push run for this exact source SHA")
    if {v["name"] for v in jobs} != EXPECTED_JOBS or not all(
        v["status"] == "completed" and v["conclusion"] == "success" for v in jobs
    ):
        raise ValueError("Every required CI job must finish successfully")
    return {
        "run_id": run["id"],
        "source_sha": revision,
        "verified_success": True,
        "url": run["html_url"],
        "jobs": sorted(EXPECTED_JOBS),
    }


def successful_ci(revision, run_id=None):
    if run_id is None:
        runs = api(
            "GET",
            "/actions/workflows/ci.yml/runs?head_sha=" + revision + "&event=push&per_page=100",
        )["workflow_runs"]
    else:
        runs = [api("GET", f"/actions/runs/{run_id}")]
    for run in runs:
        if run.get("conclusion") != "success":
            continue
        jobs = api("GET", f"/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
        return validate_ci(run, jobs, revision)
    raise ValueError("No successful exact-source CI run is available")


def successful_candidate(revision):
    runs = api(
        "GET",
        "/actions/workflows/release.yml/runs?head_sha="
        + revision
        + "&event=push&branch=main&per_page=100",
    )["workflow_runs"]
    for run in runs:
        if not (
            run["head_sha"] == revision
            and run["head_branch"] == "main"
            and run["event"] == "push"
            and run["status"] == "completed"
            and run["conclusion"] == "success"
        ):
            continue
        candidates = api("GET", f"/actions/runs/{run['id']}/artifacts?per_page=100")["artifacts"]
        expected = "alpha-candidate-" + revision
        if any(v["name"] == expected and not v["expired"] for v in candidates):
            return run["id"]
    raise ValueError("No successful main candidate exists for this exact source SHA")


def promote(candidate_directory, directory, proof, *, root=artifacts.ROOT):
    candidate = artifacts.verify(candidate_directory, root=root)
    revision = candidate["source_sha"]
    if proof["source_sha"] != revision or proof["verified_success"] is not True:
        raise ValueError("Promotion CI proof has a different source")
    if candidate["build_run_id"] != str(successful_candidate(revision)):
        raise ValueError("Downloaded candidate is not the successful main build")
    receipts = {}
    for filename in ("install-smoke.json", "workspace-smoke.json"):
        receipt = json.loads((candidate_directory / filename).read_text())
        if receipt.get("passed") is not True or receipt.get("source_sha") != revision:
            raise ValueError("Candidate smoke receipt does not match this source")
        receipts[filename] = receipt
    install = receipts["install-smoke.json"]
    wheel = next(v for v in candidate["artifacts"] if v["name"].endswith(".whl"))
    if install["wheel_sha256"] != wheel["sha256"]:
        raise ValueError("Installed wheel does not match candidate artifact")
    workspace = receipts["workspace-smoke.json"]
    if workspace.get("platform") != "linux/amd64" or workspace.get("database_counts") != {
        "users": 0,
        "runs": 0,
        "mcp_tasks": 0,
    }:
        raise ValueError("Candidate must prove an empty Linux/amd64 workspace")
    directory.mkdir(parents=True, exist_ok=False)
    for item in candidate["artifacts"]:
        shutil.copyfile(candidate_directory / item["name"], directory / item["name"])
    result = artifacts.prepare(
        directory, ci_run_id=proof["run_id"], root=root, build_identity=candidate
    )
    if result["artifacts"] != candidate["artifacts"] or result["ci"] != proof:
        raise ValueError("Promoted distributions or CI identity differ from candidate")
    return result


def publication_guard(tag, *, root=artifacts.ROOT):
    revision = artifacts.clean_source(root)
    if not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_EVENT_NAME") == "push"
        and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_REF") == "refs/tags/" + tag
        and os.environ.get("GITHUB_SHA") == revision
        and os.environ.get("GITHUB_TOKEN")
    ):
        raise PermissionError("Publishing requires this repository's actual tag-push Actions job")
    artifacts.metadata(root, tag=tag, publishing=True)
    if artifacts.command(["git", "rev-list", "-n1", tag], cwd=root) != revision:
        raise ValueError("Tag does not resolve to the current full source SHA")
    # Only tags whose commits have been merged into main are eligible.
    artifacts.command(["git", "merge-base", "--is-ancestor", revision, "origin/main"], cwd=root)
    return revision


def publish(directory, tag, notes, *, root=artifacts.ROOT):
    revision = publication_guard(tag, root=root)
    candidate = artifacts.verify(directory, root=root, require_ci=True)
    proof = successful_ci(revision, candidate["ci"]["run_id"])
    if proof != candidate["ci"]:
        raise ValueError("Recorded CI proof differs from the actual GitHub run")
    # Never edit, replace or silently resume an existing draft/published release.
    try:
        api("GET", "/releases/tags/" + urllib.parse.quote(tag, safe=""))
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        raise FileExistsError(
            "This tag already has a release; inspect it before any further action"
        )
    release = api(
        "POST",
        "/releases",
        {
            "tag_name": tag,
            "target_commitish": revision,
            "name": "DeerMate " + tag,
            "body": notes.read_text(),
            "draft": True,
            "prerelease": True,
            "make_latest": "false",
        },
    )
    upload_url = release["upload_url"].split("{", 1)[0]
    paths = [directory / v["name"] for v in candidate["artifacts"]]
    paths += [directory / "manifest.json", directory / "SHA256SUMS"]
    for path in paths:
        result = api(
            "POST",
            upload_url + "?name=" + urllib.parse.quote(path.name, safe=""),
            binary=path.read_bytes(),
        )
        if not (
            result["name"] == path.name
            and result["size"] == path.stat().st_size
            and result.get("digest") == "sha256:" + artifacts.digest(path)
        ):
            raise ValueError("Uploaded asset digest or size differs; release remains draft")
    actual = api("GET", f"/releases/{release['id']}/assets?per_page=100")
    if {v["name"] for v in actual} != {p.name for p in paths}:
        raise ValueError("Draft asset inventory differs")
    # A UTC midnight crossing must leave the release unpublished.
    publication_guard(tag, root=root)
    result = api(
        "PATCH",
        f"/releases/{release['id']}",
        {
            "draft": False,
            "prerelease": True,
            "make_latest": "false",
        },
    )
    published = datetime.fromisoformat(result["published_at"].replace("Z", "+00:00")).astimezone(
        UTC
    )
    if (
        result["draft"]
        or not result["prerelease"]
        or published.date().isoformat() != candidate["release_date_utc"]
    ):
        raise RuntimeError("Published release metadata needs operator reconciliation")
    return {
        "release_url": result["html_url"],
        "published_at": result["published_at"],
        "source_sha": revision,
        "tag": tag,
        "asset_names": sorted(p.name for p in paths),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("find-candidate", "wait-ci", "publish"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--notes", type=Path, default=Path("releases/alpha-notes.md"))
    parser.add_argument("--wait-seconds", type=int, default=2400)
    parser.add_argument("--candidate-directory", type=Path)
    args = parser.parse_args()
    if args.action == "find-candidate":
        revision = artifacts.clean_source()
        candidate_run = successful_candidate(revision)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as out:
            out.write(f"run_id={candidate_run}\n")
        print(json.dumps({"candidate_run_id": candidate_run, "source_sha": revision}))
    elif args.action == "wait-ci":
        revision = artifacts.clean_source()
        deadline = time.monotonic() + args.wait_seconds
        while True:
            try:
                proof = successful_ci(revision)
                break
            except ValueError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Exact-source CI did not become successful") from None
                time.sleep(15)
        if args.candidate_directory is None:
            raise ValueError("Publication must promote a verified main candidate")
        promote(args.candidate_directory.resolve(), args.directory.resolve(), proof)
        print(json.dumps({"ci_run_id": proof["run_id"], "source_sha": revision}))
    else:
        print(json.dumps(publish(args.directory.resolve(), args.tag, args.notes)))


if __name__ == "__main__":
    main()
