"""Build identities, checksums and isolated wheel smoke for the public Alpha."""

import argparse
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import tempfile
import time
import tomllib
import urllib.request
import venv
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "mzydmer/deermate"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, **kwargs):
    return subprocess.check_output(argv, text=True, **kwargs).strip()


def metadata(root=ROOT, *, tag=None, publishing=False, today=None):
    config = json.loads((root / "releases/alpha.json").read_text())
    package = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    cff = yaml.safe_load((root / "CITATION.cff").read_text())
    actual_tag = tag or config["tag"]
    if not re.fullmatch(r"v(\d+\.\d+\.\d+)-alpha\.(\d+)", actual_tag):
        raise ValueError("An explicit vMAJOR.MINOR.PATCH-alpha.N tag is required")
    base, number = actual_tag[1:].split("-alpha.")
    if not (
        actual_tag == config["tag"]
        and config["version"] == actual_tag[1:] == str(cff.get("version"))
        and config["worker_version"] == package["version"] == base + "a" + number
        and config["prerelease"] is True
        and config["public_oci_images"] == []
    ):
        raise ValueError("Tag, CFF, Worker version or public artifact scope differs")
    stamp = config["release_date_utc"]
    if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
        raise ValueError("Release date must be an explicit UTC calendar date")
    parsed = date.fromisoformat(stamp)
    if str(cff.get("date-released")) != stamp:
        raise ValueError("CFF and release policy dates differ")
    current = today or datetime.now(UTC).date()
    if parsed > current or (publishing and parsed != current):
        raise ValueError("Publication must occur on the declared actual UTC date")
    if any(field in cff for field in ("doi", "preferred-citation")):
        raise ValueError("No DOI or preferred-paper identity has been assigned")
    return config


def clean_source(root=ROOT):
    if command(["git", "status", "--porcelain"], cwd=root):
        raise ValueError("Release candidates require a clean source checkout")
    revision = command(["git", "rev-parse", "HEAD"], cwd=root)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("A full source SHA is required")
    return revision


def files(directory, version):
    expected = {f"deermate-{version}-py3-none-any.whl", f"deermate-{version}.tar.gz"}
    actual = {
        p.name for p in directory.iterdir() if p.suffix == ".whl" or p.name.endswith(".tar.gz")
    }
    if actual != expected:
        raise ValueError("Release directory must contain exactly the expected wheel and sdist")
    result = []
    for name in sorted(expected):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Release artifacts must be regular files")
        result.append(
            {
                "name": name,
                "sha256": digest(path),
                "size": path.stat().st_size,
                "platform": "py3-none-any" if name.endswith(".whl") else "source",
            }
        )
    return result


def prepare(directory, *, ci_run_id=None, root=ROOT, build_identity=None):
    config = metadata(root)
    revision = clean_source(root)
    upstream = (root / "deploy/deerflow.lock").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", upstream):
        raise ValueError("Invalid fixed DeerFlow revision")
    artifacts = files(directory, config["worker_version"])
    proof = {"run_id": None, "source_sha": revision, "verified_success": False, "url": None}
    if ci_run_id is not None:
        if __package__:
            from .release_publish import successful_ci
        else:
            from release_publish import successful_ci
        proof = successful_ci(revision, ci_run_id)
    manifest = {
        **config,
        "source_sha": revision,
        "source_url": f"https://github.com/{REPOSITORY}/tree/{revision}",
        "deerflow_sha": upstream,
        "artifacts": artifacts,
        "ci": proof,
        "build_run_id": (build_identity or {}).get("build_run_id", os.environ.get("GITHUB_RUN_ID")),
        "publication_run_id": os.environ.get("GITHUB_RUN_ID") if build_identity else None,
        "publication_status": "verified_candidate" if ci_run_id else "candidate_not_published",
        "builder": (build_identity or {}).get(
            "builder", {"python": platform.python_version(), "platform": platform.platform()}
        ),
    }
    manifest_path = directory / "manifest.json"
    if manifest_path.exists() or (directory / "SHA256SUMS").exists():
        raise FileExistsError("Do not overwrite a prepared release candidate")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    paths = [directory / v["name"] for v in artifacts] + [manifest_path]
    (directory / "SHA256SUMS").write_text(
        "".join(f"{digest(p)}  {p.name}\n" for p in sorted(paths))
    )
    return manifest


