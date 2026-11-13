#!/usr/bin/env python3
"""Fail on design drift across first-party React, embedded Go and extension UI."""

import json
import re
import subprocess
from pathlib import Path

if __package__:
    from .sync_design_tokens import ROOT, load_design, outputs
else:
    from sync_design_tokens import ROOT, load_design, outputs


def sources(root):
    paths = list((root / "frontend/overlay/src").rglob("*"))
    paths += list((root / "backend/internal/controlplane").glob("*.html"))
    paths += list((root / "src/deermate/tooling_ui").rglob("*"))
    return sorted(
        p
        for p in paths
        if p.is_file()
        and p.suffix
        in (".css", ".html", ".tsx", ".jsx", ".ts", ".js", ".mjs", ".scss", ".sass", ".less")
    )


def violations(path, text, *, layer_policy=True):
    issues = []
    if path.suffix in (".scss", ".sass", ".less"):
        issues.append("unregistered stylesheet format; extend the gate before adding it")
    if path.suffix == ".html":
        regions = re.findall(r"<style[^>]*>(.*?)</style>", text, re.S)
    elif path.suffix == ".mjs":
        regions = re.findall(r"style.textContent\s*=\s*`(.*?)`", text, re.S)
    elif path.suffix == ".css":
        regions = [text]
    else:
        regions = []
    for region in regions:
        region = re.sub(r"/\*.*?\*/", "", region, flags=re.S)
        if re.search(r"#[\da-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch)\(", region):
            issues.append("hard-coded color outside design.md")
        if re.search(r"--ds-[\w-]+\s*:", region):
            issues.append("canonical token redefinition outside generated assets")
        for prop, value in re.findall(r"(?:^|[;{])\s*([\w-]+)\s*:\s*([^;{}]+)", region):
            if prop in ("font-size", "border-radius", "box-shadow", "letter-spacing"):
                if not value.strip().startswith("var(--") and value.strip() not in (
                    "inherit",
                    "initial",
                ):
                    issues.append(f"{prop} must use a token")
            if re.fullmatch(r"(?:padding|margin)(?:-[\w-]+)?|(?:row-|column-)?gap", prop):
                if re.search(r"\d+(?:\.\d+)?(?:px|rem)\b", value):
                    issues.append(f"{prop} must use spacing tokens")
            if prop in ("font", "font-size") and re.search(r"\d+(?:\.\d+)?px", value):
                issues.append("font dimensions must use typography tokens")
            if prop in ("color", "background", "background-color", "border-color"):
                if re.search(r"\b(?:red|green|blue|white|black|purple|orange)\b", value):
                    issues.append("named color outside design.md")
        if re.search(r"transition\s*:\s*all\b", region):
            issues.append("transition: all is not allowed")
    for region in regions:
        if re.search(r"\bresize\s*:", region):
            issues.append("native resize is forbidden; use the Textarea primitive")
        for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", region):
            if re.search(r"text-decoration\s*:\s*underline", declarations):
                if not (
                    "prose" in selector
                    or all(
                        re.search(r"(?:^|[\s>])a(?:[\s.:[#]|$)", part.strip())
                        for part in selector.split(",")
                    )
                ):
                    issues.append("underlines are reserved for links and prose")
    if layer_policy and path.suffix in (".tsx", ".jsx"):
        normalized = path.as_posix()
        primitive = "/deermate/ui/" in normalized
        pattern = "/deermate/patterns/" in normalized
        if not primitive and re.search(
            r"<(?:button|input|textarea|select|details|summary)\b", text
        ):
            issues.append("native interactive element outside primitives")
        if not primitive and not pattern:
            classes_to_check = re.findall(r'className\s*=\s*["\']([^"\']*)', text)
            for expression in re.findall(r"className\s*=\s*\{([^}]+)\}", text, re.S):
                classes_to_check.extend(re.findall(r'["\'`]([^"\'`]+)["\'`]', expression))
            for classes in classes_to_check:
                if re.search(
                    r"(?:^|\s)(?:[\w-]+:)*(?:bg-|border(?:-|\b)|rounded(?:-|\b)|shadow(?:-|\b)|ring-|font-|text-(?!left\b|right\b|center\b|ellipsis\b))",
                    classes,
                ):
                    issues.append("visual utilities outside primitives or patterns")
        inline_copy = re.search(r'\b(?:t|text)\(\s*["\'`][^)]*?,\s*["\'`]', text, re.S)
        inline_copy = inline_copy or re.search(
            r'\bzh\s*\?\s*["\'`][^"\'`]+["\'`]\s*:\s*["\'`]', text
        )
        if not primitive and inline_copy:
            issues.append("inline bilingual copy; use the DeerMate dictionary")

    if path.suffix in (".tsx", ".jsx", ".ts", ".js"):
        if path.suffix in (".tsx", ".jsx") and "ds-marketing-" in text:
            issues.append(
                "marketing recipe in product overlay; define a marketing route scope first"
            )
        if re.search(r"(?:bg|text|border|ring|shadow|rounded)-\[(?!var\(--)[^\]]+\]", text):
            issues.append("arbitrary visual utility; use design tokens or a shared recipe")
        if re.search(
            r"(?:bg|text|border)-(?:red|green|blue|violet|cyan|pink|gray|zinc|slate)-\d", text
        ):
            issues.append("independent utility color palette")
        inline_checked = re.sub(
            r'style\s*=\s*\{\s*\{\s*"--dm-index":\s*Math\.min\(index, 5\),?'
            r"\s*\}\s*as React\.CSSProperties\s*\}",
            "",
            text,
        )
        if re.search(r"style\s*=\s*\{\s*\{", inline_checked):
            issues.append(
                "inline visual styles; use shared CSS (typed dynamic motion variables excepted)"
            )
    return sorted(set(issues))


