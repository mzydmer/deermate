"""Private configuration, actual wire probe and exporter outage contracts."""

import asyncio
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml
from otel_receiver import Receiver

from deermate import telemetry
from deermate.api import create_app
from scripts import observability as cli

ROOT = Path(__file__).resolve().parents[1]


def profile(endpoint="http://127.0.0.1:4318/v1/traces"):
    return {"DEERMATE_TELEMETRY_ENABLED": "true", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": endpoint}


def test_private_env_and_invalid_endpoint(tmp_path):
    env = tmp_path / "telemetry.env"
    cli.private_write(env, "DEERMATE_TELEMETRY_ENABLED=true\n")
    assert cli.read_env(env) == {"DEERMATE_TELEMETRY_ENABLED": "true"}
    env.chmod(0o644)
    with pytest.raises(ValueError):
        cli.read_env(env)
    with pytest.raises(ValueError):
        cli.validate(profile("http://remote.invalid/traces"))
    with pytest.raises(ValueError):
        cli.validate(profile("https://replace-from-console.invalid/traces"))
    with pytest.raises(ValueError):
        cli.validate({**profile(), "OTEL_EXPORTER_OTLP_HEADERS": "key=replace-from-console"})
    link = tmp_path / "symlink"
    link.symlink_to(env)
    with pytest.raises(ValueError):
        cli.private_write(link, "must not overwrite", replace=True)
    assert env.read_text() == "DEERMATE_TELEMETRY_ENABLED=true\n"


def test_mcp_profile_patch_is_idempotent_and_preserves_authority(tmp_path):
    path = tmp_path / "extensions.json"
    server = {
        "command": "/private/venv/bin/python",
        "args": ["-m", "deermate.cli", "--relay-config", "/private/bridge.json", "mcp"],
        "env": {"PRIVATE_GRANT": "unchanged"},
    }
    unrelated = {"command": "other-server", "args": [], "env": {"OTHER_KEY": "unchanged"}}
    path.write_text(json.dumps({"mcpServers": {"deermate": server, "other": unrelated}}))
    assert cli.patch_mcp(path, profile()) == 1
    first = path.read_bytes()
    assert cli.patch_mcp(path, profile()) == 1
    assert path.read_bytes() == first
    result = json.loads(first)
    assert result["mcpServers"]["other"] == unrelated
    assert result["mcpServers"]["deermate"]["args"] == server["args"]
    assert result["mcpServers"]["deermate"]["env"]["PRIVATE_GRANT"] == "unchanged"
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(result["mcpInterceptors"]) == 1


def test_invalid_mcp_shape_does_not_truncate_original(tmp_path):
    path = tmp_path / "extensions.json"
    source = '{"mcpServers":{"broken":[]}}'
    path.write_text(source)
    with pytest.raises(ValueError):
        cli.patch_mcp(path, profile())
    assert path.read_text() == source


def test_probe_actual_otlp_receipt_does_not_export_or_print_credentials(tmp_path):
    with Receiver() as receiver:
        values = {
            **profile(receiver.endpoint),
            "OTEL_EXPORTER_OTLP_HEADERS": "Authentication=PRIVATE_WRITE_KEY",
        }
        env = tmp_path / "arms.env"
        cli.private_write(env, "".join(k + "=" + repr(v) + "\n" for k, v in values.items()))
        receipt = tmp_path / "receipt.json"
        run = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/observability.py"),
                "probe",
                "--env-file",
                str(env),
                "--receipt",
                str(receipt),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert run.returncode == 0, run.stderr
        result = json.loads(receipt.read_text())
        assert result["export_accepted"] is True and result["indexed_verified"] is False
        assert receiver.spans()[0].trace_id.hex() == result["trace_id"]
        assert "PRIVATE_WRITE_KEY" not in run.stdout + run.stderr + str(receiver.payloads)
        assert receipt.stat().st_mode & 0o777 == 0o600


def test_bundle_does_not_change_credentials_and_compose_preserves_literal_values(tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "runtime").mkdir(parents=True)
    (bundle / "bundle.json").write_text('{"project":"deermate-observability-check"}')
    (bundle / "compose.yaml").write_text(
        yaml.safe_dump(
            {
                "services": {
                    "control": {"image": "test", "env_file": ["control.env"]},
                    "gateway": {"image": "test"},
                }
            }
        )
    )
    secret = bundle / "control.env"
    secret.write_text("AUTH_JWT_SECRET=unchanged-secret\n")
    # $, apostrophe, quotes and backslash must survive Compose's dotenv parser.
    key = "Auth=PRIVATE$KEY'\\suffix\"quoted"
    cli.configure_bundle(bundle, {**profile(), "OTEL_EXPORTER_OTLP_HEADERS": key})
    assert secret.read_text() == "AUTH_JWT_SECRET=unchanged-secret\n"
    assert (bundle / "observability.env").stat().st_mode & 0o777 == 0o600
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose is required for actual dotenv contract")
    run = subprocess.run(
        [str(docker), "compose", "-f", str(bundle / "compose.yaml"), "config", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert run.returncode == 0, run.stderr
    # Compose serializes literal dollars as $$ so its normalized file is reusable.
    actual = json.loads(run.stdout)["services"]["control"]["environment"][
        "OTEL_EXPORTER_OTLP_HEADERS"
    ]
    assert actual == key.replace("$", "$$")


@pytest.mark.asyncio
async def test_unreachable_exporter_does_not_change_worker_execution(settings, monkeypatch, caplog):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    endpoint = f"http://127.0.0.1:{sock.getsockname()[1]}/v1/traces?key=PRIVATE_ENDPOINT_KEY"
    sock.close()
    monkeypatch.setattr(telemetry, "_provider", None)
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setattr(telemetry, "_export_failures", 0)
    monkeypatch.setenv("DEERMATE_TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", endpoint)
    app = create_app(settings, token="x" * 48)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": "Bearer " + "x" * 48},
            ) as client:
                body = {
                    "project_id": "demo",
                    "prompt": "fix PRIVATE_PROMPT",
                    "idempotency_key": "outage-once",
                }
                one = (await client.post("/tasks", json=body)).json()
                duplicate = (await client.post("/tasks", json=body)).json()
                assert one["task_id"] == duplicate["task_id"]
                async with asyncio.timeout(10):
                    while True:
                        final = (await client.get("/tasks/" + one["task_id"])).json()
                        if final["status"] in {"completed", "failed"}:
                            break
                        await asyncio.sleep(0.02)
                assert (
                    final["status"] == "completed"
                    and final["result"]["validation_status"] == "passed"
                )
                assert len(app.state.worker.store.list_tasks()) == 1
        telemetry.shutdown()
        assert telemetry._export_failures > 0
        assert "PRIVATE_ENDPOINT_KEY" not in caplog.text and "PRIVATE_PROMPT" not in caplog.text
    finally:
        if telemetry._provider:
            telemetry._provider.shutdown()
