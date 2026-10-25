import subprocess
import sys
from pathlib import Path

import pytest

from deermate.config import Project, Settings


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
