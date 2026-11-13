"""Prepare the pinned frontend without Docker; never modify the upstream checkout."""

import argparse
import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from frontend_overlay import apply

ROOT = Path(__file__).resolve().parents[1]
PIN = "a1b89d0432de4e45adc59f512cb25bb386ea1e51"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT / ".deermate/ack/deer-flow")
    parser.add_argument("--output", type=Path, default=ROOT / ".deermate/frontend-overhaul")
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument("--pnpm", default=shutil.which("pnpm"))
    parser.add_argument("--reuse-deps", type=Path)
    parser.add_argument("--mode", choices=["prepare", "build", "dev", "fixture"], default="build")
    parser.add_argument("--control", type=Path)
    args = parser.parse_args()
    if not args.node:
        parser.error("Node must be on PATH or supplied with --node")
    target = args.output.resolve() / "frontend"
    if target.exists():
        parser.error("Use a fresh output directory; existing builds are preserved")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile() as archive:
        subprocess.run(
            ["git", "-C", str(args.upstream), "archive", PIN, "frontend"],
            stdout=archive,
            check=True,
        )
        archive.seek(0)
        with tarfile.open(fileobj=archive) as tar:
            tar.extractall(target.parent, filter="data")
    apply(target)
    if args.reuse_deps:
        for name in ("package.json", "pnpm-lock.yaml"):
            if (
                hashlib.sha256((target / name).read_bytes()).digest()
                != hashlib.sha256((args.reuse_deps / name).read_bytes()).digest()
            ):
                raise ValueError("Dependency reuse requires identical package and lock files")
        (target / "node_modules").symlink_to(
            (args.reuse_deps / "node_modules").resolve(), target_is_directory=True
        )
    elif args.mode != "prepare":
        if not args.pnpm:
            parser.error("pnpm is required for a frozen install")
        subprocess.run([args.pnpm, "install", "--frozen-lockfile"], cwd=target, check=True)
    env = os.environ.copy()
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    if args.mode in ("build", "fixture"):
        subprocess.run(
            [args.node, "node_modules/next/dist/bin/next", "build", "--webpack"],
            cwd=target,
            env=env,
            check=True,
        )
    if args.mode == "dev":
        subprocess.run(
            [args.node, "node_modules/next/dist/bin/next", "dev", "--hostname", "127.0.0.1"],
            cwd=target,
            env=env,
            check=True,
        )
    if args.mode == "fixture":
        if not args.control:
            parser.error("Supply a freshly built Go --control for fixture mode")
        subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                str(ROOT / "scripts/design_visual_fixture.py"),
                "--frontend",
                str(target),
                "--control",
                str(args.control.resolve()),
                "--node",
                args.node,
                "--work-dir",
                str(args.output.resolve() / "fixture"),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
