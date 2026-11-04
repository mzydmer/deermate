"""Run only inside an isolated synthetic Gateway container. Uses fake_codex.py."""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import uvicorn

from deermate.api import create_app, token_file
from deermate.config import Project, Settings
from deermate.device_connector import install_snapshot, process_request

ROOT = Path("/app/backend/.deer-flow/continuous-native-fixture")


def prepare_settings():
    ROOT.mkdir(mode=0o700, exist_ok=True)
    repo = ROOT / "repo"
    if not (repo / ".git").exists():
        import subprocess

        repo.mkdir(exist_ok=True)
        (repo / "tests").mkdir(exist_ok=True)
        (repo / "answer.py").write_text("def add(a, b):\n    return a - b\n")
        (repo / "tests/test_answer.py").write_text(
            "import unittest\nfrom answer import add\n"
            "class Addition(unittest.TestCase):\n"
            " def test_add(self): self.assertEqual(add(2,3),5)\n"
        )
        (repo / ".gitignore").write_text("__pycache__/\n")
        for args in (
            ["init", "-q"],
            ["add", "."],
            [
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
        ):
            subprocess.run(["git", "-C", str(repo), *args], check=True)
    settings = Settings(
        state_dir=ROOT / "state",
        task_timeout_seconds=60,
        codex_command=[sys.executable, "/etc/deermate/fake_codex.py", str(ROOT / "native")],
        projects={
            "demo": Project(
                root=repo,
                allow_write=True,
                test_command=[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            )
        },
    )
    return settings


async def main():
    settings = await asyncio.to_thread(prepare_settings)

    app = create_app(settings)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=18777, access_log=False, log_level="error")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            await task
        await asyncio.sleep(0.02)
    (ROOT / "descriptor.json").write_text(
        json.dumps(
            {
                "instance_id": app.state.worker.store.instance_id,
                "profile": "fake-codex-protocol-only",
            }
        )
    )
    async with (
        httpx.AsyncClient(base_url="http://control:8080", timeout=20, trust_env=False) as cloud,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:18777",
            timeout=10,
            headers={"Authorization": "Bearer " + token_file(settings.state_dir)},
            trust_env=False,
        ) as local,
    ):
        while not task.done() and not (ROOT / "stop").exists():
            path = ROOT / "device.json"
            if path.exists():
                state = json.loads(path.read_text())
                cloud.headers["Authorization"] = "Bearer " + state["token"]
                try:
                    response = await cloud.post(
                        "/api/agent-devices/poll",
                        json={
                            "worker_status": "reachable",
                            "continuous_protocol": "work-orders-v1",
                        },
                    )
                    response.raise_for_status()
                    packet = response.json()
                    install_snapshot(packet, state, settings)
                    await process_request(cloud, local, state, settings, packet)
                except (httpx.HTTPError, ValueError, KeyError) as error:
                    print("Fixture connector: " + type(error).__name__, flush=True)
            await asyncio.sleep(0.2)
    server.should_exit = True
    await task


if __name__ == "__main__":
    asyncio.run(main())
