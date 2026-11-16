"""Public docs cannot silently drift or disappear from implementation changes."""

import json
import shutil
import subprocess
import sys

import pytest

from scripts import product_docs as docs


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(docs.ROOT / docs.CONTENT, root / docs.CONTENT)
    shutil.copytree(
        docs.ROOT / "frontend/overlay/public/deermate/docs/diagrams",
        root / "frontend/overlay/public/deermate/docs/diagrams",
    )
    catalog = json.loads((root / docs.CONTENT / "catalog.json").read_text())
    for page in catalog:
        for source in page["sources"]:
            path = root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    return root


def test_public_output_matches_markdown_without_internal_evidence():
    output = docs.compile_docs()
    assert output == (docs.ROOT / docs.OUTPUT).read_text()
    assert all("sources" not in page for page in json.loads(output))


def test_broken_article_link_is_rejected(project):
    page = project / docs.CONTENT / "guide/quickstart.md"
    page.write_text(page.read_text() + "\n[Missing](./missing.md)\n")
    with pytest.raises(ValueError, match="Missing documentation link"):
        docs.compile_docs(project)


def test_missing_source_evidence_is_rejected(project):
    (project / "docs/STATUS.md").unlink()
    with pytest.raises(ValueError, match="Missing source evidence"):
        docs.compile_docs(project)


def test_uncatalogued_article_is_rejected(project):
    (project / docs.CONTENT / "guide/hidden.md").write_text("# Hidden\n")
    with pytest.raises(ValueError, match="Uncatalogued"):
        docs.compile_docs(project)


@pytest.mark.parametrize(
    "path",
    [
        "frontend/overlay/src/components/deermate/desk.tsx",
        "backend/internal/controlplane/server.go",
        "src/deermate/worker.py",
        "scripts/example.py",
        ".github/workflows/ci.yml",
    ],
)
def test_code_without_documentation_review_is_rejected(path, project):
    with pytest.raises(ValueError, match="without public documentation review"):
        docs.check_impact({path, "docs/STATUS.md", str(docs.OUTPUT)}, project)


def test_changed_public_article_satisfies_impact_review(project):
    docs.check_impact(
        {"src/example.py", "docs/product/guide/quickstart.md", "docs/product/changelog.md"}, project
    )


def test_article_update_alone_requires_changelog_or_internal_note(project):
    with pytest.raises(ValueError, match="without public documentation review"):
        docs.check_impact({"src/example.py", "docs/product/guide/quickstart.md"}, project)


def test_changelog_alone_does_not_replace_the_affected_guide(project):
    with pytest.raises(ValueError, match="without public documentation review"):
        docs.check_impact({"src/example.py", "docs/product/changelog.md"}, project)


def test_deleted_article_does_not_satisfy_impact_review(project):
    (project / docs.CONTENT / "guide/quickstart.md").unlink()
    with pytest.raises(ValueError, match="without public documentation review"):
        docs.check_impact({"src/example.py", "docs/product/guide/quickstart.md"}, project)


def test_internal_change_requires_reasoned_note(project):
    path = project / "docs/change-notes/internal.md"
    path.parent.mkdir(exist_ok=True)
    paths = {"tests/internal.py", "docs/change-notes/internal.md"}
    path.write_text("结论：无需更新客户文档\n理由：测试\n涉及文件：tests/internal.py\n")
    with pytest.raises(ValueError, match="without public documentation review"):
        docs.check_impact(paths, project)
    path.write_text(
        "结论：无需更新客户文档\n理由：仅增加离线测试的故障样本，不改变任何用户操作、返回结果或技术方案。\n涉及文件：tests/internal.py\n"
    )
    docs.check_impact(paths, project)


def test_missing_diagram_is_rejected(project):
    (project / "frontend/overlay/public/deermate/docs/diagrams/architecture.svg").unlink()
    with pytest.raises(ValueError, match="Missing diagram asset"):
        docs.compile_docs(project)


def test_active_svg_content_is_rejected(project):
    path = project / "frontend/overlay/public/deermate/docs/diagrams/architecture.svg"
    path.write_text(path.read_text().replace("</svg>", "<script>alert(1)</script></svg>"))
    with pytest.raises(ValueError, match="Unsafe diagram SVG"):
        docs.compile_docs(project)


def test_relative_links_map_to_existing_routes_and_preserve_https(project):
    source = project / docs.CONTENT / "guide/quickstart.md"
    source.write_text(
        source.read_text()
        + (
            "\n[Sibling](./conversations.md)\n"
            "[Encoded sibling](./%63onversations.md)\n"
            "[Technical](../technical/architecture.md)\n"
            "[Changes](../changelog.md)\n"
            "[External](https://example.com/reference?q=one#section)\n"
        )
    )
    pages = json.loads(docs.compile_docs(project))
    body = next(p["body"] for p in pages if p["slug"] == "guide/quickstart")
    assert "[Sibling](/docs/guide/conversations)" in body
    assert "[Encoded sibling](/docs/guide/conversations)" in body
    assert "[Technical](/docs/technical/architecture)" in body
    assert "[Changes](/docs/changelog)" in body
    assert "](/deermate/docs/diagrams/quickstart.svg)" in body
    assert "[External](https://example.com/reference?q=one#section)" in body


