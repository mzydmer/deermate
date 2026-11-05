# ruff: noqa: E501
"""Build accessible, dependency-free SVG diagrams from versioned layout data."""

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/diagrams/product/diagrams.json"
DEST = ROOT / "frontend/overlay/public/deermate/docs/diagrams"


def render(diagram):
    esc = html.escape
    width, height = diagram["size"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif" aria-labelledby="title desc">',
        f'<title id="title">{esc(diagram["title"])}</title><desc id="desc">{esc(diagram["description"])}</desc>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#666"/></marker></defs>',
        '<rect width="100%" height="100%" rx="12" fill="#fff"/>',
        f'<text x="32" y="38" font-size="20" font-weight="600" fill="#171717">{esc(diagram["title"])}</text>',
        '<g font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif">',
    ]
    for edge in diagram["edges"]:
        points = " ".join(f"{x},{y}" for x, y in edge["points"])
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#666" stroke-width="1.6" marker-end="url(#arrow)"/>'
        )
        if "label" in edge:
            x, y = edge["at"]
            label = esc(edge["label"])
            parts.append(
                f'<text x="{x}" y="{y}" text-anchor="middle" font-size="13" fill="#555" stroke="#fff" stroke-width="5" paint-order="stroke">{label}</text>'
            )
    for node in diagram["nodes"]:
        x, y, w, h = node["box"]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#fafafa" stroke="#8f8f8f"/>'
        )
        for index, line in enumerate(node["lines"]):
            text_y = y + h / 2 + (index - (len(node["lines"]) - 1) / 2) * 23 + 5
            size = 16 if index == 0 else 13
            parts.append(
                f'<text x="{x + w / 2}" y="{text_y}" text-anchor="middle" font-size="{size}" fill="#171717">{esc(line)}</text>'
            )
    parts.append("</g></svg>\n")
    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    diagrams = json.loads(SOURCE.read_text())
    DEST.mkdir(parents=True, exist_ok=True)
    for name, diagram in diagrams.items():
        path = DEST / (name + ".svg")
        expected = render(diagram)
        if args.write:
            path.write_text(expected)
        elif not path.is_file() or path.read_text() != expected:
            parser.exit(
                1, f"Diagram drift: {name}; run python scripts/product_doc_diagrams.py --write\n"
            )
    print(f"{len(diagrams)} product diagrams match their versioned layout source.")


if __name__ == "__main__":
    main()
