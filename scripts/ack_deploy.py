#!/usr/bin/env python3
"""Prepare/build/render/install a single-owner DeerMate control plane on ACK.

No cluster is accessed until deploy/status/open. Run with the deploy extra.
"""

import argparse
import base64
import copy
import io
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path

import yaml

from deermate.remote_config import SSHWorker

ROOT = Path(__file__).resolve().parents[1]
PIN = "a1b89d0432de4e45adc59f512cb25bb386ea1e51"
DEFAULT_CONFIG = ROOT / ".deermate/ack/config.yaml"
CHART = "deploy/helm/deer-flow"
NAME = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")
PRIVATE_FILES = ("client.key", "known_hosts", "api.token")
COPY_CREDENTIALS = """import os
from pathlib import Path
os.umask(0o077)
target = Path('/worker-credentials/private')
target.mkdir(mode=0o700, exist_ok=True)
target.chmod(0o700)
for name in ('client.key', 'known_hosts', 'api.token'):
    path = target / name
    path.write_bytes((Path('/credential-source') / name).read_bytes())
    path.chmod(0o600)
"""


class DeploymentError(Exception):
    pass


def command(argv, *, capture=False, data=None, env=None, cwd=None, quiet=False):
    result = subprocess.run(
        [str(arg) for arg in argv],
        input=data,
        text=True,
        env=env,
        cwd=cwd,
        stdout=subprocess.PIPE if capture or quiet else None,
        stderr=subprocess.PIPE if quiet else None,
    )
    if result.returncode:
        # Do not echo secret-bearing subprocess input, arguments or responses.
        raise DeploymentError(f"{Path(argv[0]).name} failed (exit {result.returncode}).")
    return result.stdout or ""


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(text)
    path.chmod(0o600)


def load(path):
    settings = yaml.safe_load(path.read_text())
    if not isinstance(settings, dict):
        raise DeploymentError("Configuration must be a mapping.")
    expected = {
        "registry",
        "tag",
        "kube_context",
        "namespace",
        "release",
        "platform",
        "storage_class",
        "image_pull_secret",
        "model",
        "worker",
    }
    if set(settings) != expected:
        raise DeploymentError("Use the generated config schema; unknown/missing fields detected.")
    for key in ("namespace", "release", "image_pull_secret", "storage_class"):
        if not isinstance(settings[key], str) or not NAME.fullmatch(settings[key]):
            raise DeploymentError(f"Invalid Kubernetes name: {key}.")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.:-]*/[a-z0-9][a-z0-9_/-]*", settings["registry"]):
        raise DeploymentError("registry must be an ACR registry/namespace, without credentials.")
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}", settings["tag"]):
        raise DeploymentError("Invalid image tag.")
    if settings["tag"] == "latest":
        raise DeploymentError("Choose a versioned image tag, not latest.")
    if settings["platform"] not in {"linux/amd64", "linux/arm64"}:
        raise DeploymentError("platform must be linux/amd64 or linux/arm64.")
    context = settings["kube_context"]
    if not isinstance(context, str) or not context or context.startswith("-"):
        raise DeploymentError("An explicit kube_context is required.")
    model = settings["model"]
    if not isinstance(model, dict) or set(model) != {"model", "base_url"}:
        raise DeploymentError(
            "model requires model and base_url; API keys belong in private files."
        )
    if not isinstance(model["model"], str) or not model["model"]:
        raise DeploymentError("A model ID is required.")
    from urllib.parse import urlsplit

    endpoint = urlsplit(model["base_url"])
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
    ):
        raise DeploymentError("Model base_url must be HTTPS without credentials/query/fragment.")
    worker = settings["worker"]
    if not isinstance(worker, dict) or not isinstance(worker.get("enabled"), bool):
        raise DeploymentError("worker.enabled must be a boolean.")
    if worker["enabled"]:
        enrollment(settings).admit()
    return settings


def enrollment(settings):
    return SSHWorker.model_validate(
        {
            **settings["worker"],
            "known_hosts": "/var/run/deermate/known_hosts",
            "client_key": "/var/run/deermate/client.key",
            "token_file": "/var/run/deermate/api.token",
        }
    )