def verify(directory, *, root=ROOT, require_ci=False):
    manifest = json.loads((directory / "manifest.json").read_text())
    config = metadata(root, tag=manifest["tag"])
    if any(manifest.get(k) != v for k, v in config.items()):
        raise ValueError("Candidate metadata differs from the actual source policy")
    if manifest["source_sha"] != clean_source(root):
        raise ValueError("Candidate source is not this clean checkout")
    if manifest["deerflow_sha"] != (root / "deploy/deerflow.lock").read_text().strip():
        raise ValueError("Candidate DeerFlow revision differs")
    if files(directory, config["worker_version"]) != manifest["artifacts"]:
        raise ValueError("Artifact checksum, size or platform differs")
    expected = {v["name"]: v["sha256"] for v in manifest["artifacts"]}
    expected["manifest.json"] = digest(directory / "manifest.json")
    recorded = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] in recorded:
            raise ValueError("Malformed or duplicate checksum entry")
        recorded[match[2]] = match[1]
    if recorded != expected:
        raise ValueError("SHA256SUMS does not cover exactly the provided artifacts")
    if require_ci and not (
        manifest["ci"]["verified_success"] is True
        and isinstance(manifest["ci"]["run_id"], int)
        and manifest["ci"]["source_sha"] == manifest["source_sha"]
    ):
        raise ValueError("A successful CI run for the exact source SHA is required")
    return manifest


def smoke(directory, *, root=ROOT):
    manifest = verify(directory, root=root)
    wheel = next(directory / v["name"] for v in manifest["artifacts"] if v["name"].endswith(".whl"))
    with tempfile.TemporaryDirectory(prefix="deermate-release-smoke-") as temporary:
        work = Path(temporary)
        environment = work / "venv"
        venv.create(environment, with_pip=True)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("DEERMATE_EVALUATION_CONFIG", None)
        env.pop("GITHUB_TOKEN", None)
        env.pop("GH_TOKEN", None)
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-cache-dir", str(wheel)],
            cwd=work,
            env=env,
            check=True,
        )
        subprocess.run(
            [str(python), "-I", "-m", "deermate.cli", "--help"],
            cwd=work,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        installed = command(
            [
                str(python),
                "-I",
                "-c",
                "import importlib.metadata;print(importlib.metadata.version('deermate'))",
            ],
            cwd=work,
            env=env,
        )
        if installed != manifest["worker_version"]:
            raise ValueError("Installed wheel version differs")
        project = work / "project"
        project.mkdir()
        config = work / "worker.toml"
        config.write_text(
            f"state_dir = {json.dumps(str(work / 'state'))}\n"
            f"[projects.demo]\nroot = {json.dumps(str(project))}\n"
            "allow_write = false\n"
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with (work / "worker.log").open("w") as output:
            child = subprocess.Popen(
                [
                    str(python),
                    "-I",
                    "-m",
                    "deermate.cli",
                    "--config",
                    str(config),
                    "--port",
                    str(port),
                    "serve",
                ],
                cwd=work,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                            health = json.load(r)
                        if health.get("status") == "ok":
                            break
                    except (OSError, ValueError) as error:
                        if child.poll() is not None:
                            raise RuntimeError(
                                "Fresh installed Worker exited before readiness"
                            ) from error
                    time.sleep(0.1)
                else:
                    raise TimeoutError("Installed Worker did not become ready")
            finally:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        # No task is submitted; no Codex process or Provider call is necessary.
        return {
            "passed": True,
            "source_sha": manifest["source_sha"],
            "wheel_sha256": digest(wheel),
            "installed_version": installed,
            "platform": platform.system().lower() + "/" + platform.machine(),
            "cli_help": True,
            "worker_ready": True,
            "native_tasks_submitted": 0,
            "real_provider_calls": 0,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify", "smoke"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--ci-run-id", type=int)
    parser.add_argument("--require-ci", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if args.action == "prepare":
        result = prepare(directory, ci_run_id=args.ci_run_id)
    elif args.action == "smoke":
        result = smoke(directory)
    else:
        result = verify(directory, require_ci=args.require_ci)
    if args.receipt:
        with args.receipt.open("x") as out:
            json.dump(result, out, ensure_ascii=False, indent=2)
            out.write("\n")
    print(json.dumps({"action": args.action, "source_sha": result["source_sha"], "passed": True}))


if __name__ == "__main__":
    main()
