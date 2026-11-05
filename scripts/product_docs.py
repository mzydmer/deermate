"""Compile the public Markdown catalog; verify links, provenance and doc impact."""

import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = Path("docs/product")
OUTPUT = Path("frontend/overlay/src/components/deermate/product-docs.generated.json")
GROUPS = {"guide", "technical", "changelog"}


def compile_docs(root=ROOT):
    catalog = json.loads((root / CONTENT / "catalog.json").read_text())
    slugs = [page["slug"] for page in catalog]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Duplicate documentation slug")
    pages = []
    for page in catalog:
        slug = page["slug"]
        if not re.fullmatch(r"(?:guide|technical)/[a-z-]+|changelog", slug):
            raise ValueError(f"Invalid documentation slug: {slug}")
        if page["group"] not in GROUPS or not slug.startswith(page["group"]):
            raise ValueError(f"Invalid documentation group: {slug}")
        datetime.date.fromisoformat(page["updated"])
        for field in ("title", "description", "status", "sources"):
            if not page[field]:
                raise ValueError(f"Missing {field}: {slug}")
        for source in page["sources"]:
            target = (root / source).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                raise ValueError(f"Missing source evidence: {source}")
        path = root / CONTENT / f"{slug}.md"
        markdown = path.read_text()
        if not markdown.startswith(f"# {page['title']}\n"):
            raise ValueError(f"Title mismatch: {slug}")
        if len(re.findall(r"^# ", markdown, re.M)) != 1:
            raise ValueError(f"Expected one document title: {slug}")
        if re.search(r"^#{3,6} |<[^>]+>|!\[", markdown, re.M):
            raise ValueError(f"Use h2 sections, plain Markdown and no embedded HTML: {slug}")
        for href in re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown):
            if href.startswith("/docs/") and "#" not in href:
                if href.removeprefix("/docs/") not in slugs:
                    raise ValueError(f"Broken documentation link in {slug}: {href}")
            elif not href.startswith("https://"):
                raise ValueError(f"Unsupported documentation link in {slug}: {href}")
        # Source evidence is for maintainers; never bundle repository internals.
        public = {key: value for key, value in page.items() if key != "sources"}
        pages.append({**public, "body": markdown.split("\n", 1)[1].lstrip()})
    expected = {f"{slug}.md" for slug in slugs}
    actual = {str(path.relative_to(root / CONTENT)) for path in (root / CONTENT).rglob("*.md")}
    if actual != expected:
        raise ValueError(f"Uncatalogued or missing public Markdown: {actual ^ expected}")
    return json.dumps(pages, ensure_ascii=False, indent=2) + "\n"


def changed_paths(root, base):
    # Include staged/unstaged tracked changes and new files during local review.
    tracked = (
        subprocess.check_output(["git", "diff", "--name-only", "-z", base, "--"], cwd=root)
        .decode()
        .split("\0")
    )
    untracked = (
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    )
    return {path for path in tracked + untracked if path}


def check_impact(paths, root=ROOT):
    implementation = {
        path
        for path in paths
        if not path.startswith(("docs/", ".github/ISSUE_TEMPLATE/"))
        and not path.endswith(".md")
        and path != str(OUTPUT)
    }
    if not implementation:
        return
    updated = {p for p in paths if p.startswith("docs/product/") and p.endswith(".md")}
    if (
        any((root / path).is_file() for path in updated - {"docs/product/changelog.md"})
        and "docs/product/changelog.md" in updated
        and (root / "docs/product/changelog.md").is_file()
    ):
        return
    notes = {p for p in paths if p.startswith("docs/change-notes/") and p.endswith(".md")}
    for path in notes:
        if path.endswith("/TEMPLATE.md") or not (root / path).is_file():
            continue
        note = (root / path).read_text()
        if (
            not any(placeholder in note for placeholder in ("替换为", "填写实际", "填写变更名称"))
            and re.search(r"^结论：无需更新客户文档。?$", note, re.M)
            and re.search(r"^理由：\S.{19,}$", note, re.M)
            and re.search(r"^涉及文件：\S.+$", note, re.M)
        ):
            return
    raise ValueError(
        "Implementation changed without public documentation review. Update the affected "
        "docs/product/*.md (and changelog for user-visible changes), or add a reasoned "
        "docs/change-notes/*.md using TEMPLATE.md. See docs/DOCUMENTATION_POLICY.md."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the frontend catalog")
    parser.add_argument(
        "--base", help="also enforce documentation impact against this Git revision"
    )
    args = parser.parse_args()
    try:
        output = compile_docs()
        if args.write:
            (ROOT / OUTPUT).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / OUTPUT).write_text(output)
        elif not (ROOT / OUTPUT).is_file() or (ROOT / OUTPUT).read_text() != output:
            raise ValueError(
                "Stale product documentation. Run python scripts/product_docs.py --write"
            )
        if args.base:
            check_impact(changed_paths(ROOT, args.base))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Documentation check failed: {error}\n")
    print("Product documentation: catalog, source evidence, links and generated content match.")
    if args.base:
        print(f"Documentation impact checked against {args.base}.")


if __name__ == "__main__":
    main()
