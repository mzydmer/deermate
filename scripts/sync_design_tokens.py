#!/usr/bin/env python3
"""Generate shared React/Go tokens and component recipes from design.md."""

import argparse
import copy
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = re.compile(r"^\{([\w.-]+)\}$")


class UniqueLoader(yaml.SafeLoader):
    """Fail closed on duplicate keys instead of silently changing a token."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate design key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_design(root=ROOT):
    text = (root / "design.md").read_text()
    if not text.startswith("---\n"):
        raise ValueError("design.md needs YAML frontmatter")
    return yaml.load(text.split("---\n", 2)[1], Loader=UniqueLoader)


def resolve(design, value, seen=()):
    if isinstance(value, list):
        return [resolve(design, item, seen) for item in value]
    if isinstance(value, dict):
        return {key: resolve(design, item, seen) for key, item in value.items()}
    if not isinstance(value, str):
        return value
    match = REFERENCE.fullmatch(value)
    if not match:
        return value
    path = match[1]
    if path in seen:
        raise ValueError(f"Circular design reference: {path}")
    target = design
    for part in path.split("."):
        if not isinstance(target, dict) or part not in target:
            raise ValueError(f"Unknown design reference: {path}")
        target = target[part]
    return resolve(design, target, (*seen, path))


def variable(path):
    return "--ds-" + path.replace(".", "-")


def leaves(data, prefix=""):
    for name, value in data.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            yield from leaves(value, path)
        elif isinstance(value, (str, int, float)):
            yield path, value


def declaration(value):
    match = REFERENCE.fullmatch(str(value))
    return f"var({variable(match[1])})" if match else str(value)


def token_css(design):
    collections = (
        "colors",
        "fontFamilies",
        "typography",
        "spacing",
        "rounded",
        "sizes",
        "borders",
        "shadows",
        "focus",
        "opacity",
        "tracking",
        "legacyMotion",
        "motion",
    )
    lines = [
        "/* Generated from design.md; run scripts/sync_design_tokens.py. */",
        ":root {",
        "  color-scheme: light;",
    ]
    for collection in collections:
        for path, value in leaves(design[collection], collection):
            if path.endswith("description"):
                continue
            lines.append(f"  {variable(path)}: {declaration(value)};")
    aliases = design["implementation"]["legacyAliases"]
    for alias, name in aliases.items():
        lines.append(f"  --dm-{alias}: var(--ds-colors-{name});")
    for family in ("sans", "mono"):
        lines.append(f"  --dm-font-{family}: var(--ds-fontFamilies-{family});")
    for key, value in design["spacing"].items():
        if key != "none":
            lines.append(f"  --dm-space-{int(value[:-2]) // 4}: var(--ds-spacing-{key});")
    for key in design["rounded"]:
        lines.append(f"  --dm-radius-{key}: var(--ds-rounded-{key});")
    lines.append("  --dm-control-height: var(--ds-sizes-control-md);")
    for key in ("stagger", "quick", "fast", "medium", "slow"):
        lines.append(f"  --duration-{key}: var(--ds-legacyMotion-{key});")
    lines.extend(
        [
            "  --ease-smooth-out: var(--ds-legacyMotion-ease);",
            "  --distance-base: var(--ds-legacyMotion-distance);",
            "}",
        ]
    )
    for name, theme in design["themes"].items():
        lines.extend([f".{name} {{", f"  color-scheme: {name};"])
        for collection in ("colors", "shadows"):
            for key, value in theme.get(collection, {}).items():
                lines.append(f"  {variable(collection + '.' + key)}: {declaration(value)};")
        # CSS aliases resolve at definition time: rebind them in the theme scope.
        for alias, key in aliases.items():
            lines.append(f"  --dm-{alias}: var(--ds-colors-{key});")
        lines.append("}")
    return "\n".join(lines) + "\n"


PROPERTIES = {
    "backgroundColor": "background-color",
    "textColor": "color",
    "borderColor": "border-color",
    "borderWidth": "border-width",
    "rounded": "border-radius",
    "shadow": "box-shadow",
}
CSS_FIELDS = {"height", "width", "minHeight", "maxWidth", "gap", "padding"}


def recipe_declarations(recipe):
    result = []
    for key, value in recipe.items():
        if key == "typography":
            match = REFERENCE.fullmatch(value)
            for attribute in (
                "fontFamily",
                "fontSize",
                "fontWeight",
                "lineHeight",
                "letterSpacing",
            ):
                name = re.sub(r"[A-Z]", lambda m: "-" + m[0].lower(), attribute)
                result.append(f"{name}: var({variable(match[1] + '.' + attribute)})")
        elif key == "padding" and isinstance(value, dict):
            result.extend(f"padding-{axis}: {declaration(item)}" for axis, item in value.items())
        elif key in PROPERTIES or key in CSS_FIELDS:
            name = PROPERTIES.get(key, re.sub(r"[A-Z]", lambda m: "-" + m[0].lower(), key))
            result.append(f"{name}: {declaration(value)}")
    if "borderColor" in recipe:
        result.append("border-style: solid")
        if "borderWidth" not in recipe:
            result.append("border-width: var(--ds-borders-thin)")
    return result


def component_css(design):
    lines = ["/* Generated component recipes from design.md. */"]
    for name, recipe in design["components"].items():
        selector = ".ds-" + name
        lines.append(selector + " { " + "; ".join(recipe_declarations(recipe)) + "; }")
        parts = {
            "title": {"typography": recipe.get("titleTypography")},
            "body": {"typography": recipe.get("bodyTypography")},
            "header": {
                "typography": recipe.get("headerTypography"),
                "backgroundColor": recipe.get("headerBackgroundColor"),
            },
            "cell": {
                "typography": recipe.get("cellTypography"),
                "padding": recipe.get("cellPadding"),
            },
            "row": {"minHeight": recipe.get("rowMinHeight")},
        }
        for part, attributes in parts.items():
            attributes = {key: value for key, value in attributes.items() if value is not None}
            if attributes:
                lines.append(
                    selector
                    + f' [data-design-part="{part}"] {{ '
                    + "; ".join(recipe_declarations(attributes))
                    + "; }"
                )
        for state, overrides in recipe.get("states", {}).items():
            suffix = {"selected": '[aria-selected="true"]', "invalid": '[aria-invalid="true"]'}.get(
                state, ":" + state
            )
            rule = selector + suffix + " { " + "; ".join(recipe_declarations(overrides)) + "; }"
            if state == "hover":
                rule = "@media (hover: hover) { " + rule + " }"
            lines.append(rule)
        for name, overrides in recipe.get("variants", {}).items():
            lines.append(
                selector
                + f'[data-design-variant="{name}"] {{ '
                + "; ".join(recipe_declarations(overrides))
                + "; }"
            )
        mobile = recipe.get("responsive", {}).get("mobile")
        if mobile:
            lines.append(
                "@media (width < "
                + design["breakpoints"]["tablet"]
                + ") { "
                + selector
                + " { "
                + "; ".join(recipe_declarations(mobile))
                + "; } }"
            )
    return "\n".join(lines) + "\n"


def theme_css(design):
    lines = ["/* Generated semantic utilities from design.md. */", "@theme inline {"]
    for name in design["colors"]:
        lines.append(f"  --color-{name}: var(--ds-colors-{name});")
    for name in design["typography"]:
        lines.extend([f"  --text-{name}: var(--ds-typography-{name}-fontSize);",
                      f"  --text-{name}--line-height: var(--ds-typography-{name}-lineHeight);",
                      f"  --text-{name}--letter-spacing: var(--ds-typography-{name}-letterSpacing);"])
    for name in design["rounded"]:
        lines.append(f"  --radius-ds-{name}: var(--ds-rounded-{name});")
    for name in design["sizes"]:
        lines.append(f"  --spacing-ds-{name}: var(--ds-sizes-{name});")
    lines.append("}")
    return "\n".join(lines) + "\n"


def outputs(design):
    resolve(design, design)  # Validate every reference, including unused recipes.
    for theme in design["themes"].values():
        themed = copy.deepcopy(design)
        for collection in ("colors", "shadows"):
            themed[collection].update(theme.get(collection, {}))
        resolve(themed, themed)
    tokens = token_css(design)
    return {
        "frontend/overlay/src/styles/design-tokens.css": tokens,
        "backend/internal/controlplane/design-tokens.css": tokens,
        "frontend/overlay/src/styles/design-components.css": component_css(design),
        "frontend/overlay/src/styles/design-theme.css": theme_css(design),
    }


def sync(check=False):
    design = load_design()
    for template in (ROOT / "backend/internal/controlplane").glob("*.html"):
        if template.read_text().count("/* DEERMATE_DESIGN_TOKENS */") != 1:
            raise ValueError(f"{template.name} must embed design tokens exactly once")
    for name, data in outputs(design).items():
        path = ROOT / name
        if check:
            if not path.exists() or path.read_text() != data:
                raise ValueError(f"Generated design drift: {name}; run sync_design_tokens.py")
        else:
            path.write_text(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    sync(parser.parse_args().check)
    print("design.md, React, Go and component recipes match.")
