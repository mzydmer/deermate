"""The budget target must retain the private Go boundary and exclude desktop authority."""

import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from scripts import single_host


def test_single_host_budget_and_private_boundary():
    config = single_host.compose("budget-test", 12027)
    services = config["services"]
    running = [s for name, s in services.items() if name != "init"]
    assert sum(int(s["mem_limit"][:-1]) for s in running) == 1472
    assert sum(s["cpus"] for s in running) == 2
    assert [(name, s["ports"]) for name, s in services.items() if s.get("ports")] == [
        ("nginx", ["127.0.0.1:12027:2026"])
    ]
    for service in running:
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert not service.get("privileged")
        assert all(not mount.startswith(("/", "~")) for mount in service["volumes"])
        assert service["mem_limit"] == service["memswap_limit"]
    assert services["control"]["env_file"] == ["control.env"]
    assert services["control"]["environment"]["DEERMATE_RUNTIME_URL"] == "http://gateway:8001"
    assert (
        services["frontend"]["environment"]["DEER_FLOW_INTERNAL_GATEWAY_BASE_URL"]
        == "http://control:8080"
    )
    assert "credentials" not in config["volumes"]
    text = json.dumps(config)
    assert "local_gateway.py" not in text
    assert "host.docker.internal" not in text
    assert "docker.sock" not in text


def test_prepare_never_overwrites_bundle_secrets(tmp_path, monkeypatch):
    output = tmp_path / "existing"
    output.mkdir()
    secret = output / "runtime.env"
    secret.write_text("keep-existing-secret")
    monkeypatch.setattr(single_host.ack, "load", lambda _: {})
    with pytest.raises(single_host.ack.DeploymentError, match="already exists"):
        single_host.prepare(Path("unused"), output, "budget-test", 12027)
    assert secret.read_text() == "keep-existing-secret"


def test_actual_bundle_has_no_host_credentials(tmp_path, monkeypatch):
    upstream = os.environ.get("DEERMATE_ACK_UPSTREAM")
    helm = os.environ.get("DEERMATE_HELM") or shutil.which("helm")
    if not upstream or not helm:
        pytest.skip("Set DEERMATE_ACK_UPSTREAM and DEERMATE_HELM for bundle rendering")
    monkeypatch.setenv("PATH", str(Path(helm).parent) + os.pathsep + os.environ["PATH"])
    monkeypatch.setattr(single_host.ack, "prepare", lambda _: Path(upstream))
    settings = yaml.safe_load((single_host.ack.ROOT / "deploy/ack/config.example.yaml").read_text())
    settings.update(registry="registry.example.invalid/owner", tag="test-123")
    images = tmp_path / "images.yaml"
    images.write_text(yaml.safe_dump(settings))
    (tmp_path / "credentials").mkdir()
    (tmp_path / "credentials/model-key").write_text("never-copy-test-model-secret")
    output = tmp_path / "bundle"
    single_host.prepare(images, output, "budget-test", 12027)
    content = "\n".join(p.read_text() for p in output.rglob("*") if p.is_file())
    assert "never-copy-test-model-secret" not in content
    assert "DEERMATE_LOCAL_VERIFICATION_KEY" not in content
    assert "local_gateway.py" not in content
    assert str(tmp_path) not in content
    assert yaml.safe_load((output / "runtime/config.yaml").read_text())["models"] == []
    assert json.loads((output / "runtime/extensions_config.json").read_text())["mcpServers"] == {}
    for name in (".env", "runtime.env", "control.env", "frontend.env"):
        assert (output / name).stat().st_mode & 0o777 == 0o600
    control_secret = (output / "control.env").read_text()
    assert control_secret in (output / "runtime.env").read_text()
    assert "INTERNAL_AUTH" not in control_secret
    assert "server control:8080;" in (output / "runtime/nginx.conf").read_text()