def controller(settings):
    worker = enrollment(settings).model_dump(mode="json", exclude_none=True)
    return "[workers.home]\n" + "".join(
        f"{key} = {json.dumps(value)}\n" for key, value in worker.items()
    )


def app_config(settings):
    return {
        "config_version": 62,
        "models": [
            {
                "name": "secretary",
                "display_name": "Secretary",
                "use": "langchain_openai:ChatOpenAI",
                **settings["model"],
                "api_key": "$DEERMATE_MODEL_API_KEY",
            }
        ],
        "database": {"backend": "sqlite", "sqlite_dir": "/app/backend/.deer-flow/data"},
        "checkpointer": {
            "type": "sqlite",
            "connection_string": "/app/backend/.deer-flow/data/checkpoints.db",
        },
        "stream_bridge": {"type": "memory"},
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
        "tools": [],
        "tool_groups": [],
        "memory": {"enabled": False},
        "scheduler": {"enabled": False},
        "title": {"enabled": False},
        "suggestions": {"enabled": False},
        "mcp_tasks": {
            "enabled": True,
            "poll_interval_seconds": 5,
            "lease_seconds": 120,
            "max_concurrent_polls": 4,
        },
    }


def values(settings):
    extensions = json.loads((ROOT / "examples/deerflow.ssh.extensions.json").read_text())
    server = extensions["mcpServers"]["deermate-home"]
    server.update(
        {
            "enabled": settings["worker"]["enabled"],
            "command": "/app/backend/.venv/bin/python",
            "cwd": "/app/backend",
            "args": [
                "-m",
                "deermate.cli",
                "--config",
                "/etc/deermate/controller.toml",
                "--worker",
                "home",
                "mcp",
            ],
        }
    )
    if settings["worker"].get("passphrase_env"):
        variable = settings["worker"]["passphrase_env"]
        server["env"] = {variable: f"${variable}"}
    return {
        "namespace": settings["namespace"],
        "image": {
            "registry": settings["registry"],
            "tag": settings["tag"],
            "gatewayImage": "deermate-gateway",
            "frontendImage": "deermate-frontend",
            "pullSecrets": [{"name": settings["image_pull_secret"]}],
        },
        "gateway": {
            "replicas": 1,
            "multiInstance": False,
            "strategy": {"type": "Recreate", "rollingUpdate": None},
        },
        "provisioner": {"enabled": False},
        "postgresql": {"enabled": False},
        "redis": {"enabled": False},
        "ingress": {"enabled": False},
        "nginx": {
            "service": {"type": "ClusterIP"},
            "image": {
                "repository": settings["registry"] + "/deermate-nginx",
                "tag": settings["tag"],
            },
        },
        "persistence": {
            "home": {
                "enabled": True,
                "storageClass": settings["storage_class"],
                "accessMode": "ReadWriteOnce",
                "size": "20Gi",
            }
        },
        "existingSecret": settings["release"] + "-provider",
        "config": yaml.safe_dump(app_config(settings), sort_keys=False),
        "extensionsConfig": json.dumps(extensions),
    }


