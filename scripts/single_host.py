#!/usr/bin/env python3
"""Prepare a portable, private single-host bundle without accessing a cloud account."""

import argparse
import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path

import yaml

if __package__:
    from . import ack_deploy as ack
else:
    import ack_deploy as ack


def compose(project, port):
    data = yaml.safe_load((ack.ROOT / "deploy/local/compose.yaml").read_text())
    if set(data["services"]) != {"init", "gateway", "control", "frontend", "nginx"}:
        raise ack.DeploymentError("Review the changed local service contract first.")
    data["name"] = project
    data["volumes"].pop("credentials")
    data["volumes"]["stage"] = {
        "external": True,
        "name": "${DEERMATE_STAGE_VOLUME}",
    }
    limits = {
        "init": (256, 0.25),
        "gateway": (1024, 1),
        "control": (128, 0.25),
        "frontend": (256, 0.65),
        "nginx": (64, 0.1),
    }
    for name, service in data["services"].items():
        memory, cpu = limits[name]
        service.update(
            mem_limit=f"{memory}m",
            memswap_limit=f"{memory}m",
            cpus=cpu,
            pids_limit=256,
            logging={"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
        )
        service["volumes"] = [v for v in service["volumes"] if not v.startswith("credentials:")]
        if "env_file" in service:
            service["env_file"] = [name + ".env" if name != "gateway" else "runtime.env"]
    init = data["services"]["init"]
    init["entrypoint"] = ["/app/backend/.venv/bin/python", "/stage/single_host_init.py"]
    init["volumes"] = [v for v in init["volumes"] if not v.startswith("credentials:")]
    gateway = data["services"]["gateway"]
    gateway["entrypoint"] = [
        "/app/backend/.venv/bin/python",
        "-m",
        "uvicorn",
        "app.gateway.app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8001",
        "--no-access-log",
        "--log-level",
        "warning",
    ]
    gateway["environment"]["NO_PROXY"] = "localhost,127.0.0.1,gateway,frontend,nginx,control"
    control = data["services"]["control"]["environment"]
    control["DEERMATE_ORIGIN"] = f"http://localhost:{port}"
    control["DEERMATE_ALLOWED_HOSTS"] = (
        f"localhost:{port},127.0.0.1:{port},nginx:2026,127.0.0.1:8080,control:8080"
    )
    data["services"]["frontend"]["environment"]["NODE_OPTIONS"] = "--max-old-space-size=192"
    data["services"]["nginx"]["ports"] = [f"127.0.0.1:{port}:2026"]
    return data


def prepare(images, output, project, port):
    settings = ack.load(images)
    if not ack.NAME.fullmatch(project) or not 1024 <= port <= 65535:
        raise ack.DeploymentError("Use a valid project name and an unprivileged web port.")
    if output.exists():
        raise ack.DeploymentError("Output already exists; preserve its secrets and data.")
    checkout = ack.prepare(images.parent)
    ack.check_helm()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="single-host-") as temp:
        work = Path(temp)
        runtime = work / "runtime"
        runtime.mkdir(mode=0o755)
        values = work / "values.json"
        values.write_text(json.dumps(ack.values(settings)))
        rendered = ack.command(
            ["helm", "template", project, checkout / ack.CHART, "--values", values], capture=True
        )
        nginx = next(
            d["data"]["nginx.conf"]
            for d in yaml.safe_load_all(rendered)
            if d and d["kind"] == "ConfigMap" and "nginx.conf" in d.get("data", {})
        )
        nginx = ack.control_nginx(nginx.replace("server gateway:8001;", "server control:8080;"))
        (runtime / "nginx.conf").write_text(nginx)
        config = ack.app_config(settings)
        config["models"] = []
        (runtime / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
        (runtime / "extensions_config.json").write_text('{"mcpServers":{},"skills":{}}\n')
        (runtime / "empty.env").touch()
        shutil.copyfile(ack.ROOT / "deploy/single-host/init.py", runtime / "single_host_init.py")
        for path in runtime.iterdir():
            path.chmod(0o644)
        jwt = "AUTH_JWT_SECRET=" + secrets.token_urlsafe(40) + "\n"
        ack.private_write(
            work / "runtime.env",
            jwt + "DEER_FLOW_INTERNAL_AUTH_TOKEN=" + secrets.token_urlsafe(40) + "\n",
        )
        ack.private_write(work / "control.env", jwt)
        ack.private_write(
            work / "frontend.env", "BETTER_AUTH_SECRET=" + secrets.token_urlsafe(40) + "\n"
        )
        environment = {"COMPOSE_PROJECT_NAME": project, "DEERMATE_STAGE_VOLUME": project + "-stage"}
        for name in ("gateway", "control", "frontend", "nginx"):
            environment[f"DEERMATE_{name.upper()}_IMAGE"] = (
                f"{settings['registry']}/deermate-{name}:{settings['tag']}"
            )
        ack.private_write(work / ".env", "".join(f"{k}={v}\n" for k, v in environment.items()))
        ack.private_write(
            work / "compose.yaml", yaml.safe_dump(compose(project, port), sort_keys=False)
        )
        shutil.copyfile(ack.ROOT / "deploy/single-host/start.sh", work / "start.sh")
        (work / "start.sh").chmod(0o700)
        values.unlink()
        ack.private_write(
            work / "bundle.json",
            json.dumps(
                {
                    "upstream_pin": ack.PIN,
                    "project": project,
                    "port": port,
                    "worker_enabled": False,
                    "models_preconfigured": False,
                    "images": {k: v for k, v in environment.items() if k.endswith("_IMAGE")},
                    "running_container_memory_limit_mib": 1472,
                    "scope": "Single host; no native credentials or cloud provisioning",
                },
                indent=2,
            )
            + "\n",
        )
        os.rename(work, output)
    print(f"Prepared private bundle: {output}")
    print("Load the four images, run ./start.sh, then use a matching localhost SSH tunnel.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", default="deermate-single")
    parser.add_argument("--port", type=int, default=2027)
    args = parser.parse_args()
    try:
        prepare(args.images_config.absolute(), args.output.absolute(), args.project, args.port)
    except (ack.DeploymentError, OSError, ValueError) as error:
        message = str(error) if isinstance(error, ack.DeploymentError) else type(error).__name__
        parser.exit(1, f"Bundle preparation failed: {message}\n")


if __name__ == "__main__":
    main()
