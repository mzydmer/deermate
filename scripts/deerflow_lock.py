"""Read DeerMate's single DeerFlow revision and validate existing checkouts."""

import argparse
import re
import subprocess
from pathlib import Path

LOCK_PATH = Path(__file__).resolve().parents[1] / "deploy/deerflow.lock"
IMAGE_LABEL = "io.deermate.deerflow.commit"


class DeerFlowLockError(ValueError):
    """An upstream input is missing, invalid, mismatched or locally modified."""


def read_revision(path: Path | None = None) -> str:
    path = LOCK_PATH if path is None else path
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise DeerFlowLockError(f"Cannot read DeerFlow lock: {path}") from error
    if not re.fullmatch(r"[0-9a-f]{40}\n?", content) or content.rstrip("\n") == "0" * 40:
        raise DeerFlowLockError(
            f"Invalid DeerFlow lock: {path}; expected one full 40-character lowercase Git SHA."
        )
    return content.rstrip("\n")


def verify_checkout(checkout: Path, *, paths: tuple[str, ...] = (), revision=None) -> str:
    expected = read_revision() if revision is None else revision
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    actual = result.stdout.strip() if result.returncode == 0 else "<unavailable>"
    if actual != expected:
        raise DeerFlowLockError(
            f"DeerFlow checkout mismatch; expected: {expected}; actual: {actual}. "
            "Preserve the existing checkout and choose a fresh workspace for the locked revision."
        )
    result = subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *paths,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode or result.stdout:
        raise DeerFlowLockError(
            f"DeerFlow checkout must be clean in the required paths; "
            f"expected: {expected}; actual: {actual}. Local changes were preserved."
        )
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        revision = read_revision(args.lock)
    except DeerFlowLockError as error:
        parser.exit(1, f"{error}\n")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write(f"revision={revision}\n")
    print(revision)


if __name__ == "__main__":
    main()