def post_render(documents, settings, rollout="review"):
    """Add narrow deployment hooks and fail closed on unexpected chart output."""
    documents = copy.deepcopy([doc for doc in documents if doc])
    gateway = []
    for doc in documents:
        kind = doc["kind"]
        metadata = doc["metadata"]
        if metadata.get("namespace") != settings["namespace"]:
            raise DeploymentError(
                "Rendered resource namespace does not match the selected namespace."
            )
        if kind in {"Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding", "Ingress"}:
            raise DeploymentError(
                "The quick profile does not grant execution RBAC or public ingress."
            )
        if kind == "Service" and doc["spec"].get("type", "ClusterIP") != "ClusterIP":
            raise DeploymentError("The quick profile requires private ClusterIP services.")
        if kind == "PersistentVolumeClaim" or kind == "Secret":
            metadata.setdefault("annotations", {})["helm.sh/resource-policy"] = "keep"
        if kind == "PersistentVolumeClaim":
            volume = doc["spec"]
            if (
                volume.get("storageClassName") != settings["storage_class"]
                or volume.get("accessModes") != ["ReadWriteOnce"]
                or volume["resources"]["requests"]["storage"] != "20Gi"
            ):
                raise DeploymentError("The quick profile requires its 20Gi RWO cloud-disk claim.")
        if kind == "ConfigMap" and "config.yaml" in doc.get("data", {}):
            config = yaml.safe_load(doc["data"]["config.yaml"])
            if config != app_config(settings):
                raise DeploymentError(
                    "Unexpected app config; use the reviewed single-owner profile."
                )
        if kind != "Deployment":
            continue
        component = metadata.get("labels", {}).get("app.kubernetes.io/component")
        if component not in {"gateway", "frontend", "nginx"}:
            raise DeploymentError("Unexpected deployment in the quick profile.")
        pod = doc["spec"]["template"]["spec"]
        pod["automountServiceAccountToken"] = False
        pod.setdefault("nodeSelector", {})["kubernetes.io/arch"] = settings["platform"].split("/")[
            1
        ]
        pod["imagePullSecrets"] = [{"name": settings["image_pull_secret"]}]
        if component != "gateway":
            continue
        gateway.append(doc)
        if doc["spec"]["replicas"] != 1 or doc["spec"]["strategy"] != {"type": "Recreate"}:
            raise DeploymentError("SQLite requires exactly one Gateway and Recreate updates.")
        if pod["securityContext"].get("runAsUser") != 1000:
            raise DeploymentError(
                "Credential ownership requires the reviewed non-root Gateway UID."
            )
        annotations = doc["spec"]["template"]["metadata"].setdefault("annotations", {})
        annotations["deermate.io/deployment-generation"] = rollout
        for container in pod.get("initContainers", []):
            container["image"] = settings["registry"] + "/deermate-tools:" + settings["tag"]
            if container["name"] == "init-extensions":
                container["args"] = [
                    "set -eu; cp /extensions-seed/extensions_config.json "
                    "/extensions-runtime/extensions_config.json"
                ]
        if not settings["worker"]["enabled"]:
            continue
        container = next(item for item in pod["containers"] if item["name"] == "gateway")
        pod["volumes"].extend(
            [
                {
                    "name": "worker-source",
                    "secret": {"secretName": settings["release"] + "-worker", "defaultMode": 0o440},
                },
                {"name": "worker-credentials", "emptyDir": {"medium": "Memory"}},
                {
                    "name": "worker-controller",
                    "configMap": {"name": settings["release"] + "-worker-controller"},
                },
            ]
        )
        pod["initContainers"].append(
            {
                "name": "init-worker-credentials",
                "image": container["image"],
                "command": ["/app/backend/.venv/bin/python", "-c", COPY_CREDENTIALS],
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                },
                "volumeMounts": [
                    {"name": "worker-source", "mountPath": "/credential-source", "readOnly": True},
                    {"name": "worker-credentials", "mountPath": "/worker-credentials"},
                ],
            }
        )
        container["volumeMounts"].extend(
            [
                {
                    "name": "worker-credentials",
                    "mountPath": "/var/run/deermate",
                    "subPath": "private",
                    "readOnly": True,
                },
                {"name": "worker-controller", "mountPath": "/etc/deermate", "readOnly": True},
            ]
        )
    if len(gateway) != 1:
        raise DeploymentError("Expected exactly one pinned-chart Gateway deployment.")
    if settings["worker"]["enabled"]:
        documents.append(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": settings["release"] + "-worker-controller",
                    "namespace": settings["namespace"],
                },
                "data": {"controller.toml": controller(settings)},
            }
        )
    return documents


def prepare(work):
    checkout = work / "deer-flow"
    if not checkout.exists():
        command(["git", "init", "--quiet", checkout])
        command(
            [
                "git",
                "-C",
                checkout,
                "remote",
                "add",
                "origin",
                "https://github.com/bytedance/deer-flow.git",
            ]
        )
        (checkout / ".git/deermate-pin").write_text(PIN)
    try:
        head = command(["git", "-C", checkout, "rev-parse", "HEAD"], quiet=True).strip()
    except DeploymentError:
        if not (checkout / ".git/deermate-pin").exists():
            raise DeploymentError(
                "Incomplete unmanaged checkout; choose a fresh workspace."
            ) from None
        command(["git", "-C", checkout, "fetch", "--depth=1", "origin", PIN])
        command(["git", "-C", checkout, "checkout", "--detach", PIN])
        head = PIN
    dirty = command(["git", "-C", checkout, "status", "--porcelain"], capture=True)
    if head != PIN or dirty:
        raise DeploymentError("Deployment checkout must be clean at the pinned DeerFlow commit.")
    return checkout


