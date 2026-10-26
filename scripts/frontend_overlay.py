"""Apply the versioned DeerMate frontend to an ephemeral pinned build context."""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply(frontend: Path):
    patches = json.loads((ROOT / "frontend/patches.json").read_text())
    staged = []
    for patch in patches:
        target = frontend / patch["path"]
        if not target.resolve().is_relative_to(frontend.resolve()):
            raise ValueError("Frontend patch escapes its build context")
        original = target.read_bytes()
        if hashlib.sha256(original).hexdigest() != patch["sha256"]:
            raise ValueError("Pinned frontend file changed: " + patch["path"])
        content = original.decode()
        for before, after in patch["replace"]:
            if content.count(before) != 1:
                raise ValueError("Frontend anchor is not unique: " + patch["path"])
            content = content.replace(before, after, 1)
        staged.append((target, content))
    overlay = ROOT / "frontend/overlay"
    files = [file for file in overlay.rglob("*") if file.is_file()]
    for file in files:
        if file.is_symlink() or not file.resolve().is_relative_to(overlay.resolve()):
            raise ValueError("Frontend overlay must contain ordinary files")
        target = frontend / file.relative_to(overlay)
        if not target.resolve().is_relative_to(frontend.resolve()):
            raise ValueError("Frontend overlay escapes its build context")
    for target, content in staged:
        target.write_text(content)
    for file in files:
        target = frontend / file.relative_to(overlay)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
    scene = ROOT / "frontend/motion/public/projects/deermate/scene-1/lottie.json"
    shutil.copyfile(scene, frontend / "public/deermate/secretary.json")
