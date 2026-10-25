import stat

from fastapi.testclient import TestClient

from deermate.api import create_app, token_file


def test_auth_host_origin_and_project_admission(settings):
    token = "a" * 48
    app = create_app(settings, token=token)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/tasks").status_code == 401
        client.headers["Authorization"] = "Bearer " + token
        assert client.get("/tasks").status_code == 200
        assert client.get("/tasks", headers={"Origin": "https://evil.invalid"}).status_code == 403
        assert client.get("/tasks", headers={"Host": "evil.invalid"}).status_code == 403
        payload = {"project_id": "missing", "prompt": "hi", "idempotency_key": "1"}
        assert client.post("/tasks", json=payload).status_code == 404
        payload["project_id"] = "demo"
        assert client.post("/tasks", json={**payload, "command": ["arbitrary"]}).status_code == 422
        response = client.post("/tasks", json=payload)
        assert response.status_code == 201
        duplicate = client.post("/tasks", json=payload)
        assert duplicate.status_code == 200
        assert duplicate.json()["task_id"] == response.json()["task_id"]
        assert client.post("/tasks", json={**payload, "prompt": "changed"}).status_code == 409
        assert client.get("/tasks/unknown").status_code == 404
        assert client.get("/tasks?limit=100000").status_code == 422
        assert client.post("/tasks", content=b"x" * 64_001).status_code == 413
        assert client.get("/tasks").headers["cache-control"] == "no-store"


def test_token_symlink_rejected(tmp_path):
    import pytest

    target = tmp_path / "secret"
    target.write_text("a" * 48)
    (tmp_path / "api.token").symlink_to(target)
    with pytest.raises(OSError):
        token_file(tmp_path)


def test_private_token_file(tmp_path):
    token = token_file(tmp_path)
    assert len(token) >= 32
    assert token_file(tmp_path) == token
    assert stat.S_IMODE((tmp_path / "api.token").stat().st_mode) == 0o600
