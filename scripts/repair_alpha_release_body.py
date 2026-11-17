"""Repair only the three pinned documentation links in one existing Alpha Release."""

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "mzydmer/deermate"
API = "https://api.github.com/repos/" + REPOSITORY
RELEASE_ID = 447839083
TAG = "v0.1.0-alpha.1"
SOURCE = "b9f20fb75162a51102ecc53b0f9cee20d2e30aee"
TAG_OBJECT = "e0ec3f211c47f9e7bfeea2bc7562a9113120cfbb"
BEFORE_BODY_SHA256 = "a4a491fa0699fb501a7a09760d7c0c230c3198c2db5269ea048440d08e868bf8"
AFTER_BODY_SHA256 = "113f8c5b847464d7251a5a3061210af9d6eea4d6c98824725f8ac5d82b5f8af7"
DOCUMENTS = ("local-worker.md", "local-docker.md", "backup-restore.md")
RECEIPT = ROOT / "docs/verification/public-alpha-release-2026-11-17.json"


def digest(body):
    return hashlib.sha256(body.encode()).hexdigest()


def api(method, path, body=None):
    if method not in {"GET", "PATCH"} or not path.startswith("/"):
        raise ValueError("Unsupported metadata API operation")
    if method == "PATCH" and (path != f"/releases/{RELEASE_ID}" or set(body or {}) != {"body"}):
        raise ValueError("Only this Release's body may be patched")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + token
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    # An unknown PATCH result stops here; do not retry or overwrite another state.
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def identity(release):
    keys = ("id", "name", "tag_name", "target_commitish", "draft", "prerelease", "published_at")
    result = {key: release[key] for key in keys}
    result["assets"] = sorted(
        (
            {key: asset[key] for key in ("id", "name", "size", "digest", "state")}
            for asset in release["assets"]
        ),
        key=lambda asset: asset["name"],
    )
    return result


def expected_identity(receipt):
    return {
        "id": RELEASE_ID,
        "name": "DeerMate " + TAG,
        "tag_name": TAG,
        "target_commitish": SOURCE,
        "draft": False,
        "prerelease": True,
        "published_at": receipt["publication"]["published_at_utc"],
        "assets": sorted(
            (
                {
                    "id": a["id"],
                    "name": a["name"],
                    "size": a["size"],
                    "digest": a["server_digest"],
                    "state": "uploaded",
                }
                for a in receipt["assets"]
            ),
            key=lambda a: a["name"],
        ),
    }


def verify_tag(api_call):
    ref = api_call("GET", "/git/ref/tags/" + TAG)["object"]
    if ref["type"] != "tag" or ref["sha"] != TAG_OBJECT:
        raise ValueError("Annotated tag identity changed")
    target = api_call("GET", "/git/tags/" + TAG_OBJECT)["object"]
    if target["type"] != "commit" or target["sha"] != SOURCE:
        raise ValueError("Release source changed")


def repaired_body(body):
    if digest(body) == AFTER_BODY_SHA256:
        return body
    if digest(body) != BEFORE_BODY_SHA256:
        raise ValueError("Unexpected Release body; inspect before changing it")
    for name in DOCUMENTS:
        old = "(../docs/" + name + ")"
        if body.count(old) != 1:
            raise ValueError("Expected exactly one original documentation link")
        body = body.replace(old, f"(https://github.com/{REPOSITORY}/blob/{TAG}/docs/{name})")
    if digest(body) != AFTER_BODY_SHA256:
        raise ValueError("Replacement body differs from the reviewed change")
    return body


def repair(*, apply=False, api_call=api, receipt_path=RECEIPT):
    if apply and not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
        and os.environ.get("GITHUB_REF") == "refs/heads/main"
        and os.environ.get("GITHUB_EVENT_NAME") in {"push", "workflow_dispatch"}
        and os.environ.get("GITHUB_TOKEN")
    ):
        raise ValueError("Applying this repair requires this repository's main Actions job")
    receipt = json.loads(receipt_path.read_text())
    if (
        receipt["source_sha"] != SOURCE
        or receipt["tag"] != TAG
        or receipt["publication"]["release_id"] != RELEASE_ID
        or len(receipt["assets"]) != 4
    ):
        raise ValueError("Publication receipt identity changed")
    verify_tag(api_call)
    before = api_call("GET", f"/releases/{RELEASE_ID}")
    expected = expected_identity(receipt)
    if identity(before) != expected:
        raise ValueError("Existing Release or four asset identities differ")
    body = repaired_body(before["body"])
    changed = body != before["body"]
    if apply:
        if changed:
            api_call("PATCH", f"/releases/{RELEASE_ID}", {"body": body})
        after = api_call("GET", f"/releases/{RELEASE_ID}")
        verify_tag(api_call)
        if identity(after) != expected or after["body"] != body:
            raise ValueError("Post-patch body, Release or asset identity differs")
    return {
        "release_id": RELEASE_ID,
        "tag": TAG,
        "source_sha": SOURCE,
        "applied": apply and changed,
        "public_body_verified": apply,
        "before_body_sha256": digest(before["body"]),
        "after_body_sha256": digest(body),
        "release_and_asset_identity": expected,
        "links": [f"https://github.com/{REPOSITORY}/blob/{TAG}/docs/{name}" for name in DOCUMENTS],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = repair(apply=args.apply)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
