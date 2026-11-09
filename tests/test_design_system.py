"""Regression tests for actual enforcement boundaries, not visual snapshots."""

import copy
from pathlib import Path

import pytest

from scripts import design_gate as gate
from scripts import sync_design_tokens as tokens


def test_repository_has_no_design_drift():
    gate.check()


@pytest.mark.parametrize("value", ["{colors.missing}", "{colors.loop}"])
def test_invalid_or_circular_reference_fails(value):
    design = tokens.load_design()
    design["colors"]["loop"] = value
    with pytest.raises(ValueError, match="reference"):
        tokens.outputs(design)


def test_duplicate_frontmatter_key_fails(tmp_path):
    (tmp_path / "design.md").write_text("---\ncolors: {}\ncolors: {}\n---\n")
    with pytest.raises(ValueError, match="Duplicate"):
        tokens.load_design(tmp_path)


@pytest.mark.parametrize(
    "source,css",
    [
        ("page.css", ".x { color: #123456; }"),
        ("page.css", ":root { --ds-colors-ink: inherit; }"),
        ("admin.html", "<style>.x { border-radius: 7px; }</style>"),
        ("tools.mjs", "style.textContent = `.x { padding: 13px; }`;"),
        ("page.css", ".x { transition: all 1s; }"),
        ("page.tsx", '<div className="text-red-500"/>'),
        ("page.tsx", '<div className="rounded-[7px]"/>'),
        ("page.tsx", '<div style={{color: "red"}}/>'),
    ],
)
def test_new_off_spec_styles_are_rejected(source, css):
    assert gate.violations(Path(source), css)


def test_valid_token_styles_and_geometry_are_allowed():
    assert not gate.violations(
        Path("page.css"),
        ".x { color: var(--ds-colors-ink); width: 310px; padding: var(--ds-spacing-md); }",
    )


def test_dark_aliases_are_rebound_after_semantic_overrides():
    design = tokens.load_design()
    dark = copy.deepcopy(design)
    dark["colors"].update(design["themes"]["dark"]["colors"])
    assert tokens.resolve(dark, "{colors.on-primary}") == "#111111"
    css = tokens.token_css(design).split(".dark {", 1)[1]
    assert "--dm-primary: var(--ds-colors-primary)" in css
    assert "--ds-colors-primary: #ededed" in css


def test_generated_asset_drift_is_rejected(tmp_path):
    design = tokens.load_design()
    (tmp_path / "design.md").write_text((tokens.ROOT / "design.md").read_text())
    for name, content in tokens.outputs(design).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n/* hand edited */")
    with pytest.raises(ValueError, match="generated drift"):
        gate.check(tmp_path)


def test_frontend_build_refuses_gate_failure_before_writing(tmp_path, monkeypatch):
    from scripts import frontend_overlay

    def reject():
        raise ValueError("design rejected")

    monkeypatch.setattr(gate, "check", reject)
    with pytest.raises(ValueError, match="design rejected"):
        frontend_overlay.apply(tmp_path)
    assert not list(tmp_path.iterdir())