def check_helm():
    version = command(["helm", "version", "--template", "{{.Version}}"], capture=True)
    if not re.match(r"v3\.(?:1[89]|[2-9][0-9])\.", version):
        raise DeploymentError("This package is tested with Helm 3.18+ (3.x); use Helm 3.")


def private_file(path, *, limit=128_000):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or not 0 < info.st_size <= limit:
        raise DeploymentError(
            f"Private file must be a nonempty owner-only regular file: {path.name}."
        )
    return path.read_bytes()


def secret_manifests(settings, config_path):
    credentials = config_path.parent / "credentials"
    provider = {"DEERMATE_MODEL_API_KEY": private_file(credentials / "model-key").decode().strip()}
    if not provider["DEERMATE_MODEL_API_KEY"]:
        raise DeploymentError("Model API key file is empty after whitespace removal.")
    result = []
    if settings["worker"]["enabled"]:
        data = {name: private_file(credentials / name) for name in PRIVATE_FILES}
        token = data["api.token"].decode().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
            raise DeploymentError("Invalid Worker token file.")
        result.append(secret(settings["release"] + "-worker", settings, data))
        variable = settings["worker"].get("passphrase_env")
        if variable:
            if variable != "DEERMATE_SSH_KEY_PASSPHRASE":
                raise DeploymentError(
                    "Use DEERMATE_SSH_KEY_PASSPHRASE for the optional key passphrase."
                )
            provider[variable] = private_file(credentials / "passphrase").decode().rstrip("\r\n")
    result.append(
        secret(
            settings["release"] + "-provider",
            settings,
            {key: value.encode() for key, value in provider.items()},
        )
    )
    return result


def secret(name, settings, data):
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {"name": name, "namespace": settings["namespace"]},
        "data": {key: base64.b64encode(value).decode() for key, value in data.items()},
    }


def render_files(settings, config_path):
    work = config_path.parent
    checkout = prepare(work)
    check_helm()
    values_file = work / "values.generated.json"
    private_write(values_file, json.dumps(values(settings), indent=2))
    renderer = work / "post-renderer"
    private_write(
        renderer,
        "#!/bin/sh\nexec "
        + shlex.join(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--config",
                str(config_path),
                "post-render",
            ]
        )
        + "\n",
    )
    renderer.chmod(0o700)
    return checkout, values_file, renderer


def kubectl(settings, *args, **kwargs):
    return command(
        [
            "kubectl",
            "--context",
            settings["kube_context"],
            "--namespace",
            settings["namespace"],
            *args,
        ],
        **kwargs,
    )


def registry_secret(settings, username, password_file):
    import getpass

    password = (
        private_file(password_file).decode().rstrip("\r\n")
        if password_file
        else getpass.getpass("ACR registry password: ")
    )
    if not username or not password:
        raise DeploymentError("ACR username and password are required.")
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    payload = {
        "auths": {
            settings["registry"].split("/")[0]: {
                "username": username,
                "password": password,
                "auth": auth,
            }
        }
    }
    manifest = secret(
        settings["image_pull_secret"], settings, {".dockerconfigjson": json.dumps(payload).encode()}
    )
    manifest["type"] = "kubernetes.io/dockerconfigjson"
    namespace = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": settings["namespace"]},
    }
    kubectl(settings, "apply", "-f", "-", data=json.dumps(namespace), quiet=True)
    kubectl(settings, "apply", "-f", "-", data=json.dumps(manifest), quiet=True)
    print("ACR pull Secret installed in the selected namespace.")


