#!/usr/bin/env python3
"""Bounded synthetic corpus and API timing on a named, credential-free fixture."""

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

LOAD = (Path(__file__).resolve().parents[1] / "tests/continuous_fixture_load.py").read_text()


def verify(args):
    parsed = urlsplit(args.url)
    if (
        parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.port == 2026
        or parsed.scheme != "http"
        or not args.project.startswith("deermate-")
        or not args.project.endswith(("-check", "-fixture"))
    ):
        raise ValueError("A separate named loopback fixture is required")
    owner = json.loads(args.owner_file.read_text())
    gateway = args.project + "-gateway-1"
    label = subprocess.check_output(
        [
            "docker",
            "inspect",
            "--format",
            '{{ index .Config.Labels "com.docker.compose.project" }}',
            gateway,
        ],
        text=True,
    ).strip()
    assert label == args.project
    with httpx.Client(base_url=args.url, trust_env=False, timeout=20) as client:
        client.post(
            "/api/v1/auth/login/local",
            data={"username": owner["email"], "password": owner["password"]},
        ).raise_for_status()
        identity = client.get("/api/v1/auth/me").json()
        assert [v["name"] for v in client.get("/api/models").json()["models"]] == [
            "continuous-fixture"
        ]
        assert client.get("/api/agent-authorizations").json()["devices"] == []
        client.headers.update(
            {"X-CSRF-Token": client.cookies["csrf_token"], "X-Expected-User-Id": identity["id"]}
        )
        corpus = json.loads(
            subprocess.check_output(
                ["docker", "exec", "-i", gateway, "/app/backend/.venv/bin/python", "-c", LOAD],
                input=json.dumps({"owner": identity["id"]}),
                text=True,
            )
        )
        before = client.get("/api/me/continuous-config").json()["reserved"]
        endpoints = {
            "list": "/api/me/work-orders",
            "detail": "/api/me/work-orders/load-work-00000",
            "context": "/api/me/work-orders/load-work-00000/context",
            "search": "/api/me/work-orders/search?q=synthetic",
        }
        timings = {}
        for name, endpoint in endpoints.items():
            samples = []
            first = None
            for index in range(101):
                start = time.perf_counter()
                response = client.get(endpoint)
                response.raise_for_status()
                elapsed = (time.perf_counter() - start) * 1000
                if index == 0:
                    first = elapsed
                else:
                    samples.append(elapsed)
            timings[name] = {
                "samples": len(samples),
                "concurrency": 1,
                "first_read_ms": round(first, 3),
                "p50_ms": round(statistics.median(samples), 3),
                "p95_ms": round(sorted(samples)[94], 3),
            }
        after = client.get("/api/me/continuous-config").json()["reserved"]
        assert before == after, "Read-only refresh invoked a model or Native admission"
    stats = subprocess.check_output(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            *[
                args.project + "-" + name + "-1"
                for name in ("gateway", "control", "frontend", "nginx")
            ],
        ],
        text=True,
    )
    states = []
    for name in ("gateway", "control", "frontend", "nginx"):
        state = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .State}}",
                    args.project + "-" + name + "-1",
                ],
                text=True,
            )
        )
        states.append(
            {
                "service": name,
                "running": state["Running"],
                "oom_killed": state["OOMKilled"],
                "health": state.get("Health", {}).get("Status"),
            }
        )
    passed = all(v["p95_ms"] <= 300 for v in timings.values()) and all(
        v["running"] and not v["oom_killed"] for v in states
    )
    receipt = {
        "schema_version": 1,
        "passed": passed,
        "profile": "isolated-synthetic-container-load",
        "corpus": corpus,
        "timings": timings,
        "container_states": states,
        "container_stats": [json.loads(line) for line in stats.splitlines()],
        "reserved_before": before,
        "reserved_after": after,
        "running_memory_limit_mib": 1472,
        "limits": (
            "First-read is not a cold filesystem measurement. "
            "No real models, Native processes or 2 GiB cloud-host claim."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps({"passed": passed, "p95_ms": {name: v["p95_ms"] for name, v in timings.items()}})
    )
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", type=Path, required=True)
    verify(parser.parse_args())
