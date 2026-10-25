"""Opt-in compatibility probe: actual pinned upstream driver, no model calls."""

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType

import pytest
from mcp_helpers import mcp_session

DEERFLOW_COMMIT = "a1b89d0432de4e45adc59f512cb25bb386ea1e51"


def load_driver(checkout: Path, monkeypatch):
    head = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    assert head == DEERFLOW_COMMIT, "Use the documented pinned DeerFlow checkout"
    source_root = "backend/packages/harness/deerflow"
    files = ["constants.py", "mcp/tasks/models.py", "mcp/tasks/ordinary.py"]
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "diff",
            "--exit-code",
            head,
            "--",
            *(f"{source_root}/{file}" for file in files),
        ],
        check=True,
        capture_output=True,
    )
    # Isolate these pure upstream contract modules from harness/model/provider
    # bootstrap. No copied parser, fake driver or installed DeerFlow is used.
    for name in ["deerflow", "deerflow.mcp", "deerflow.mcp.tasks"]:
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    loaded = []
    for name, file in zip(
        ["deerflow.constants", "deerflow.mcp.tasks.models", "deerflow.mcp.tasks.ordinary"],
        files,
        strict=True,
    ):
        spec = importlib.util.spec_from_file_location(name, checkout / source_root / file)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded[1], loaded[2]


async def test_pinned_deerflow_driver_over_real_mcp(local_server, tmp_path, monkeypatch):
    value = os.environ.get("DEERMATE_DEERFLOW_CHECKOUT")
    if not value:
        pytest.skip("Set DEERMATE_DEERFLOW_CHECKOUT to run the pinned upstream probe")
    models, ordinary = load_driver(Path(value), monkeypatch)
    config, port, worker = local_server
    toolset = {
        "submit_tool": "submit_task",
        "status_tool": "get_task_status",
        "cancel_tool": "cancel_task",
    }

    class Caller:
        def __init__(self, session):
            self.session = session

        async def call_tool(self, *, tool_name, arguments, **scope):
            assert scope["server_name"] == "deermate"
            return await self.session.call_tool(tool_name, arguments)

    def request(prompt, key):
        return models.TaskSubmitRequest(
            user_id="owner",
            thread_id="thread",
            run_id="run",
            tool_call_id=key,
            server_name="deermate",
            task_name="coding",
            arguments={"project_id": "demo", "prompt": prompt, "idempotency_key": key},
            driver_data=toolset,
        )

    def reference(submission):
        return models.TaskReference(
            local_task_id="tracking-row",
            user_id="owner",
            thread_id="thread",
            server_name="deermate",
            remote_task_id=submission.remote_task_id,
            driver_data=submission.driver_data,
        )

    async def wait(driver, ref, expected):
        async with asyncio.timeout(10):
            while True:
                result = await driver.get_status(ref)
                if result.status in expected:
                    return result
                await asyncio.sleep(0.02)

    async with mcp_session(config, port) as session:
        driver = ordinary.OrdinaryMcpTaskDriver(Caller(session))
        submission = await driver.submit(request("slow", "persisted"))
        ref = reference(submission)
        assert submission.snapshot.status == models.TaskStatus.SUBMITTED
        await wait(driver, ref, {models.TaskStatus.WORKING})
        (tmp_path / "reference.json").write_text(json.dumps(asdict(ref)))
    # Recreate the driver and stdio process using only persisted handle data.
    async with mcp_session(config, port) as session:
        driver = ordinary.OrdinaryMcpTaskDriver(Caller(session))
        ref = models.TaskReference(**json.loads((tmp_path / "reference.json").read_text()))
        assert (await driver.get_status(ref)).status == models.TaskStatus.WORKING
        assert (await driver.cancel(ref)).status == models.TaskStatus.CANCELLED
        assert (await driver.cancel(ref)).status == models.TaskStatus.CANCELLED
        for prompt, expected in [
            ("fix", models.TaskStatus.COMPLETED),
            ("bad-fix", models.TaskStatus.FAILED),
            ("question", models.TaskStatus.INPUT_REQUIRED),
        ]:
            ref = reference(await driver.submit(request(prompt, prompt)))
            result = await wait(driver, ref, {expected})
            if expected == models.TaskStatus.COMPLETED:
                assert result.result["validation"]["exit_code"] == 0
            if expected == models.TaskStatus.INPUT_REQUIRED:
                assert result.input_required["kind"] == "input_required"
                assert (await driver.cancel(ref)).status == models.TaskStatus.CANCELLED
        missing = models.TaskReference(
            local_task_id="missing",
            user_id="owner",
            thread_id="thread",
            server_name="deermate",
            remote_task_id="a" * 32,
            driver_data=toolset,
        )
        assert (await driver.get_status(missing)).status == models.TaskStatus.FAILED
    assert len(worker.store.list_tasks()) == 4
