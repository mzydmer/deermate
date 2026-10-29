import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scripts import verify_secretary as live


@pytest.mark.parametrize(
    "url", ["http://localhost:2026", "http://127.0.0.1:2026/", "https://example.com"]
)
def test_explicit_https_or_loopback_origin(url):
    assert live.origin(url) == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:secret@example.com",
        "https://example.com/api",
        "https://example.com?key=secret",
        "https://example.com#fragment",
        "file:///tmp/local",
    ],
)
def test_unsafe_origin_rejected_without_echoing_secrets(url):
    with pytest.raises(live.AcceptanceError) as error:
        live.origin(url)
    assert "secret" not in str(error.value)


def test_private_account_and_state_limits(tmp_path):
    account = tmp_path / "account.json"
    live.save_private(account, {"email": "owner@example.invalid", "password": "private"})
    assert account.stat().st_mode & 0o777 == 0o600
    assert live.private_json(account)["password"] == "private"
    symlink = tmp_path / "symlink"
    symlink.symlink_to(account)
    with pytest.raises(OSError):
        live.private_json(symlink)
    account.chmod(0o644)
    with pytest.raises(live.AcceptanceError):
        live.private_json(account)
    account.chmod(0o600)
    account.write_text("x" * 16385)
    with pytest.raises(live.AcceptanceError):
        live.private_json(account)


def test_saved_intent_stays_bound_to_target_and_model(tmp_path):
    path = tmp_path / "intent.json"
    args = dict(url="http://localhost:2026", mode="dispatch", model="configured", project="demo")
    first = live.intent(path, **args)
    assert live.intent(path, **args) == first
    with pytest.raises(live.AcceptanceError):
        live.intent(path, **(args | {"model": "different"}))
    assert live.private_json(path) == first


def test_state_lock_rejects_concurrent_verifier_and_releases_after_exit(tmp_path):
    with live.state_lock(tmp_path):
        with pytest.raises(live.AcceptanceError, match="concurrent"):
            with live.state_lock(tmp_path):
                pytest.fail("Concurrent verification must not start")
    with live.state_lock(tmp_path):
        pass


def test_interrupted_temporary_write_does_not_block_future_atomic_save(tmp_path):
    path = tmp_path / "intent.json"
    leftover = tmp_path / "intent.json.tmp"
    leftover.write_text("interrupted incomplete data")
    leftover.chmod(0o600)
    live.save_private(path, {"run_attempted": True})
    assert live.private_json(path) == {"run_attempted": True}


def test_lost_run_ack_only_reconciles_and_never_posts_again(tmp_path):
    path = tmp_path / "intent.json"
    value = live.intent(
        path, url="http://localhost:2026", mode="dispatch", model="model", project="demo"
    )
    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            assert live.private_json(path)["run_attempted"]
            assert request.headers["Idempotency-Key"] == value["key"]
            assert "/deermate-local/" not in request.url.path
            raise httpx.ReadTimeout("private upstream error")
        if request.url.path.endswith("/runs"):
            return httpx.Response(
                200,
                json=[{"run_id": "existing", "metadata": {"deermate_acceptance": value["key"]}}],
            )
        return httpx.Response(200, json={"thread_id": value["thread_id"]})

    with httpx.Client(
        base_url="http://localhost:2026", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(httpx.ReadTimeout):
            live.ensure_run(client, path, value)
        restored = live.private_json(path)
        assert live.ensure_run(client, path, restored) == "existing"
    assert len([method for method, _ in calls if method == "POST"]) == 1


def test_ambiguous_attempt_fails_without_replay(tmp_path):
    path = tmp_path / "intent.json"
    value = live.intent(
        path, url="http://localhost:2026", mode="chat", model="model", project="demo"
    )
    value["run_attempted"] = True

    def respond(request):
        assert request.method == "GET"
        return httpx.Response(200, json=[])

    with httpx.Client(
        base_url="http://localhost:2026", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(live.AcceptanceError, match="no replay"):
            live.ensure_run(client, path, value)


def test_raw_api_error_body_is_never_reported():
    with httpx.Client(
        base_url="http://localhost:2026",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, text="private-key-or-provider-error")
        ),
    ) as client:
        with pytest.raises(live.AcceptanceError) as error:
            live.request(client, "GET", "/api/models")
    assert "private" not in str(error.value)


def test_chat_receipt_projects_facts_without_messages_account_or_origin(tmp_path, monkeypatch):
    account = tmp_path / "account.json"
    live.save_private(account, {"email": "private@example.invalid", "password": "private-password"})
    args = SimpleNamespace(
        url="http://localhost:2026",
        account_file=account,
        mode="chat",
        model="configured",
        project="demo",
        worker_config=None,
        state_dir=tmp_path / "state",
        receipt=tmp_path / "receipt.json",
    )

    def respond(request):
        path = request.url.path
        if path == "/api/v1/auth/login/local":
            return httpx.Response(200, json={}, headers={"Set-Cookie": "csrf_token=private-cookie"})
        if path == "/api/v1/auth/me":
            return httpx.Response(200, json={"id": "private-owner", "system_role": "admin"})
        if path == "/api/models":
            return httpx.Response(200, json={"models": [{"name": "configured"}]})
        if path.endswith("/state"):
            return httpx.Response(
                200,
                json={
                    "values": {
                        "messages": [
                            {"type": "human", "content": "private message"},
                            {"type": "ai", "content": "DEERMATE_CHAT_OK"},
                        ]
                    }
                },
            )
        if path.endswith("/mcp-tasks"):
            return httpx.Response(200, json=[])
        if request.method == "POST" and path.endswith("/runs"):
            return httpx.Response(200, json={"run_id": "run"})
        if path.endswith("/runs/run"):
            return httpx.Response(200, json={"status": "success", "llm_call_count": 1})
        return httpx.Response(200, json={})

    original = httpx.Client
    monkeypatch.setattr(
        live.httpx,
        "Client",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    receipt = live.verify(args)
    assert receipt["passed"] and receipt["mcp_tasks"] == 0
    assert receipt["normal_run_api"] and not receipt["submit_shim_used"]
    assert "private" not in json.dumps(receipt) and "localhost" not in json.dumps(receipt)
    assert live.private_json(Path(args.receipt)) == receipt


@pytest.mark.parametrize("failure", [None, "instance", "fingerprint", "missing", "invalid_id"])
def test_native_key_mapping_is_read_only_and_instance_bound(tmp_path, failure):
    settings = SimpleNamespace(state_dir=tmp_path)
    value = {"key": "known-key", "project": "demo"}
    expected = live.digest(
        {
            "operation": "submit",
            "project_id": "demo",
            "prompt": live.PROMPT,
            "idempotency_key": value["key"],
        }
    )
    path = tmp_path / "tasks.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE metadata(key TEXT, value TEXT);"
            "CREATE TABLE requests(key TEXT, task_id TEXT, fingerprint TEXT);"
        )
        db.execute(
            "INSERT INTO metadata VALUES ('instance_id',?)",
            ("b" * 32 if failure == "instance" else "a" * 32,),
        )
        if failure != "missing":
            db.execute(
                "INSERT INTO requests VALUES (?,?,?)",
                (
                    value["key"],
                    "invalid/../id" if failure == "invalid_id" else "c" * 32,
                    "wrong-operation" if failure == "fingerprint" else expected,
                ),
            )
    before = path.read_bytes()
    if failure:
        with pytest.raises(live.AcceptanceError, match="did not match"):
            live.native_reference(settings, value, "a" * 32)
    else:
        assert live.native_reference(settings, value, "a" * 32) == "c" * 32
    assert path.read_bytes() == before
