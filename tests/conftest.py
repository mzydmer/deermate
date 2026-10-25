import asyncio
import hashlib
import importlib.metadata
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import uvicorn

from deermate.api import create_app
from deermate.config import Project, Settings

_ssh_reports = []


def pytest_addoption(parser):
    parser.addoption(
        "--ssh-receipt", help="save bounded SSH fixture outcomes after a passing session"
    )


def pytest_runtest_logreport(report):
    if report.when == "call" and report.nodeid.startswith("tests/test_ssh.py::"):
        _ssh_reports.append(
            {
                "test": report.nodeid.split("::")[-1],
                "outcome": report.outcome,
                "seconds": round(report.duration, 3),
            }
        )


def pytest_sessionfinish(session, exitstatus):
    destination = session.config.getoption("ssh_receipt")
    if not destination or exitstatus != 0 or not _ssh_reports:
        return
    root = Path(__file__).resolve().parents[1]
    sources = sorted((root / "src/deermate").glob("*.py")) + [
        root / "tests/test_ssh.py",
        root / "tests/ssh_helpers.py",
        root / "tests/fake_codex.py",
        root / "tests/conftest.py",
        root / "tests/mcp_helpers.py",
    ]
    data = {
        "schema_version": 1,
        "passed": True,
        "scope": "Real generated-key SSH and HTTP Worker on loopback; offline native fixture",
        "limits": [
            "No operator keys/sshd or cross-machine deployment",
            "No NAT, relay, UI or real model",
        ],
        "packages": {
            name: importlib.metadata.version(name)
            for name in ["asyncssh", "bcrypt", "cryptography", "mcp", "httpx"]
        },
        "source_sha256": {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources
        },
        "test_count": len(_ssh_reports),
        "tests": _ssh_reports,
    }
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n")


@pytest.fixture
def settings(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "answer.py").write_text("def add(a, b):\n    return a - b\n")
    (repo / "tests").mkdir()
    (repo / "tests/test_answer.py").write_text(
        "import unittest\nfrom answer import add\n"
        "class Addition(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
    )
    (repo / ".gitignore").write_text("__pycache__/\n")
    for args in [
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
    ]:
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    return Settings(
        state_dir=tmp_path / "state",
        task_timeout_seconds=20,
        codex_command=[
            sys.executable,
            "-u",
            str(Path(__file__).with_name("fake_codex.py")),
            str(tmp_path / "native"),
        ],
        projects={
            "demo": Project(
                root=repo,
                allow_write=True,
                test_command=[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            )
        },
    )


@pytest.fixture
async def local_server(settings, tmp_path):
    config_path = tmp_path / "worker.toml"
    config_path.write_text(
        f"state_dir = {json.dumps(str(settings.state_dir))}\n"
        f"codex_command = {json.dumps(settings.codex_command)}\n"
        "[projects.demo]\n"
        f"root = {json.dumps(str(settings.projects['demo'].root))}\n"
        "allow_write = true\n"
        f"test_command = {json.dumps(settings.projects['demo'].test_command)}\n"
    )
    app = create_app(settings)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    job = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:  # noqa: ASYNC110 - wait for actual server startup
                if job.done():
                    await job
                    raise AssertionError("Worker server stopped before startup")
                await asyncio.sleep(0.01)
        yield config_path, port, app.state.worker
    finally:
        server.should_exit = True
        await asyncio.wait_for(job, timeout=10)
        sock.close()
