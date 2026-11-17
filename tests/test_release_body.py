"""Existing Release metadata repair must never republish or change asset identity."""

import copy
import json

import pytest

from scripts import repair_alpha_release_body as repair


@pytest.fixture
def fixture(monkeypatch):
    before_body = "\n".join(f"[guide](../docs/{name})" for name in repair.DOCUMENTS)
    after_body = before_body
    for name in repair.DOCUMENTS:
        after_body = after_body.replace(
            f"(../docs/{name})",
            f"(https://github.com/{repair.REPOSITORY}/blob/{repair.TAG}/docs/{name})",
        )
    monkeypatch.setattr(repair, "BEFORE_BODY_SHA256", repair.digest(before_body))
    monkeypatch.setattr(repair, "AFTER_BODY_SHA256", repair.digest(after_body))
    for key, value in {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": repair.REPOSITORY,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_TOKEN": "synthetic-job-token",
    }.items():
        monkeypatch.setenv(key, value)
    receipt = json.loads(repair.RECEIPT.read_text())
    release = repair.expected_identity(receipt)
    release["body"] = before_body
    calls = []
    state = {"release": release, "change_asset_after_patch": False, "unknown_patch": False}

    def api(method, path, body=None):
        calls.append((method, path, body))
        if path == "/git/ref/tags/" + repair.TAG:
            return {"object": {"type": "tag", "sha": repair.TAG_OBJECT}}
        if path == "/git/tags/" + repair.TAG_OBJECT:
            return {"object": {"type": "commit", "sha": repair.SOURCE}}
        assert path == f"/releases/{repair.RELEASE_ID}"
        if method == "PATCH":
            assert set(body) == {"body"}
            if state["unknown_patch"]:
                raise OSError("Unknown PATCH result")
            state["release"]["body"] = body["body"]
            if state["change_asset_after_patch"]:
                state["release"]["assets"][0]["digest"] = "sha256:" + "0" * 64
        else:
            assert method == "GET" and body is None
        return copy.deepcopy(state["release"])

    return state, calls, api, after_body


def test_only_body_is_patched_and_identity_is_rechecked(fixture):
    state, calls, api, body = fixture
    before = repair.identity(state["release"])
    result = repair.repair(apply=True, api_call=api)
    assert result["applied"] and result["public_body_verified"]
    assert state["release"]["body"] == body
    assert repair.identity(state["release"]) == before
    assert [c for c in calls if c[0] != "GET"] == [
        ("PATCH", f"/releases/{repair.RELEASE_ID}", {"body": body})
    ]
    assert sum(c[1].startswith("/git/") for c in calls) == 4


def test_dry_run_is_read_only(fixture):
    state, calls, api, body = fixture
    original = state["release"]["body"]
    result = repair.repair(api_call=api)
    assert not result["applied"] and not result["public_body_verified"]
    assert state["release"]["body"] == original and original != body
    assert all(c[0] == "GET" for c in calls)


@pytest.mark.parametrize("change", ["body", "draft", "asset_digest", "missing_asset"])
def test_unknown_existing_state_refuses_patch(fixture, change):
    state, calls, api, _ = fixture
    release = state["release"]
    if change == "body":
        release["body"] += "\nUnexpected edit"
    elif change == "draft":
        release["draft"] = True
    elif change == "asset_digest":
        release["assets"][0]["digest"] = "sha256:" + "0" * 64
    else:
        release["assets"].pop()
    with pytest.raises(ValueError):
        repair.repair(apply=True, api_call=api)
    assert all(c[0] == "GET" for c in calls)


def test_already_repaired_body_does_not_write_again(fixture):
    state, calls, api, body = fixture
    state["release"]["body"] = body
    result = repair.repair(apply=True, api_call=api)
    assert not result["applied"] and result["public_body_verified"]
    assert all(c[0] == "GET" for c in calls)


def test_post_patch_asset_drift_stops_without_another_write(fixture):
    state, calls, api, _ = fixture
    state["change_asset_after_patch"] = True
    with pytest.raises(ValueError, match="Post-patch"):
        repair.repair(apply=True, api_call=api)
    assert len([c for c in calls if c[0] == "PATCH"]) == 1


def test_unknown_patch_result_is_not_retried(fixture):
    state, calls, api, _ = fixture
    state["unknown_patch"] = True
    with pytest.raises(OSError, match="Unknown PATCH"):
        repair.repair(apply=True, api_call=api)
    assert len([c for c in calls if c[0] == "PATCH"]) == 1


def test_outside_main_actions_refuses_before_api_access(fixture, monkeypatch):
    _, calls, api, _ = fixture
    monkeypatch.setenv("GITHUB_REF", "refs/pull/20/merge")
    with pytest.raises(ValueError, match="main Actions job"):
        repair.repair(apply=True, api_call=api)
    assert not calls


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/releases", {}),
        ("PATCH", f"/releases/{repair.RELEASE_ID}", {"draft": False}),
        ("PATCH", "/releases/1", {"body": "unexpected"}),
    ],
)
def test_transport_rejects_republication_flags_and_other_releases(method, path, body):
    with pytest.raises(ValueError):
        repair.api(method, path, body)
