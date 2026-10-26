"""Deployment admission, credentials, and actual pinned Helm-chart regression."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from deermate.ssh import _read_file
from scripts import ack_deploy as ack


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "config.yaml"
    ack.initialize(path, "registry.example.invalid/owner", "ack-test", "test-123")
    data = yaml.safe_load(path.read_text())
    data["model"] = {"model": "operator-selected-model", "base_url": "https://model.invalid/v1"}
    data["worker"].update(
        {
            "host": "worker.invalid",
            "expected_instance_id": "a" * 32,
            "expires_at": "2099-01-01T00:00:00Z",
        }
    )
    ack.private_write(path, yaml.safe_dump(data))
    return ack.load(path)


def gateway(settings):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "test-gateway",
            "namespace": settings["namespace"],
            "labels": {"app.kubernetes.io/component": "gateway"},
        },
        "spec": {
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "template": {
                "metadata": {},
                "spec": {
                    "securityContext": {"runAsUser": 1000},
                    "initContainers": [{"name": "init-extensions"}],
                    "containers": [
                        {"name": "gateway", "image": "test-gateway:123", "volumeMounts": []}
                    ],
                    "volumes": [],
                },
            },
        },
    }


@pytest.mark.parametrize("change", ["namespace", "replicas", "strategy", "uid", "rbac", "public"])
def test_reject_widened_or_overlapping_deployment(settings, change):
    document = gateway(settings)
    if change == "namespace":
        document["metadata"]["namespace"] = "other"
    elif change == "replicas":
        document["spec"]["replicas"] = 2
    elif change == "strategy":
        document["spec"]["strategy"] = {"type": "RollingUpdate"}
    elif change == "uid":
        document["spec"]["template"]["spec"]["securityContext"]["runAsUser"] = 0
    else:
        document = {
            "kind": "Role" if change == "rbac" else "Service",
            "metadata": {"namespace": settings["namespace"]},
            "spec": {"type": "LoadBalancer"},
        }
    with pytest.raises(ack.DeploymentError):
        ack.post_render([document], settings)


def test_reject_local_execution_toolset(settings):
    config = ack.app_config(settings)
    config["tools"] = [{"name": "bash", "use": "deerflow.sandbox.tools:bash_tool"}]
    document = {
        "kind": "ConfigMap",
        "metadata": {"namespace": settings["namespace"]},
        "data": {"config.yaml": yaml.safe_dump(config)},
    }
    with pytest.raises(ack.DeploymentError, match="Unexpected app config"):
        ack.post_render([document, gateway(settings)], settings)


def test_worker_init_copies_projected_symlinks_to_private_regular_files(tmp_path, settings):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"
    target.mkdir(mode=0o770)
    for name in ack.PRIVATE_FILES:
        real = source / ("real-" + name)
        real.write_bytes(b"known-fixture-data")
        (source / name).symlink_to(real)
    script = ack.COPY_CREDENTIALS.replace("/credential-source", str(source))
    script = script.replace("/worker-credentials", str(target))
    subprocess.run([sys.executable, "-c", script], check=True)
    target = target / "private"
    assert target.stat().st_mode & 0o777 == 0o700
    for name in ack.PRIVATE_FILES:
        assert not (target / name).is_symlink()
        assert (target / name).stat().st_mode & 0o777 == 0o600
        assert _read_file(target / name, private=True) == b"known-fixture-data"


@pytest.mark.parametrize("kind", ["public", "symlink"])
def test_private_input_rejects_exposed_or_linked_file(tmp_path, kind):
    path = tmp_path / "key"
    path.write_text("fixture-value")
    if kind == "public":
        path.chmod(0o644)
    else:
        path.chmod(0o600)
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    with pytest.raises(ack.DeploymentError):
        ack.private_file(path)


def test_registry_password_never_enters_argv_or_output(settings, tmp_path, monkeypatch, capsys):
    password = tmp_path / "password"
    ack.private_write(password, "fixture-registry-secret")
    calls = []

    def invoke(argv, **kwargs):
        calls.append((argv, kwargs))
        return ""

    monkeypatch.setattr(ack, "command", invoke)
    ack.registry_secret(settings, "fixture-user", password)
    assert len(calls) == 2
    assert all("--context" in call[0] and "ack-test" in call[0] for call in calls)
    assert all("fixture-registry-secret" not in json.dumps(call[0]) for call in calls)
    assert all(call[1]["quiet"] for call in calls)
    assert "fixture-registry-secret" not in capsys.readouterr().out


def test_model_secret_not_embedded_in_values_and_redeploy_refreshes_credentials(settings, tmp_path):
    settings["worker"]["enabled"] = True
    original = gateway(settings)
    result = ack.post_render([original], settings, "generation-1")
    assert original == gateway(settings)
    pod = result[0]["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["initContainers"][-1]["name"] == "init-worker-credentials"
    assert any(v.get("emptyDir", {}).get("medium") == "Memory" for v in pod["volumes"])
    mounts = pod["containers"][0]["volumeMounts"]
    assert all(mount["readOnly"] for mount in mounts)
    config_map = result[-1]
    assert "client_key" in config_map["data"]["controller.toml"]
    assert "DEERMATE_MODEL_API_KEY" in ack.values(settings)["config"]
    next_result = ack.post_render([original], settings, "generation-2")
    assert (
        result[0]["spec"]["template"]["metadata"] != next_result[0]["spec"]["template"]["metadata"]
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_actual_pinned_helm_chart(settings, tmp_path, enabled):
    checkout = os.environ.get("DEERMATE_ACK_UPSTREAM")
    helm = os.environ.get("DEERMATE_HELM") or shutil.which("helm")
    if not checkout or not helm:
        pytest.skip("Set DEERMATE_ACK_UPSTREAM and DEERMATE_HELM for actual-chart checks")
    head = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip()
    assert head == ack.PIN
    settings["worker"]["enabled"] = enabled
    values = tmp_path / "values.json"
    values.write_text(json.dumps(ack.values(settings)))
    raw = subprocess.check_output(
        [
            helm,
            "template",
            settings["release"],
            str(Path(checkout) / ack.CHART),
            "--namespace",
            settings["namespace"],
            "--values",
            str(values),
        ],
        text=True,
    )
    documents = ack.post_render(yaml.safe_load_all(raw), settings)
    deployments = [doc for doc in documents if doc["kind"] == "Deployment"]
    assert len(deployments) == 3
    assert not any(
        doc["kind"] in {"Role", "RoleBinding", "Ingress", "StatefulSet"} for doc in documents
    )
    pvc = next(doc for doc in documents if doc["kind"] == "PersistentVolumeClaim")
    assert pvc["spec"]["resources"]["requests"]["storage"] == "20Gi"
    assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    for document in deployments:
        pod = document["spec"]["template"]["spec"]
        assert pod["automountServiceAccountToken"] is False
        assert pod["imagePullSecrets"] == [{"name": settings["image_pull_secret"]}]
    application = next(
        doc
        for doc in documents
        if doc["kind"] == "ConfigMap" and "config.yaml" in doc.get("data", {})
    )
    config = yaml.safe_load(application["data"]["config.yaml"])
    assert config["database"]["backend"] == "sqlite"
    assert config["checkpointer"]["type"] == "sqlite"
    assert config["tools"] == []
    assert config["models"][0]["api_key"] == "$DEERMATE_MODEL_API_KEY"