def test_existing_but_uncatalogued_link_target_is_rejected(project):
    (project / docs.CONTENT / "guide/hidden.md").write_text("# Hidden\n")
    source = project / docs.CONTENT / "guide/quickstart.md"
    source.write_text(source.read_text() + "\n[Hidden](./hidden.md)\n")
    with pytest.raises(ValueError, match="target is not catalogued"):
        docs.compile_docs(project)


@pytest.mark.parametrize(
    "href",
    [
        "../../security.md",
        "../../../../outside.md",
        "../../../%2e%2e/outside.md",
        "%2foutside.md",
        "/docs/guide/quickstart",
        "//example.com/file.md",
        "http://example.com/file.md",
        "javascript:alert",
        "./conversations.md?query=1",
        "./conversations.md#section",
        "./%00conversations.md",
        ".%5cconversations.md",
    ],
)
def test_unsupported_or_escaping_document_links_are_rejected(project, href):
    source = project / docs.CONTENT / "guide/quickstart.md"
    source.write_text(source.read_text() + f"\n[Invalid]({href})\n")
    with pytest.raises(ValueError, match="documentation link"):
        docs.compile_docs(project)


@pytest.mark.parametrize(
    "href",
    [
        "https://example.com/figure.svg",
        "../../../../outside.svg",
        "../../../docs/assets/not-managed.svg",
    ],
)
def test_external_or_unmanaged_diagram_is_rejected(project, href):
    source = project / docs.CONTENT / "guide/quickstart.md"
    source.write_text(source.read_text() + f"\n![Invalid figure]({href})\n")
    with pytest.raises(ValueError, match="diagram|documentation link"):
        docs.compile_docs(project)


def test_article_symlink_alias_is_rejected(project):
    guide = project / docs.CONTENT / "guide"
    (guide / "alias.md").symlink_to(guide / "conversations.md")
    source = guide / "quickstart.md"
    source.write_text(source.read_text() + "\n[Alias](./alias.md)\n")
    with pytest.raises(ValueError, match="Symlink documentation link"):
        docs.compile_docs(project)


def test_symlink_followed_by_parent_cannot_launder_a_registered_target(project):
    outside = project.parent / "outside"
    outside.mkdir()
    guide = project / docs.CONTENT / "guide"
    (guide / "alias").symlink_to(outside, target_is_directory=True)
    source = guide / "quickstart.md"
    # resolve() alone would turn this into the registered conversations.md.
    href = f"./alias/../{project.name}/docs/product/guide/conversations.md"
    assert (guide / href).resolve() == guide / "conversations.md"
    source.write_text(source.read_text() + f"\n[Alias]({href})\n")
    with pytest.raises(ValueError, match="Symlink documentation link"):
        docs.compile_docs(project)


@pytest.mark.parametrize("kind", ["catalog", "article", "diagram", "diagram_parent"])
def test_symlinked_content_is_rejected_before_external_file_read(project, monkeypatch, kind):
    if kind == "catalog":
        target = project / docs.CONTENT / "catalog.json"
    elif kind == "article":
        target = project / docs.CONTENT / "guide/overview.md"
    elif kind == "diagram":
        target = project / docs.DIAGRAMS / "quickstart.svg"
    else:
        target = project / docs.DIAGRAMS
    external = project.parent / "external"
    target.rename(external)
    target.symlink_to(external, target_is_directory=external.is_dir())
    read_text = type(project).read_text

    def guarded_read(path, *args, **kwargs):
        assert path.resolve().is_relative_to(project), "external content must not be read"
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(type(project), "read_text", guarded_read)
    with pytest.raises(ValueError, match="Symlink"):
        docs.compile_docs(project)


def test_reference_definitions_cannot_bypass_target_validation(project):
    source = project / docs.CONTENT / "guide/quickstart.md"
    source.write_text(
        source.read_text() + "\n[Hidden][target]\n\n[target]: ../../../../missing.md\n"
    )
    with pytest.raises(ValueError, match="Use inline documentation links"):
        docs.compile_docs(project)


@pytest.mark.parametrize(
    "failure",
    [
        "missing_article",
        "uncatalogued_article",
        "missing_svg",
        "escaping_path",
        "symlink",
        "unsafe_svg",
    ],
)
def test_actual_offline_documentation_check_fails_for_bad_targets(project, failure):
    source = project / docs.CONTENT / "guide/quickstart.md"
    if failure == "missing_article":
        (project / docs.CONTENT / "guide/conversations.md").unlink()
    elif failure == "uncatalogued_article":
        (project / docs.CONTENT / "guide/hidden.md").write_text("# Hidden\n")
        source.write_text(source.read_text() + "\n[Hidden](./hidden.md)\n")
    elif failure == "missing_svg":
        (project / docs.DIAGRAMS / "quickstart.svg").unlink()
    elif failure == "escaping_path":
        source.write_text(source.read_text() + "\n[Escape](../../../%2e%2e/outside.md)\n")
    elif failure == "symlink":
        target = project / docs.CONTENT / "guide/conversations.md"
        outside = project.parent / "outside.md"
        target.rename(outside)
        target.symlink_to(outside)
    else:
        target = project / docs.DIAGRAMS / "quickstart.svg"
        target.write_text(target.read_text().replace("</svg>", "<script>alert(1)</script></svg>"))
    script = project / "scripts/product_docs.py"
    script.parent.mkdir(exist_ok=True)
    shutil.copyfile(docs.ROOT / "scripts/product_docs.py", script)
    result = subprocess.run(
        [sys.executable, str(script)],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Documentation check failed:" in result.stderr