def deploy(settings, config_path):
    # Validate every local input before the first cluster mutation.
    for key in ("registry", "tag", "kube_context"):
        if "REPLACE" in settings[key]:
            raise DeploymentError(f"Fill in {key} before deploying.")
    if "REPLACE" in json.dumps(settings["model"]):
        raise DeploymentError("Configure a tool-calling model ID and HTTPS endpoint first.")
    secrets = secret_manifests(settings, config_path)
    checkout, values_file, renderer = render_files(settings, config_path)
    storage = json.loads(
        kubectl(
            settings, "get", "storageclass", settings["storage_class"], "--output=json", quiet=True
        )
    )
    if storage.get("provisioner") != "diskplugin.csi.alibabacloud.com":
        raise DeploymentError(
            "Use an ACK cloud-disk CSI StorageClass; SQLite is not placed on NAS."
        )
    # Creating a missing namespace is idempotent; never print a Secret manifest.
    namespace = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": settings["namespace"]},
    }
    kubectl(settings, "apply", "-f", "-", data=json.dumps(namespace), quiet=True)
    kubectl(settings, "get", "secret", settings["image_pull_secret"], quiet=True)
    for item in secrets:
        kubectl(settings, "apply", "-f", "-", data=json.dumps(item), quiet=True)
    # Force copied Secret refresh even when values/config did not change.
    env = {**os.environ, "DEERMATE_ACK_ROLLOUT": uuid.uuid4().hex}
    command(
        [
            "helm",
            "upgrade",
            "--install",
            settings["release"],
            checkout / CHART,
            "--kube-context",
            settings["kube_context"],
            "--namespace",
            settings["namespace"],
            "--values",
            values_file,
            "--post-renderer",
            renderer,
            "--atomic",
            "--wait",
            "--timeout",
            "10m",
            "--history-max",
            "5",
        ],
        env=env,
    )
    print("Control plane installed. Run the open command for private first-user setup.")


def build(settings, config_path, push):
    checkout = prepare(config_path.parent)
    with tempfile.TemporaryDirectory(prefix="ack-build-", dir=config_path.parent) as temp:
        context = Path(temp)
        # Only committed upstream files enter the build context, never operator state.
        archive = subprocess.check_output(["git", "-C", str(checkout), "archive", PIN])
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(context, filter="data")
        wheel_dir = context / "deermate-wheel"
        command([sys.executable, "-m", "build", "--wheel", "--outdir", wheel_dir, ROOT])
        gateway_file = context / "Dockerfile.deermate"
        gateway_file.write_text(
            (context / "backend/Dockerfile").read_text()
            + "\n"
            + (ROOT / "deploy/ack/gateway-layer.dockerfile").read_text()
        )
        with (context / ".dockerignore").open("a") as ignore:
            ignore.write("\n!deermate-wheel/\n!deermate-wheel/*.whl\n")
        output = "--push" if push else "--load"
        for name, dockerfile, target in [
            ("gateway", gateway_file, None),
            ("frontend", context / "frontend/Dockerfile", "prod"),
        ]:
            argv = [
                "docker",
                "buildx",
                "build",
                "--platform",
                settings["platform"],
                "--file",
                dockerfile,
                "--tag",
                f"{settings['registry']}/deermate-{name}:{settings['tag']}",
                output,
            ]
            if target:
                argv.extend(["--target", target])
            command([*argv, context])
        # Mirror the two helper images too, so ACK need not pull Docker Hub.
        for name, image in [("nginx", "nginx:1.28-alpine"), ("tools", "busybox:1.36")]:
            (context / f"Dockerfile.{name}").write_text(f"FROM {image}\n")
            command(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--platform",
                    settings["platform"],
                    "--file",
                    context / f"Dockerfile.{name}",
                    "--tag",
                    f"{settings['registry']}/deermate-{name}:{settings['tag']}",
                    output,
                    context,
                ]
            )
    print("Images pushed." if push else "Images loaded locally; use build --push for ACR.")


