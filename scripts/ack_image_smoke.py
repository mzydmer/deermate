"""Probe the built ACK Gateway image as UID 1000, without a cluster/model call."""

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import yaml
from ack_deploy import COPY_CREDENTIALS, app_config, command, load


def run(image, settings, receipt):
    with tempfile.TemporaryDirectory(prefix="ack-image-") as temp:
        directory = Path(temp)
        directory.chmod(0o755)
        fixtures = directory / "credentials"
        fixtures.mkdir(mode=0o755)
        for name in ("client.key", "known_hosts", "api.token"):
            (fixtures / name).write_text("offline-credential-fixture")
            (fixtures / name).chmod(0o644)
        # Simulate a root-owned fsGroup-writable volume: UID 1000 cannot chmod
        # the mount root, and must create its own private subdirectory.
        command(
            [
                "docker",
                "run",
                "--rm",
                "--user=1000:1000",
                "--cap-drop=ALL",
                "--tmpfs=/worker-credentials:uid=0,gid=1000,mode=0770",
                "--mount",
                f"type=bind,source={fixtures},target=/credential-source,readonly",
                "--entrypoint=/app/backend/.venv/bin/python",
                image,
                "-c",
                COPY_CREDENTIALS + "\nfrom deermate.ssh import _read_file\n"
                "expected=b'offline-credential-fixture'\n"
                "assert _read_file(target/'client.key', private=True)==expected\n",
            ]
        )
        for name, content in {
            "config.yaml": yaml.safe_dump(app_config(settings)),
            "extensions.json": '{"mcpServers":{},"skills":{}}',
            "empty.env": "",
        }.items():
            (directory / name).write_text(content)
            (directory / name).chmod(0o644)
        argv = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--user=1000:1000",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--publish=127.0.0.1::8001",
            "--tmpfs=/app/backend/.deer-flow:uid=1000,gid=1000,mode=0700",
            "--env=PYTHONDONTWRITEBYTECODE=1",
            "--env=UV_CACHE_DIR=/tmp/uv",
            "--env=DEER_FLOW_PROJECT_ROOT=/app",
            "--env=DEER_FLOW_HOME=/app/backend/.deer-flow",
            "--env=DEER_FLOW_CONFIG_PATH=/app/config.yaml",
            "--env=DEER_FLOW_ENV_FILE=/app/empty.env",
            "--env=DEER_FLOW_EXTENSIONS_CONFIG_PATH=/app/extensions.json",
            "--env=DEERMATE_MODEL_API_KEY=offline-image-fixture",
            "--env=DEER_FLOW_INTERNAL_AUTH_TOKEN=offline-internal-fixture",
            "--env=AUTH_JWT_SECRET=offline-session-fixture-at-least-32-characters",
        ]
        for name in ("config.yaml", "extensions.json", "empty.env"):
            argv.extend(
                ["--mount", f"type=bind,source={directory / name},target=/app/{name},readonly"]
            )
        container = command([*argv, image], capture=True).strip()
        try:
            port = command(["docker", "port", container, "8001/tcp"], capture=True).strip()
            with httpx.Client(base_url="http://" + port, trust_env=False, timeout=5) as client:
                ready = False
                for _ in range(120):
                    try:
                        ready = client.get("/health/ready").status_code == 200
                    except httpx.TransportError:
                        pass
                    if ready:
                        break
                    if (
                        command(
                            ["docker", "inspect", "--format={{.State.Running}}", container],
                            capture=True,
                        ).strip()
                        != "true"
                    ):
                        raise RuntimeError("Gateway container exited before readiness")
                    time.sleep(1)
                if not ready:
                    raise RuntimeError("Gateway did not become ready")
                unauthenticated = client.get("/api/threads")
                if unauthenticated.status_code not in {401, 403}:
                    raise RuntimeError("Unauthenticated task access was not rejected")
            packages = json.loads(
                command(
                    [
                        "docker",
                        "exec",
                        container,
                        "/app/backend/.venv/bin/python",
                        "-c",
                        "import importlib.metadata as m,json; import deermate.mcp_server,asyncssh; "
                        "names=['deermate','mcp','asyncssh']; "
                        "print(json.dumps({n:m.version(n) for n in names}))",
                    ],
                    capture=True,
                )
            )
            digest = command(
                ["docker", "image", "inspect", "--format={{.Id}}", image], capture=True
            ).strip()
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "image_id": digest,
                        "packages": packages,
                        "uid": 1000,
                        "checks": [
                            "gateway_ready",
                            "unauthenticated_threads_rejected",
                            "mcp_ssh_imported",
                            "non_root_credential_copy",
                        ],
                        "limits": "Image only; no ACK/model/frontend login/home SSH test.",
                    },
                    indent=2,
                )
                + "\n"
            )
            print("Gateway ready as UID 1000; unauthenticated threads rejected; MCP/SSH import OK.")
        finally:
            subprocess.run(["docker", "logs", "--tail=60", container], check=False)
            subprocess.run(
                ["docker", "rm", "--force", container], check=False, stdout=subprocess.DEVNULL
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    run(args.image, load(args.config), args.receipt)
