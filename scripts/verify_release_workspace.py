"""Start a fresh Linux/amd64 source-built workspace without users, models or Native work."""

import argparse
import json
import platform
import subprocess
import time
import uuid
from pathlib import Path

import httpx

if __package__:
    from . import release_artifacts, single_host
else:
    import release_artifacts
    import single_host


def run(images_config, directory):
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ValueError("The full source workspace release smoke requires Linux/amd64")
    revision = release_artifacts.clean_source()
    project = "deermate-alpha-" + uuid.uuid4().hex[:10] + "-check"
    single_host.prepare(images_config.resolve(), directory.resolve(), project, 22077)
    compose = ["docker", "compose", "--project-directory", str(directory.resolve())]
    try:
        subprocess.run([str(directory.resolve() / "start.sh")], check=True)
        with httpx.Client(base_url="http://localhost:22077", trust_env=False, timeout=10) as client:
            ready = client.get("/health/ready")
            ready.raise_for_status()
            setup = client.get("/api/v1/auth/setup-status")
            setup.raise_for_status()
            if setup.json().get("needs_setup") is not True:
                raise ValueError("Release smoke must start with no administrator")
            page = client.get("/setup")
            page.raise_for_status()
            if "<html" not in page.text.lower():
                raise ValueError("Production frontend did not serve setup HTML")
        output = subprocess.check_output(
            [
                "docker",
                "exec",
                project + "-gateway-1",
                "/app/backend/.venv/bin/python",
                "-c",
                "import sqlite3,json;from pathlib import Path;"
                "p=Path('/app/backend/.deer-flow/data/deerflow.db');"
                "d=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);"
                "print(json.dumps({name:d.execute('SELECT count(*) FROM '+name).fetchone()[0] "
                "for name in ['users','runs','mcp_tasks']}))",
            ],
            text=True,
        )
        counts = json.loads(output)
        if any(counts.values()):
            raise ValueError("Startup must not create users, model runs or MCP tasks")
        return {
            "passed": True,
            "source_sha": revision,
            "platform": "linux/amd64",
            "setup_html": True,
            "go_ready": True,
            "needs_setup": True,
            "database_counts": counts,
            "native_tasks_submitted": 0,
            "real_provider_calls": 0,
            "scope": "Fresh source-built application; no hosted rollout",
        }
    finally:
        subprocess.run(compose + ["down", "--timeout", "60"], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-config", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    result = run(args.images_config, args.work_dir)
    result["elapsed_seconds"] = time.monotonic() - started
    with args.receipt.open("x") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print("Linux/amd64 full workspace ready; no account/model/Native work created.")


if __name__ == "__main__":
    main()
