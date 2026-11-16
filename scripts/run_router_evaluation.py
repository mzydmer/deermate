#!/usr/bin/env python3
"""Freeze a clean offline batch, then execute every planned row exactly once."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from pathlib import Path

if __package__:
    from . import verify_router_a as fixture
else:
    import verify_router_a as fixture

ROOT = Path(__file__).resolve().parents[1]
DATASET = "docs/research/router-dataset-v1.json"
CONFIG = "docs/research/router-offline-config-v1.json"
RUNTIME_FILES = [
    "scripts/run_router_sample.py",
    "scripts/verify_router_a.py",
    "tests/router_evaluation_probe.py",
    "tests/router_evaluation_proxy.py",
    "tests/router_evaluation_model.py",
    "tests/fake_codex.py",
    "tests/continuous_native_fixture.py",
    "tests/continuous_fixture_model.py",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with path.open("x") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")


def plan(kind, config):
    rows = []
    for scenario in ["S1", "S2"]:
        for paired in config["paired_order"]:
            if kind == "repeat" and paired["seed"] != 1101:
                continue
            for mode in paired["order"]:
                name = f"{scenario}-{paired['seed']}-{mode}"
                rows.append(
                    {
                        "scenario": scenario,
                        "seed": paired["seed"],
                        "mode": mode,
                        "order": len(rows) + 1,
                        "sample_path": name + "/sample.json",
                    }
                )
    return rows


def source_identity():
    if fixture.command(["git", "status", "--porcelain"], cwd=ROOT):
        raise RuntimeError("Freeze/execute requires an entirely clean source checkout")
    return fixture.command(["git", "rev-parse", "HEAD"], cwd=ROOT)


def validate_frozen(manifest):
    if source_identity() != manifest["producer_revision"]:
        raise RuntimeError("The actual source revision differs from the frozen producer")
    for name, digest in manifest["harness_file_sha256"].items():
        if sha(ROOT / name) != digest:
            raise RuntimeError("Frozen source artifact changed: " + name)
    for key in ["dataset", "config"]:
        if sha(ROOT / manifest[key]["artifact"]) != manifest[key]["sha256"]:
            raise RuntimeError("Frozen " + key + " differs")


def freeze(args):
    revision = source_identity()
    control = fixture.preflight_control(args)
    if not (
        control["producer_revision"] == control["binary_vcs_revision"] == revision
        and control["producer_source_dirty"] == "false"
        and control["binary_vcs_modified"] == "false"
    ):
        raise RuntimeError(
            "Formal control label and compiled VCS must match the clean frozen source"
        )
    config = json.loads((ROOT / CONFIG).read_text())
    runtime = {p: sha(ROOT / p) for p in RUNTIME_FILES}
    extras = [
        "scripts/run_router_evaluation.py",
        "scripts/judge_router_evaluation.py",
        "scripts/aggregate_router_evaluation.py",
        "scripts/prepare_continuous_fixture.py",
        "scripts/single_host.py",
        "deploy/testing/router-nginx.conf",
        "deploy/deerflow.lock",
    ]
    go_files = subprocess.check_output(
        ["git", "ls-files", "backend"], cwd=ROOT, text=True
    ).splitlines()
    harness = {p: sha(ROOT / p) for p in RUNTIME_FILES + extras + go_files if (ROOT / p).is_file()}
    expected_package = {
        str(p.relative_to(ROOT / "src/deermate")): sha(p)
        for p in sorted((ROOT / "src/deermate").rglob("*.py"))
    }
    import yaml

    images = yaml.safe_load(args.images_config.read_text())
    gateway_tag = images["registry"] + "/deermate-gateway:" + images["tag"]
    gateway = json.loads(fixture.command(["docker", "image", "inspect", gateway_tag]))[0]
    package = json.loads(
        fixture.command(
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--read-only",
                "--user=1000:1000",
                "--entrypoint",
                "/app/backend/.venv/bin/python",
                gateway["Id"],
                "-c",
                "import deermate,json,hashlib;from pathlib import Path;"
                "r=Path(deermate.__file__).parent;print(json.dumps({str(p.relative_to(r)):"
                "hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob('*.py'))}))",
            ]
        )
    )
    if package != expected_package:
        raise RuntimeError("Installed Gateway DeerMate package differs from frozen source")
    parent = None
    if args.kind == "repeat":
        if not args.repeat_of:
            raise ValueError("A separate repeat must identify its original main manifest")
        original = json.loads(args.repeat_of.read_text())
        if not (
            original["kind"] == "main"
            and original["producer_revision"] == revision
            and original["runtime_file_sha256"] == runtime
            and original["control"] == control
            and original["dataset"]["sha256"] == sha(ROOT / DATASET)
            and original["config"]["sha256"] == sha(ROOT / CONFIG)
        ):
            raise ValueError("Repeat must use exactly the same frozen source, artifacts and config")
        parent = sha(args.repeat_of)
    args.root.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "batch_id": str(uuid.uuid4()),
        "kind": args.kind,
        "formal_batch": True,
        "producer_revision": revision,
        "checkout_dirty": False,
        "dataset": {"artifact": DATASET, "sha256": sha(ROOT / DATASET)},
        "config": {"artifact": CONFIG, "sha256": sha(ROOT / CONFIG)},
        "runtime_file_sha256": runtime,
        "harness_file_sha256": harness,
        "harness_sha256": hashlib.sha256(json.dumps(harness, sort_keys=True).encode()).hexdigest(),
        "upstream_revision": fixture.command(
            [sys.executable, "scripts/deerflow_lock.py"], cwd=ROOT
        ),
        "control": control,
        "gateway_image_id": gateway["Id"],
        "gateway_package_sha256": package,
        "images_config_sha256": sha(args.images_config),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "go": fixture.command([args.go, "version"]),
            "docker": fixture.command(["docker", "version", "--format", "{{.Server.Version}}"]),
            "docker_cpus": fixture.command(["docker", "info", "--format", "{{.NCPU}}"]),
            "docker_memory_bytes": fixture.command(["docker", "info", "--format", "{{.MemTotal}}"]),
        },
        "planned": plan(args.kind, config),
        "repeat_of_manifest_sha256": parent,
        "outer_budget_seconds": (36 if args.kind == "main" else 6) * (90 + 180),
        "per_case_process_timeout_seconds": 270,
        "sample_deadline_seconds": 90,
        "warm_state": "Images and pinned BPE cache warm; each owner/home/workspace fresh.",
        "real_provider_calls": 0,
        "real_native_calls": 0,
    }
    write_new(args.root / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "phase": "frozen",
                "manifest": str(args.root / "manifest.json"),
                "producer_revision": revision,
                "dataset_sha256": manifest["dataset"]["sha256"],
                "planned_n": len(manifest["planned"]),
            }
        )
    )


def execute(args):
    manifest = json.loads((args.root / "manifest.json").read_text())
    validate_frozen(manifest)
    if sha(args.images_config) != manifest["images_config_sha256"]:
        raise RuntimeError("Images profile changed after freeze")
    control = fixture.preflight_control(args)
    if control != manifest["control"]:
        raise RuntimeError("Actual control artifact changed after freeze")
    write_new(
        args.root / "execution-started.json", {"manifest_sha256": sha(args.root / "manifest.json")}
    )
    started = time.monotonic()
    rows = []
    source_changed = False
    for item in manifest["planned"]:
        directory = args.root / Path(item["sample_path"]).parent
        status = "not_started_budget"
        if time.monotonic() - started < manifest["outer_budget_seconds"] and not source_changed:
            try:
                validate_frozen(manifest)
            except RuntimeError:
                source_changed = True
                status = "not_started_source_changed"
            if not source_changed:
                cmd = [
                    sys.executable,
                    str(ROOT / "scripts/run_router_sample.py"),
                    "--scenario",
                    item["scenario"],
                    "--mode",
                    item["mode"],
                    "--seed",
                    str(item["seed"]),
                    "--images-config",
                    str(args.images_config.absolute()),
                    "--control-image",
                    args.control_image,
                    "--control-image-id",
                    args.control_image_id,
                    "--go",
                    args.go,
                    "--work-dir",
                    str(directory),
                    "--port",
                    str(args.port),
                    "--subnet",
                    args.subnet,
                    "--edge-subnet",
                    args.edge_subnet,
                    "--formal-batch",
                    "--batch-id",
                    manifest["batch_id"],
                    "--dataset-sha256",
                    manifest["dataset"]["sha256"],
                ]
                log = args.root / (Path(item["sample_path"]).parent.name + ".log")
                try:
                    with log.open("x") as out:
                        process = subprocess.run(
                            cmd,
                            cwd=ROOT,
                            stdout=out,
                            stderr=subprocess.STDOUT,
                            timeout=manifest["per_case_process_timeout_seconds"],
                            check=False,
                        )
                    status = "process_finished" if process.returncode == 0 else "process_failed"
                except subprocess.TimeoutExpired:
                    status = "process_timeout"
                finally:
                    bundle = directory / "bundle"
                    if (bundle / "compose.yaml").exists():
                        with (args.root / (directory.name + "-down.log")).open("x") as out:
                            subprocess.run(
                                [
                                    "docker",
                                    "compose",
                                    "--project-directory",
                                    str(bundle),
                                    "down",
                                    "--timeout",
                                    "60",
                                ],
                                cwd=ROOT,
                                stdout=out,
                                stderr=subprocess.STDOUT,
                                check=True,
                                timeout=90,
                            )
        path = args.root / item["sample_path"]
        if not path.exists():
            directory.mkdir(parents=True, exist_ok=True)
            write_new(
                path,
                {
                    "sample_status": status,
                    "formal_batch": True,
                    "batch_id": manifest["batch_id"],
                    "scenario": item["scenario"],
                    "mode": item["mode"],
                    "seed": item["seed"],
                    "logical_operation_id": item["scenario"].lower() + "-" + str(item["seed"]),
                    "source": {"revision": manifest["producer_revision"]},
                },
            )
        rows.append({**item, "process_status": status, "sample_sha256": sha(path)})
        (args.root / "progress.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "order": item["order"],
                    "scenario": item["scenario"],
                    "mode": item["mode"],
                    "seed": item["seed"],
                    "process_status": status,
                }
            ),
            flush=True,
        )
    write_new(
        args.root / "execution-complete.json",
        {"planned_n": len(rows), "elapsed_seconds": time.monotonic() - started, "rows": rows},
    )


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["freeze", "execute"])
    parser.add_argument("--kind", choices=["main", "repeat"], default="main")
    parser.add_argument("--repeat-of", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--images-config", type=Path, required=True)
    parser.add_argument("--control-image", required=True)
    parser.add_argument("--control-image-id", required=True)
    parser.add_argument("--go", default="go")
    parser.add_argument("--port", type=int, default=22045)
    parser.add_argument("--subnet", default="192.168.240.0/24")
    parser.add_argument("--edge-subnet", default="192.168.241.0/24")
    args = parser.parse_args()
    args.root = args.root.absolute()
    (freeze if args.phase == "freeze" else execute)(args)


if __name__ == "__main__":
    main()