def check(root=ROOT):
    design = load_design(root)
    expected = outputs(design)
    failures = []
    for name, content in expected.items():
        path = root / name
        if not path.exists() or path.read_text() != content:
            failures.append(f"{name}: generated drift; run sync_design_tokens.py")
    legacy = root / "frontend/overlay/src/styles/deermate.css"
    if legacy.exists():
        failures.append("deermate.css must remain deleted")
    budget = design.get("implementation", {}).get("cssBudgetLines", 0)
    historical_limit = 1100
    if root == ROOT:
        history = subprocess.run(
            ["git", "log", "--format=%H", "--", "design.md"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        for commit in history.stdout.splitlines():
            previous = subprocess.run(
                ["git", "show", f"{commit}:design.md"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            match = re.search(r'["\']?cssBudgetLines["\']?\s*:\s*(\d+)', previous.stdout)
            if match:
                historical_limit = min(historical_limit, int(match[1]))
    if not isinstance(budget, int) or not 0 < budget <= historical_limit:
        failures.append(
            f"CSS budget must be positive and cannot increase beyond {historical_limit}"
        )
    handwritten = [
        p
        for p in (root / "frontend/overlay/src").rglob("*.css")
        if str(p.relative_to(root)) not in expected
    ]
    line_count = sum(len(p.read_text().splitlines()) for p in handwritten)
    if line_count > budget:
        failures.append(f"CSS budget exceeded: {line_count} > {budget}")
    for path in handwritten:
        if path.name == "app.css":
            if re.sub(r"/\*.*?\*/|@import[^;]+;|\s+", "", path.read_text(), flags=re.S):
                failures.append("app.css is an import entrypoint only")
        elif not any(
            f"/components/deermate/{layer}/" in path.as_posix() for layer in ("ui", "patterns")
        ):
            failures.append(f"{path.relative_to(root)}: handwritten CSS belongs beside ui/patterns")
    # Unknown custom properties often silently discard a rule: reject rather than fall back.
    definitions = set(re.findall(r"(--[\w-]+)\s*:", "\n".join(expected.values())))
    paths = sources(root)
    texts = {p: p.read_text() for p in paths if str(p.relative_to(root)) not in expected}
    for content in texts.values():
        definitions.update(re.findall(r'(--[\w-]+)["\']?\s*:', content))
    upstream = {
        "--background",
        "--foreground",
        "--border",
        "--accent",
        "--muted",
        "--primary",
        "--sidebar-width",
        "--sidebar-width-icon",
        "--sidebar-accent",
        "--font-geist-sans",
    }
    for path, content in texts.items():
        for issue in violations(path, content):
            failures.append(f"{path.relative_to(root)}: {issue}")
        for token in (
            set(re.findall(r"var\((--(?:dm|ds)-[\w-]+)", content)) - definitions - upstream
        ):
            failures.append(f"{path.relative_to(root)}: undefined token {token}")
    patch_path = root / "frontend/patches.json"
    if patch_path.exists():
        for patch in json.loads(patch_path.read_text()):
            for original, replacement in patch["replace"]:
                native = r"<(?:button|input|textarea|select|details|summary)\b"
                if (
                    len(re.findall(native, replacement)) > len(re.findall(native, original))
                    and "/ui/" not in patch["path"]
                ):
                    failures.append(
                        f"pinned UI {patch['path']}: new native control outside primitives"
                    )
                for issue in violations(Path(patch["path"]), replacement, layer_policy=False):
                    if issue.startswith(("inline", "arbitrary")):
                        continue
                    failures.append(f"pinned UI {patch['path']}: {issue}")
    if failures:
        raise ValueError("\n".join(failures))
    print(f"Design gate passed: {len(paths)} UI files; generated assets and references match.")


if __name__ == "__main__":
    check()
