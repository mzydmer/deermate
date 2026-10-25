import asyncio
import os
from pathlib import Path

LIMIT = 1024 * 1024


async def git(root: Path, *args: str, accepted=(0,)) -> bytes:
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    # Remove injected git config from the service's environment.
    for key in list(env):
        if key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            env.pop(key)
    env.pop("GIT_CONFIG_COUNT", None)
    process = await asyncio.create_subprocess_exec(
        "git",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(root),
        *args,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    except BaseException:
        process.kill()
        await process.wait()
        raise
    if len(stdout) > LIMIT:
        raise RuntimeError("git output exceeds 1 MiB; evidence is incomplete")
    if process.returncode not in accepted:
        raise RuntimeError("git command failed: " + stderr.decode(errors="replace")[:1000])
    return stdout


async def prepare(root: Path, workspace: Path) -> str:
    top = (await git(root, "rev-parse", "--show-toplevel")).decode().strip()
    if await asyncio.to_thread(Path(top).resolve) != root:
        raise ValueError("configured root must be the repository root")
    base = (await git(root, "rev-parse", "HEAD")).decode().strip()
    await asyncio.to_thread(workspace.parent.mkdir, parents=True, exist_ok=True)
    await git(root, "worktree", "add", "--detach", str(workspace), base)
    return base


async def collect(workspace: Path, base: str) -> str:
    if not await asyncio.to_thread(valid_workspace, workspace):
        raise RuntimeError("workspace no longer exists or was replaced")
    output = await git(
        workspace,
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--binary",
        "--no-renames",
        base,
        "--",
        ".",
    )
    files = await git(workspace, "ls-files", "--others", "--exclude-standard", "-z")
    for raw in files.split(b"\0"):
        if not raw:
            continue
        relative = os.fsdecode(raw)
        path = workspace / relative
        await asyncio.to_thread(validate_artifact, path, workspace)
        output += await git(
            workspace,
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            "--",
            os.devnull,
            relative,
            accepted=(0, 1),
        )
        if len(output) > LIMIT:
            raise RuntimeError("combined patch exceeds 1 MiB; evidence is incomplete")
    return output.decode(errors="replace")


def valid_workspace(workspace: Path) -> bool:
    return not workspace.is_symlink() and workspace.is_dir()


def validate_artifact(path: Path, workspace: Path):
    if (
        path.is_symlink()
        or not path.is_file()
        or not path.resolve().is_relative_to(workspace.resolve())
    ):
        raise RuntimeError("untracked artifact is not a regular workspace file")
    if path.stat().st_size > LIMIT:
        raise RuntimeError("untracked file too large for complete patch evidence")
