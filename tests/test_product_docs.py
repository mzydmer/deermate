"""Public docs cannot silently drift or disappear from implementation changes."""

import json
import shutil

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
    page.write_text(page.read_text() + "\n[Missing](/docs/guide/missing)\n")
    with pytest.raises(ValueError, match="Broken documentation link"):
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
    path.parent.mkdir()
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