def initialize(path, registry, context, tag):
    if path.exists():
        raise DeploymentError("Config already exists; edit it in place instead of overwriting it.")
    settings = yaml.safe_load((ROOT / "deploy/ack/config.example.yaml").read_text())
    settings.update({"registry": registry, "kube_context": context, "tag": tag})
    private_write(path, yaml.safe_dump(settings, sort_keys=False))
    credentials = path.parent / "credentials"
    credentials.mkdir(mode=0o700)
    print(f"Created {path}; put private files under its credentials directory.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.version_info < (3, 12):
        parser.error("ACK deployment tooling requires Python 3.12+; Worker supports Python 3.11+.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init", help="create ignored configuration; never overwrite")
    init.add_argument("--registry", required=True, help="ACR registry/namespace")
    init.add_argument("--context", required=True, help="explicit ACK kubeconfig context")
    init.add_argument(
        "--tag",
        default="dm-"
        + command(["git", "-C", ROOT, "rev-parse", "--short=12", "HEAD"], capture=True).strip(),
    )
    sub.add_parser("prepare", help="fetch the pinned unchanged upstream checkout")
    image = sub.add_parser("build", help="build Gateway/UI/helper images; no cluster calls")
    image.add_argument("--push", action="store_true", help="push to configured registry")
    sub.add_parser("render", help="print review YAML with all Secret data redacted")
    sub.add_parser("post-render", help=argparse.SUPPRESS)
    sub.add_parser("deploy", help="install/upgrade the selected ACK context")
    sub.add_parser("model-key", help="prompt and save the model key in a private local file")
    registry = sub.add_parser(
        "registry-secret", help="install ACR pull credentials; password prompted"
    )
    registry.add_argument("--username", required=True)
    registry.add_argument("--password-file", type=Path)
    sub.add_parser("status", help="read deployment/PVC status")
    sub.add_parser("open", help="localhost-only kubectl port-forward on port 2026")
    sub.add_parser("probe-worker", help="read enrolled Worker capabilities from the Gateway Pod")
    args = parser.parse_args()
    path = args.config.absolute()
    try:
        if args.action == "init":
            initialize(path, args.registry, args.context, args.tag)
            return
        settings = load(path)
        if args.action == "prepare":
            print(prepare(path.parent))
        elif args.action == "build":
            build(settings, path, args.push)
        elif args.action == "post-render":
            documents = post_render(
                yaml.safe_load_all(sys.stdin),
                settings,
                os.environ.get("DEERMATE_ACK_ROLLOUT", "review"),
            )
            sys.stdout.write(yaml.safe_dump_all(documents, sort_keys=False))
        elif args.action == "render":
            checkout, values_file, renderer = render_files(settings, path)
            output = command(
                [
                    "helm",
                    "template",
                    settings["release"],
                    checkout / CHART,
                    "--namespace",
                    settings["namespace"],
                    "--values",
                    values_file,
                    "--post-renderer",
                    renderer,
                ],
                capture=True,
            )
            documents = list(yaml.safe_load_all(output))
            for doc in documents:
                if doc and doc["kind"] == "Secret":
                    doc["data"] = {key: "REDACTED" for key in doc.get("data", {})}
                    doc["stringData"] = {key: "REDACTED" for key in doc.get("stringData", {})}
            print("# Review only: Secret values redacted; deploy uses Helm directly.")
            print(yaml.safe_dump_all(documents, sort_keys=False))
        elif args.action == "deploy":
            deploy(settings, path)
        elif args.action == "model-key":
            import getpass

            key = getpass.getpass("Model API key: ").strip()
            if not key:
                raise DeploymentError("Model key cannot be empty.")
            private_write(path.parent / "credentials/model-key", key + "\n")
            print("Model key saved locally; run deploy to update the cluster Secret.")
        elif args.action == "registry-secret":
            registry_secret(settings, args.username, args.password_file)
        elif args.action == "status":
            kubectl(settings, "get", "deployments,pods,services,pvc")
        elif args.action == "open":
            kubectl(settings, "port-forward", "--address=127.0.0.1", "service/nginx", "2026:2026")
        elif args.action == "probe-worker":
            if not settings["worker"]["enabled"]:
                raise DeploymentError("Enable and deploy the Worker enrollment first.")
            kubectl(
                settings,
                "exec",
                f"deployment/{settings['release']}-deer-flow-gateway",
                "--container=gateway",
                "--",
                "/app/backend/.venv/bin/python",
                "-m",
                "deermate.cli",
                "--config",
                "/etc/deermate/controller.toml",
                "--worker",
                "home",
                "capabilities",
            )
    except (DeploymentError, OSError, ValueError) as error:
        # Validation errors can contain user input; do not dump pydantic values.
        if isinstance(error, DeploymentError):
            print(f"Deployment error: {error}", file=sys.stderr)
        else:
            print(
                f"Deployment error ({type(error).__name__}); check configuration/files/tools.",
                file=sys.stderr,
            )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
