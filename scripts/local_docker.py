#!/usr/bin/env python3
"""Run the local Docker control plane and a host Codex Worker on a test project."""

import argparse
import io
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import yaml

if __package__:
    from . import ack_deploy as ack
else:
    import ack_deploy as ack

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".deermate/local-docker"
COMPOSE = ROOT / "deploy/local/compose.yaml"
URL = "http://localhost:2026"
PROMPT = (
    "Fix only answer.py so add(a, b) returns a + b. Do not change tests. "
    "Do not use network or external tools. Do not run tests: the Worker will run "
    "them separately. Make the one-line change and finish."
)


def wait(operation, condition, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = operation()
            if condition(value):
                return value
        except (httpx.TransportError, FileNotFoundError):
            pass
        time.sleep(0.3)
    raise ack.DeploymentError("Local verification deadline exceeded; inspect the local logs.")


def compose(*args, capture=False):
    return ack.command(
        [
            "docker",
            "compose",
            "--project-name",
            "deermate-local",
            "--file",
            COMPOSE,
            "--env-file",
            STATE / "compose.env",
            *args,
        ],
        capture=capture,
    )


def initialize(model):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile = STATE / "profile.json"
    if not profile.exists():
        codex = shutil.which("codex")
        if not codex:
            raise ack.DeploymentError("Install and sign in to Codex on the host first.")
        ack.private_write(
            profile,
            json.dumps({"model": model, "codex": codex, "worker_port": 18777, "ssh_port": 19822}),
        )
    elif model is not None and json.loads(profile.read_text())["model"] != model:
        raise ack.DeploymentError(
            "This profile already has a model; stop it before editing its policy."
        )
    images = STATE / "images.yaml"
    if not images.exists():
        revision = ack.command(
            ["git", "-C", ROOT, "rev-parse", "--short=12", "HEAD"], capture=True
        ).strip()
        ack.initialize(images, "deermate.local/runtime", "unused-local", "local-" + revision)
    cached = ROOT / ".deermate/ack/deer-flow"
    checkout = STATE / "deer-flow"
    if cached.is_dir() and not checkout.exists():
        checkout.symlink_to(cached, target_is_directory=True)
    checkout = ack.prepare(STATE)
    settings = ack.load(images)
    config_dir = STATE / "config"
    # Config files are deliberately readable by the non-root container UID;
    # their private parent directory contains no model/SSH secret literals.
    config_dir.mkdir(exist_ok=True, mode=0o755)
    (config_dir / "empty.env").touch()
    config = ack.app_config(settings)
    config["models"] = []
    (config_dir / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    (config_dir / "config.yaml").chmod(0o644)
    (config_dir / "empty.env").chmod(0o644)
    values = STATE / "nginx-values.json"
    ack.private_write(values, json.dumps(ack.values(settings)))
    rendered = ack.command(
        [
            "helm",
            "template",
            "deermate-local",
            checkout / ack.CHART,
            "--namespace",
            "deermate-local",
            "--values",
            values,
        ],
        capture=True,
    )
    nginx = next(
        doc["data"]["nginx.conf"]
        for doc in yaml.safe_load_all(rendered)
        if doc and doc["kind"] == "ConfigMap" and "nginx.conf" in doc.get("data", {})
    )
    (config_dir / "nginx.conf").write_text(nginx)
    (config_dir / "nginx.conf").chmod(0o644)
    if not (STATE / "runtime.env").exists():
        ack.private_write(
            STATE / "runtime.env",
            "".join(
                f"{name}={secrets.token_urlsafe(40)}\n"
                for name in [
                    "DEER_FLOW_INTERNAL_AUTH_TOKEN",
                    "AUTH_JWT_SECRET",
                    "DEERMATE_LOCAL_VERIFICATION_KEY",
                ]
            ),
        )
    if not (STATE / "frontend.env").exists():
        ack.private_write(
            STATE / "frontend.env", "BETTER_AUTH_SECRET=" + secrets.token_urlsafe(40) + "\n"
        )
    env = {"DEERMATE_STATE_DIR": str(STATE)}
    for name in ["gateway", "frontend", "nginx"]:
        env[f"DEERMATE_{name.upper()}_IMAGE"] = (
            f"{settings['registry']}/deermate-{name}:{settings['tag']}"
        )
    ack.private_write(
        STATE / "compose.env", "".join(f"{key}={value}\n" for key, value in env.items())
    )
    return json.loads(profile.read_text())


def owned(entry):
    probe = subprocess.run(
        ["ps", "-p", str(entry["pid"]), "-o", "command="], capture_output=True, text=True
    )
    started = subprocess.run(
        ["ps", "-p", str(entry["pid"]), "-o", "lstart="], capture_output=True, text=True
    )
    return (
        probe.returncode == 0
        and str(STATE) in probe.stdout
        and started.stdout.strip() == entry["started"]
    )


def native_start(name, argv):
    path = STATE / f"{name}.process.json"
    if path.exists() and owned(json.loads(path.read_text())):
        return
    log_path = STATE / f"{name}.log"
    ack.private_write(log_path, "")
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [str(value) for value in argv],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    started = subprocess.check_output(
        ["ps", "-p", str(process.pid), "-o", "lstart="], text=True
    ).strip()
    ack.private_write(path, json.dumps({"pid": process.pid, "started": started}))


def native_stop(name):
    path = STATE / f"{name}.process.json"
    if path.exists():
        entry = json.loads(path.read_text())
        if owned(entry):
            os.kill(entry["pid"], signal.SIGTERM)
            wait(lambda: owned(entry), lambda running: not running, timeout=30)
        path.unlink()


def host_worker(profile):
    repo = STATE / "demo-project"
    if not repo.exists():
        repo.mkdir()
        (repo / "answer.py").write_text("def add(a, b):\n    return a - b\n")
        (repo / "tests").mkdir()
        (repo / "tests/test_answer.py").write_text(
            "import unittest\nfrom answer import add\nclass Addition(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
        )
        (repo / ".gitignore").write_text("__pycache__/\n")
        for args in [
            ["init", "-q"],
            ["add", "."],
            [
                "-c",
                "user.name=Local fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
        ]:
            ack.command(["git", "-C", repo, *args])
    config = (
        f"state_dir = {json.dumps(str(STATE / 'worker'))}\n"
        f"codex_command = {json.dumps([profile['codex'], 'app-server'])}\n"
        "task_timeout_seconds = 180\n"
    )
    if profile["model"]:
        config += f"model = {json.dumps(profile['model'])}\n"
    validation_command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    config += (
        f"[projects.demo]\nroot = {json.dumps(str(repo))}\nallow_write = true\n"
        f"test_command = {json.dumps(validation_command)}\n"
    )
    ack.private_write(STATE / "worker.toml", config)
    native_start(
        "worker",
        [
            sys.executable,
            "-m",
            "deermate.cli",
            "--config",
            STATE / "worker.toml",
            "--port",
            str(profile["worker_port"]),
            "serve",
        ],
    )
    token = wait(lambda: (STATE / "worker/api.token").read_text().strip(), bool)
    with worker_client(profile, token) as client:
        identity = wait(
            lambda: client.get("/capabilities"), lambda response: response.status_code == 200
        )
    return token, identity.json()["instance_id"]


def worker_client(profile, token=None):
    token = token or (STATE / "worker/api.token").read_text().strip()
    return httpx.Client(
        base_url=f"http://127.0.0.1:{profile['worker_port']}",
        trust_env=False,
        timeout=10,
        headers={"Authorization": "Bearer " + token},
    )


def ssh_worker(profile, token, instance):
    import asyncssh

    directory = STATE / "ssh"
    directory.mkdir(exist_ok=True, mode=0o700)
    if not (directory / "host.key").exists():
        host = asyncssh.generate_private_key("ssh-ed25519")
        client = asyncssh.generate_private_key("ssh-ed25519")
        for name, data in {
            "host.key": host.export_private_key(),
            "client.key": client.export_private_key(),
            "client.pub": client.export_public_key(),
        }.items():
            ack.private_write(directory / name, data.decode())
    host = asyncssh.read_private_key(directory / "host.key")
    credentials = STATE / "credentials"
    credentials.mkdir(exist_ok=True, mode=0o700)
    for name, text in {
        "client.key": (directory / "client.key").read_text(),
        "api.token": token,
        "known_hosts": f"[host.docker.internal]:{profile['ssh_port']} "
        + host.export_public_key().decode(),
    }.items():
        ack.private_write(credentials / name, text)
    native_start(
        "ssh",
        [
            sys.executable,
            ROOT / "scripts/ssh_demo_fixture.py",
            "--state",
            directory,
            "--port",
            str(profile["ssh_port"]),
            "--worker-port",
            str(profile["worker_port"]),
        ],
    )
    wait(lambda: json.loads((directory / "stats.json").read_text()), lambda stats: stats["ready"])
    settings = ack.load(STATE / "images.yaml")
    settings["worker"].update(
        {
            "enabled": True,
            "host": "host.docker.internal",
            "port": profile["ssh_port"],
            "expected_instance_id": instance,
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "worker_port": profile["worker_port"],
        }
    )
    config = STATE / "config"
    (config / "controller.toml").write_text(ack.controller(settings))
    (config / "controller.toml").chmod(0o644)
    extensions = json.loads(ack.values(settings)["extensionsConfig"])
    extensions["mcpServers"]["deermate"] = extensions["mcpServers"].pop("deermate-home")
    (config / "extensions_config.json").write_text(json.dumps(extensions))
    (config / "extensions_config.json").chmod(0o644)


def ready():
    with httpx.Client(base_url=URL, trust_env=False, timeout=5) as client:
        wait(lambda: client.get("/health/ready"), lambda response: response.status_code == 200)


def stage_archive():
    """Package only explicit generated inputs; no host folder sharing is needed."""
    files = {
        name: (STATE / "config" / name).read_bytes()
        for name in [
            "config.yaml",
            "controller.toml",
            "extensions_config.json",
            "nginx.conf",
            "empty.env",
        ]
    }
    for name in ("local_gateway.py", "local_container_init.py"):
        files[name] = (ROOT / "scripts" / name).read_bytes()
    for name in ("client.key", "known_hosts", "api.token"):
        files["credentials/" + name] = ack.private_file(STATE / "credentials" / name)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        directory = tarfile.TarInfo("credentials")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o700
        archive.addfile(directory)
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o600 if name.startswith("credentials/") else 0o644
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


def upload_stage():
    settings = ack.load(STATE / "images.yaml")
    ack.command(["docker", "volume", "create", "deermate-local_stage"], capture=True)
    helper = ack.command(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--network=none",
            "--cap-drop=ALL",
            "--mount",
            "type=volume,source=deermate-local_stage,target=/stage",
            f"{settings['registry']}/deermate-tools:{settings['tag']}",
            "sleep",
            "120",
        ],
        capture=True,
    ).strip()
    try:
        result = subprocess.run(
            ["docker", "cp", "-", helper + ":/stage"],
            input=stage_archive(),
            capture_output=True,
        )
        if result.returncode:
            raise ack.DeploymentError("Failed to stage local inputs into the named Docker volume.")
    finally:
        subprocess.run(
            ["docker", "rm", "--force", helper],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def login(client):
    path = STATE / "admin.json"
    if not path.exists():
        ack.private_write(
            path, json.dumps({"email": "owner@example.com", "password": secrets.token_urlsafe(24)})
        )
    account = json.loads(path.read_text())
    status = client.get("/api/v1/auth/setup-status")
    status.raise_for_status()
    if status.json()["needs_setup"]:
        response = client.post("/api/v1/auth/initialize", json=account)
    else:
        response = client.post(
            "/api/v1/auth/login/local",
            data={
                "username": account["email"],
                "password": account["password"],
                "remember_me": "true",
            },
        )
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")
    return client.get("/api/v1/auth/me").status_code == 200


def verify(profile):
    checks = []

    def check(name, condition):
        if not condition:
            raise ack.DeploymentError("Local acceptance failed: " + name)
        checks.append(name)
        print("PASS " + name, flush=True)

    ready()
    environment = dict(
        line.split("=", 1) for line in (STATE / "runtime.env").read_text().splitlines()
    )
    with httpx.Client(base_url=URL, trust_env=False, timeout=60, headers={"Origin": URL}) as client:
        check("anonymous_tasks_rejected", client.get("/api/threads").status_code in {401, 403})
        check(
            "verification_key_is_not_a_login",
            client.post(
                "/api/deermate-local/submit",
                headers={"X-DeerMate-Local": environment["DEERMATE_LOCAL_VERIFICATION_KEY"]},
                json={"thread_id": "a" * 32, "prompt": "test", "key": "test"},
            ).status_code
            in {401, 403},
        )
        check("owner_setup_and_login", login(client))
        check("frontend_delivered", client.get("/").status_code in {200, 307})
        check(
            "submit_requires_separate_key",
            client.post(
                "/api/deermate-local/submit",
                json={"thread_id": "a" * 32, "prompt": "test", "key": "test"},
            ).status_code
            == 403,
        )
        client.headers["X-DeerMate-Local"] = environment["DEERMATE_LOCAL_VERIFICATION_KEY"]
        check(
            "project_override_rejected",
            client.post(
                "/api/deermate-local/submit",
                json={
                    "thread_id": "a" * 32,
                    "prompt": "test",
                    "key": "test",
                    "project_id": "other",
                },
            ).status_code
            == 422,
        )
        request = pending_submission()
        exists = client.get("/api/threads/" + request["thread_id"])
        if exists.status_code == 404:
            client.post("/api/threads", json={"thread_id": request["thread_id"]}).raise_for_status()
        response = client.post("/api/deermate-local/submit", json=request)
        if response.status_code == 409:
            # This dedicated, random verification thread has exactly one task.
            # Recover its existing durable owner after an interrupted verifier.
            detail = response.json()["detail"]
            check(
                "existing_tracking_owner_recovered",
                detail["error"] == "remote_handle_already_tracked",
            )
            tracked, remote = detail["task_id"], detail["remote_task_id"]
        else:
            response.raise_for_status()
            tracked = response.json()["tracking"]["task_id"]
            remote = response.json()["remote_task_id"]
        detail_path = f"/api/threads/{request['thread_id']}/mcp-tasks/{tracked}"
        result = wait(
            lambda: client.get(detail_path).json(),
            lambda task: task["status"] in {"completed", "failed", "input_required"},
            timeout=240,
        )
        check("gateway_ssh_real_codex_completed", result["status"] == "completed")
        check("independent_validation_passed", result["result"]["validation"]["exit_code"] == 0)
        with worker_client(profile) as worker:
            task_id = remote.split(":")[-1]
            native = worker.get("/tasks/" + task_id).json()
            patch = worker.get(f"/tasks/{task_id}/diff").text
            check(
                "repair_patch_retained",
                "-    return a - b" in patch and "+    return a + b" in patch,
            )
            duplicate = client.post("/api/deermate-local/submit", json=request)
            check(
                "idempotent_worker_identity",
                duplicate.status_code == 409
                and duplicate.json()["detail"]["remote_task_id"] == remote
                and duplicate.json()["detail"]["task_id"] == tracked
                and worker.get("/tasks/" + task_id).json()["attempt"] == 1,
            )
        compose("restart", "gateway")
        ready()
        check(
            "owner_session_survives_gateway_restart",
            client.get("/api/v1/auth/me").status_code == 200,
        )
        saved = client.get(detail_path).json()
        check(
            "sql_task_survives_gateway_restart",
            saved["task_id"] == tracked
            and saved["status"] == "completed"
            and saved["result"]["session_id"] == native["session_id"],
        )
    stats = json.loads((STATE / "ssh/stats.json").read_text())
    check(
        "authenticated_ssh_forwarding_used",
        stats["authenticated"] > 0 and stats["forward_requests"] > 0,
    )
    receipt = {
        "passed": True,
        "finished_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "native_runtime": "real locally signed-in Codex",
        "model": profile["model"],
        "configured_secretary_models": 0,
        "gateway_task_id": tracked,
        "thread_id": request["thread_id"],
        "remote_task_id": remote,
        "native_session_id": native["session_id"],
        "patch": patch,
        "validation": result["result"]["validation"],
        "limits": [
            "Local generated-key SSH development server, not an OS OpenSSH account.",
            "Owner/key-protected submit shim replaces secretary-model selection.",
            "No cloud, NAT or real secretary-model conversation/notification verification.",
        ],
    }
    ack.private_write(STATE / "verification.json", json.dumps(receipt, indent=2) + "\n")
    (STATE / "pending-verification.json").unlink()
    print("Local receipt saved; no password or token printed.", flush=True)


def pending_submission():
    path = STATE / "pending-verification.json"
    if path.exists():
        return json.loads(path.read_text())
    request = {"thread_id": uuid.uuid4().hex, "prompt": PROMPT, "key": "local-" + uuid.uuid4().hex}
    ack.private_write(path, json.dumps(request))
    return request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.platform != "darwin" or sys.version_info < (3, 12):
        parser.error("This local profile requires Docker Desktop for Mac and Python 3.12+.")
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init")
    init.add_argument(
        "--model", help="explicit host Codex model; otherwise use native configuration"
    )
    image = sub.add_parser("build")
    image.add_argument("--frontend-only", action="store_true", help="rebuild only the UI image")
    sub.add_parser("up")
    test = sub.add_parser("verify")
    test.add_argument(
        "--live", action="store_true", required=True, help="uses the signed-in Codex quota"
    )
    sub.add_parser("status")
    sub.add_parser("down")
    args = parser.parse_args()
    # Docker Desktop's bundled tools and the previously verified workspace Helm
    # also work when the caller has not started a new login shell yet.
    os.environ["PATH"] = os.pathsep.join(
        [
            str(Path.home() / ".docker/bin"),
            str(ROOT / ".deermate/tools"),
            os.environ.get("PATH", ""),
        ]
    )
    try:
        if args.action == "init":
            profile = initialize(args.model)
        else:
            profile = json.loads((STATE / "profile.json").read_text())
        if args.action == "build":
            ack.build(
                ack.load(STATE / "images.yaml"), STATE / "images.yaml", False, args.frontend_only
            )
        elif args.action == "up":
            token, instance = host_worker(profile)
            ssh_worker(profile, token, instance)
            upload_stage()
            compose("up", "--detach", "--force-recreate", "--wait", "--wait-timeout", "240")
            print("Local control plane: " + URL)
        elif args.action == "verify":
            verify(profile)
        elif args.action == "status":
            compose("ps")
        elif args.action == "down":
            compose("down")
            native_stop("ssh")
            native_stop("worker")
            print("Stopped only this local profile; named volumes and state retained.")
        else:
            print("Local profile initialized. Run build, then up, then verify --live.")
    except (ack.DeploymentError, OSError, ValueError, httpx.HTTPError) as error:
        print(
            f"Local run failed ({type(error).__name__}); inspect private local logs.",
            file=sys.stderr,
        )
        if isinstance(error, ack.DeploymentError):
            print(str(error), file=sys.stderr)
        elif isinstance(error, httpx.HTTPStatusError):
            print(f"HTTP {error.response.status_code} at {error.request.url.path}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
