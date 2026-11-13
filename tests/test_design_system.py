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


@pytest.mark.parametrize(
    "markup", ["<button/>", "<input/>", "<textarea/>", "<select/>", "<details/>", "<summary/>"]
)
def test_native_controls_are_confined_to_primitives(markup):
    assert "native interactive element outside primitives" in gate.violations(
        Path("frontend/overlay/src/components/deermate/feature.tsx"), markup
    )
    assert not gate.violations(
        Path("frontend/overlay/src/components/deermate/ui/control.tsx"), markup
    )


@pytest.mark.parametrize(
    "css", [".action { text-decoration: underline; }", ".textarea { resize: none; }"]
)
def test_action_underlines_and_resize_are_rejected(css):
    assert gate.violations(Path("feature.css"), css)


@pytest.mark.parametrize(
    "markup", ['<div className="bg-canvas rounded-md"/>', 't("中文", "English")']
)
def test_feature_visuals_and_inline_copy_are_rejected(markup):
    assert gate.violations(Path("frontend/overlay/src/components/deermate/feature.tsx"), markup)


def test_css_budget_cannot_be_increased(tmp_path):
    (tmp_path / "design.md").write_text(
        (tokens.ROOT / "design.md")
        .read_text()
        .replace('"cssBudgetLines": 1100', '"cssBudgetLines": 1101')
    )
    with pytest.raises(ValueError, match="CSS budget"):
        gate.check(tmp_path)


@pytest.mark.parametrize(
    "markup",
    ['<div className={active ? "bg-canvas" : "bg-primary"}/>', '<p>{zh ? "中文" : "English"}</p>'],
)
def test_expression_visuals_and_inline_locale_branches_are_rejected(markup):
    assert gate.violations(Path("frontend/overlay/src/components/deermate/feature.tsx"), markup)


@pytest.mark.parametrize(
    "filename,reason",
    [
        ("frontend/overlay/src/styles/deermate.css", "must remain deleted"),
        ("frontend/overlay/src/styles/feature.css", "belongs beside ui/patterns"),
        ("frontend/overlay/src/styles/app.css", "import entrypoint only"),
    ],
)
def test_stylesheet_location_and_entrypoint_contracts(tmp_path, filename, reason):
    design = tokens.load_design()
    (tmp_path / "design.md").write_text((tokens.ROOT / "design.md").read_text())
    for name, content in tokens.outputs(design).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(".feature { color: var(--ds-colors-ink); }")
    with pytest.raises(ValueError, match=reason):
        gate.check(tmp_path)
