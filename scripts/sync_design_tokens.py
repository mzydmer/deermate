#!/usr/bin/env python3
"""Keep the Go management UI on the same canonical CSS tokens as React."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sync(check=False):
    source = ROOT / "frontend/overlay/src/styles/design-tokens.css"
    destination = ROOT / "backend/internal/controlplane/design-tokens.css"
    data = source.read_bytes()
    template = ROOT / "backend/internal/controlplane/admin.html"
    if template.read_bytes().count(b"/* DEERMATE_DESIGN_TOKENS */") != 1:
        raise ValueError("Management page must embed shared design tokens exactly once")
    if check:
        if not destination.exists() or destination.read_bytes() != data:
            raise ValueError("Design tokens drifted: run python scripts/sync_design_tokens.py")
    else:
        destination.write_bytes(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    sync(arguments.check)
    print("React and Go design tokens match.")
