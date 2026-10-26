"""Frontend overlay fails closed when upstream authentication files change."""

import hashlib
import json

import pytest

from scripts import frontend_overlay as overlay


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "project"
    frontend = tmp_path / "build/frontend"
    frontend.mkdir(parents=True)
    source = root / "frontend/overlay/public/deermate"
    source.mkdir(parents=True)
    (source / "brand.txt").write_text("DeerMate")
    scene = root / "frontend/motion/public/projects/deermate/scene-1"
    scene.mkdir(parents=True)
    (scene / "lottie.json").write_text('{"layers":[]}')
    patches = []
    for name in ("auth.tsx", "layout.tsx"):
        (frontend / name).write_text("original upstream")
        patches.append(
            {
                "path": name,
                "sha256": hashlib.sha256(b"original upstream").hexdigest(),
                "replace": [["upstream", "application"]],
            }
        )
    (root / "frontend/patches.json").write_text(json.dumps(patches))
    monkeypatch.setattr(overlay, "ROOT", root)
    return root, frontend


def test_overlay_applies_only_to_supplied_build_context(tmp_path, monkeypatch):
    _, frontend = fixture(tmp_path, monkeypatch)
    overlay.apply(frontend)
    assert (frontend / "auth.tsx").read_text() == "original application"
    assert (frontend / "public/deermate/brand.txt").read_text() == "DeerMate"
    assert json.loads((frontend / "public/deermate/secretary.json").read_text()) == {"layers": []}


def test_changed_upstream_aborts_before_any_patch_is_written(tmp_path, monkeypatch):
    _, frontend = fixture(tmp_path, monkeypatch)
    (frontend / "layout.tsx").write_text("unrecognized authentication contract")
    with pytest.raises(ValueError, match="Pinned frontend file changed"):
        overlay.apply(frontend)
    assert (frontend / "auth.tsx").read_text() == "original upstream"
    assert not (frontend / "public").exists()


def test_overlay_rejects_symlink_to_outside_source(tmp_path, monkeypatch):
    root, frontend = fixture(tmp_path, monkeypatch)
    outside = tmp_path / "unrelated-secret"
    outside.write_text("must never be copied")
    (root / "frontend/overlay/leak.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="ordinary files"):
        overlay.apply(frontend)
    assert (frontend / "auth.tsx").read_text() == "original upstream"
    assert not (frontend / "leak.txt").exists()
