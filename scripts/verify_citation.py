"""Check the project's CFF identity and exports using an isolated pinned converter."""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONVERTER_VERSION = "2.0.0"
REPOSITORY = "https://github.com/mzydmer/deermate"


def verify(converter, root=ROOT):
    def run(*args):
        return subprocess.run([str(converter), *map(str, args)], capture_output=True, text=True)

    version = run("--version")
    if version.returncode or version.stdout.strip() != CONVERTER_VERSION:
        raise ValueError("Use isolated cffconvert==2.0.0")
    source = root / "CITATION.cff"
    data = yaml.safe_load(source.read_text())
    expected = {
        "cff-version": "1.2.0",
        "type": "software",
        "title": "DeerMate",
        "authors": [{"name": "DeerMate contributors"}],
        "repository-code": REPOSITORY,
        "url": REPOSITORY,
        "license": "MIT",
    }
    if any(data.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "CFF must describe DeerMate software with the approved collective identity"
        )
    if "Copyright (c) 2026 DeerMate contributors" not in (root / "LICENSE").read_text():
        raise ValueError("Review citation authors against the MIT license")
    # There is no public release/DOI in issue #6. Issue #7 owns adding actual release metadata.
    if any(key in data for key in ("version", "date-released", "doi", "preferred-citation")):
        raise ValueError(
            "Unreleased citation must not invent publication or preferred-paper metadata"
        )
    validation = run("--validate", "-i", source)
    if validation.returncode:
        raise ValueError("cffconvert rejected CITATION.cff: " + validation.stderr.strip())
    missing = {}
    with tempfile.TemporaryDirectory(prefix="deermate-citation-") as temp:
        for key in ("cff-version", "message", "title", "authors"):
            invalid = Path(temp) / f"missing-{key}.cff"
            invalid.write_text(yaml.safe_dump({k: v for k, v in data.items() if k != key}))
            result = run("--validate", "-i", invalid)
            if result.returncode == 0:
                raise ValueError(f"Missing required field was accepted: {key}")
            missing[key] = result.returncode
    exports = {}
    for name in ("apalike", "bibtex"):
        result = run("-i", source, "--format", name)
        if result.returncode or not all(
            value in result.stdout
            for value in (data["title"], data["authors"][0]["name"], REPOSITORY)
        ):
            raise ValueError(f"Inconsistent {name} title/authors/repository export")
        if name == "bibtex" and not re.search(r"title\s*=.*DeerMate", result.stdout):
            raise ValueError("BibTeX export lost the software title")
        exports[name] = result.stdout.strip()
    return {
        "passed": True,
        "converter_version": version.stdout.strip(),
        "cff_version": "1.2.0",
        "type": "software",
        "authors": data["authors"],
        "repository": REPOSITORY,
        "publication_fields_omitted": True,
        "required_field_exit_codes": missing,
        "exports": exports,
        "limits": (
            "Local CFF/APA-like/BibTeX checks; real GitHub citation UI/export is a separate check."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cffconvert", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.cffconvert.resolve())
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Citation check failed: {error}\n")
    print("CFF schema, four missing-field counterexamples and APA-like/BibTeX identities passed.")


if __name__ == "__main__":
    main()
