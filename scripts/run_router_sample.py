#!/usr/bin/env python3
"""Run one fresh offline Router calibration through the complete public tracking barrier.

The first adapter supports a normal start/foreground interaction. It is not a
formal S1/S2 sample; event scheduling and ACK-loss calibration are separate steps.
"""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import httpx

if __package__:
    from . import verify_router_a as fixture
else:
    import verify_router_a as fixture

TERMINAL_TASKS = {"completed", "failed", "cancelled"}
TERMINAL_RUNS = {"success", "error", "interrupted", "cancelled", "timeout"}
PROBE = "import json;from router_evaluation_probe import collect;print(json.dumps(collect()))"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def probe(gateway):
    return fixture.docker_python(gateway, PROBE)


def isolation(project):
    result = {}
    for service in ("control", "gateway"):
        container = json.loads(fixture.command(["docker", "inspect", f"{project}-{service}-1"]))[0]
        networks = list(container["NetworkSettings"]["Networks"])
        if len(networks) != 1 or container["HostConfig"].get("PortBindings"):
            raise RuntimeError("App runtime unexpectedly has an ingress/external network")
        network = json.loads(fixture.command(["docker", "network", "inspect", networks[0]]))[0]
        if not network["Internal"]:
            raise RuntimeError("App runtime requires an internal-only network")
        result[service] = {"internal_only": True, "published_ports": 0}
    return result


def bootstrap(client, gateway, api, cfg):
    grant = fixture.native_device(client, gateway, api)
    api(
        "PATCH",
        "me/continuous-config",
        {"enabled": True, "model": "continuous-fixture", "native_budget": 1},
    )
    work = api(
        "POST",
        "me/work-orders",
        {
            "operation_id": "create-" + cfg["logical_operation_id"],
            "goal": "Fix the toy addition. EVAL_OPERATION=" + cfg["logical_operation_id"],
            "project": "demo",
            "grant_id": grant["id"],
        },
    )
    setup = client.post("/__deermate_evaluation/setup", json={"work_id": work["id"]})
    setup.raise_for_status()
    # This is an existing owner work record, never an observer-discovered task
    # handle or invented Native head. All task discovery below uses public APIs.
    fixture.docker_python(
        gateway,
        "import json,sys;from pathlib import Path;"
        "p=Path('/app/backend/.deer-flow/evaluation-work.json');"
        "p.write_text(json.dumps(json.load(sys.stdin)));p.chmod(0o600);print('true')",
        {"work_id": work["id"]},
    )
    return work, setup.json()


def public_tracking(api, thread):
    listed = api("GET", f"threads/{thread}/mcp-tasks")
    return {
        "thread_id": thread,
        "discovery": "owner public thread task list",
        "items": [api("GET", f"threads/{thread}/mcp-tasks/{v['task_id']}") for v in listed],
    }


def barrier_state(evidence, public, view, work, mode, owner):
    workers = evidence["worker_tasks"]
    tasks = evidence["mcp_tasks"]
    public_tasks = public["items"]
    operations = [v for v in evidence["go_records"] if v["kind"] == "operation"]
    native = [v for v in operations if v["data"].get("kind") not in {"router", "assessor"}]
    model = evidence["model_events"]
    reasons = []
    if not workers or not all(v["status"] in TERMINAL_TASKS for v in workers):
        reasons.append("worker_not_terminal")
    if not public_tasks or not all(v["status"] in TERMINAL_TASKS for v in public_tasks):
        reasons.append("owned_public_mcp_not_terminal")
    if {v["task_id"] for v in public_tasks} != {v["id"] for v in tasks}:
        reasons.append("public_mcp_identity_not_reconciled")
    if not tasks or not all(
        v["user_id"] == owner
        and v["thread_id"] == public["thread_id"]
        and v["notification_status"] in {"none", "delivered"}
        and v["notified_version"] >= v["event_version"]
        for v in tasks
    ):
        reasons.append("mcp_owner_or_notification_unsettled")
    if any(v.get("notification_status") not in {"none", "delivered"} for v in public_tasks):
        reasons.append("public_notification_unsettled")
    if not operations or any(v["state"] != "settled" for v in operations):
        reasons.append("go_operations_unsettled")
    if len(native) != (0 if mode == "A" else 1):
        reasons.append("go_native_operation_count")
    if not view["items"] or any(v["state"] != "settled" for v in view["items"]):
        reasons.append("go_inbox_unsettled")
    if mode != "A" and (
        work["data"].get("active_operation")
        or work["data"].get("stage") not in TERMINAL_TASKS | {"verification_required"}
    ):
        reasons.append("go_work_unsettled")
    if not evidence["runs"] or any(
        v["user_id"] != owner or v["status"] not in TERMINAL_RUNS for v in evidence["runs"]
    ):
        reasons.append("related_runs_unsettled")
    if sum(v["kind"] == "model_started" for v in model) != sum(
        v["kind"] == "model_finished" for v in model
    ):
        reasons.append("model_call_in_flight")
    return reasons


def await_barrier(api, gateway, thread, work_id, mode, owner, directory):
    deadline = time.monotonic() + 90
    stable_since, previous = None, None
    samples = []
    while True:
        public = public_tracking(api, thread)
        view = api("GET", "me/router")
        work = api("GET", "me/work-orders/" + work_id)
        evidence = probe(gateway)
        reasons = barrier_state(evidence, public, view, work, mode, owner)
        # Exclude only observer clocks; new calls, effects, runs, notification
        # state or canonical ledger revisions reset the common four-second tail.
        snapshot = {
            "evidence": {k: v for k, v in evidence.items() if k != "clock_ns"},
            "public_tracking": public,
            "router_view": view,
            "work": work,
        }
        fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
        now = time.monotonic()
        if not reasons and fingerprint == previous:
            stable_since = stable_since if stable_since is not None else now
        else:
            stable_since = None
        previous = fingerprint
        sample = {
            "runner_ns": time.monotonic_ns(),
            "service_probe_ns": evidence["clock_ns"],
            "reasons": reasons,
            "fingerprint": fingerprint,
            "model_calls": sum(v["kind"] == "model_started" for v in evidence["model_events"]),
            "worker_statuses": [v["status"] for v in evidence["worker_tasks"]],
            "public_mcp_statuses": [v["status"] for v in public["items"]],
            "notifications": [v.get("notification_status") for v in public["items"]],
            "go_operations": [
                {"id": v["id"], "state": v["state"]}
                for v in evidence["go_records"]
                if v["kind"] == "operation"
            ],
        }
        samples.append(sample)
        with (directory / "barrier-samples.jsonl").open("a") as out:
            out.write(json.dumps(sample) + "\n")
        complete = stable_since is not None and now - stable_since >= 4
        if complete or now >= deadline:
            return {
                "complete": complete,
                "status": "complete" if complete else "unknown",
                "stable_tail_seconds": now - stable_since if stable_since is not None else 0,
                "remaining_reasons": reasons,
                "samples": len(samples),
                "evidence": evidence,
                "public_tracking": public,
                "router_view": view,
                "work": work,
                "runner_observed_ns": time.monotonic_ns(),
            }
        time.sleep(0.25)


def run(args):
    os.umask(0o077)
    if args.scenario != "normal":
        raise ValueError("This calibration step currently supports only --scenario normal")
    if args.port == 2026 or not 1024 <= args.port <= 65535:
        raise ValueError("Use a separate unprivileged fixture port")
    args.logical_operation_id = "normal-" + str(args.seed)
    preflight = fixture.preflight_control(args)
    args.control_image = preflight["image_id"]
    directory = args.work_dir.absolute()
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    save(directory / "image-preflight.json", preflight)
    source = {
        "revision": fixture.command(["git", "rev-parse", "HEAD"], cwd=fixture.ROOT),
        "checkout_dirty": bool(fixture.command(["git", "status", "--porcelain"], cwd=fixture.ROOT)),
        "file_sha256": {
            str(p.relative_to(fixture.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                fixture.ROOT / "scripts/verify_router_a.py",
                *(
                    fixture.ROOT / "tests" / name
                    for name in (
                        "router_evaluation_probe.py",
                        "router_evaluation_model.py",
                        "fake_codex.py",
                        "continuous_native_fixture.py",
                        "continuous_fixture_model.py",
                    )
                ),
            )
        },
    }
    save(directory / "source.json", source)
    project = f"deermate-router-{args.mode.lower()}-{uuid.uuid4().hex[:8]}-fixture"
    key = secrets.token_urlsafe(32)
    bundle, cfg = fixture.prepare(args, directory, project, key)
    gateway = project + "-gateway-1"
    result = {
        "profile": "single offline normal calibration",
        "formal_batch": False,
        "mode": args.mode,
        "scenario": args.scenario,
        "seed": args.seed,
        "passed": False,
        "source": source,
        "project": project,
        "logical_operation_id": cfg["logical_operation_id"],
        "real_provider_calls": 0,
        "real_native_calls": 0,
    }
    try:
        subprocess.run([str(bundle / "start.sh")], check=True, stdout=subprocess.DEVNULL)
        result["app_network_isolation"] = isolation(project)
        owner = json.loads((bundle / "owner.json").read_text())
        with httpx.Client(
            base_url=f"http://localhost:{args.port}", trust_env=False, timeout=20
        ) as client:
            client.post("/api/v1/auth/initialize", json=owner).raise_for_status()
            client.post(
                "/api/v1/auth/login/local",
                data={"username": owner["email"], "password": owner["password"]},
            ).raise_for_status()
            uid = client.get("/api/v1/auth/me").json()["id"]
            result["owner_id"] = uid
            client.headers.update(
                {
                    "X-CSRF-Token": client.cookies["csrf_token"],
                    "X-Expected-User-Id": uid,
                    "X-DeerMate-Evaluation": key,
                }
            )

            def api(method, path, body=None):
                response = client.request(method, "/api/" + path, json=body)
                if response.is_error:
                    raise RuntimeError(f"Fixture API {method} {path}: {response.status_code}")
                return response.json()

            work, setup = bootstrap(client, gateway, api, cfg)
            result.update(work_id=work["id"], fixture_setup=setup)
            start = api(
                "POST",
                "me/router/messages",
                {
                    "operation_id": "start-" + cfg["logical_operation_id"],
                    "text": "EVAL_START " + cfg["logical_operation_id"],
                },
            )
            result["start_inbox"] = start["id"]
            observations = []
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                evidence = probe(gateway)
                observations.append(
                    {
                        "runner_ns": time.monotonic_ns(),
                        "service_ns": evidence["clock_ns"],
                        "native_events": len(evidence["native_events"]),
                    }
                )
                if any(v["kind"] == "native_turn_started" for v in evidence["native_events"]):
                    break
                time.sleep(0.02)
            else:
                raise RuntimeError("The actual original Native turn did not start")
            result["native_observation_samples"] = observations
            runner_send = time.monotonic_ns()
            front = api(
                "POST",
                "me/router/messages",
                {
                    "operation_id": "front-" + cfg["logical_operation_id"],
                    "text": "EVAL_FRONT " + cfg["logical_operation_id"],
                },
            )
            result["foreground_inbox"] = front["id"]
            first = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                view = api("GET", "me/router")
                item = next(v for v in view["items"] if v["id"] == front["id"])
                if "EVAL_VISIBLE " + cfg["logical_operation_id"] in item["data"].get("reply", ""):
                    first = time.monotonic_ns()
                    break
                time.sleep(0.02)
            if first is None:
                raise RuntimeError("No actual foreground response within its deadline")
            thread = (
                view["session"]["data"]["thread_id"]
                if args.mode == "A"
                else work["data"]["thread_id"]
            )
            result.update(
                coordinator_thread=view["session"]["data"]["thread_id"], tracking_thread=thread
            )
            barrier = await_barrier(api, gateway, thread, work["id"], args.mode, uid, directory)
            result["barrier"] = barrier
            service = client.get("/__deermate_evaluation/evidence")
            service.raise_for_status()
            result["service_evidence"] = service.json()
            timing = next(v for v in service.json()["items"] if v["inbox"] == front["id"])
            result["foreground_admission_to_first_ms"] = (
                timing["first_visible_ns"] - timing["admitted_ns"]
            ) / 1e6
            result["client_send_to_first_ms"] = (first - runner_send) / 1e6
            result["client_send_to_end_barrier_ms"] = (
                barrier["runner_observed_ns"] - runner_send
            ) / 1e6
            result["runner_clock_domain"] = (
                "runner-monotonic (never subtracted from Linux service clocks)"
            )
            final = barrier["evidence"]
            tasks = final["worker_tasks"]
            effects = [v for v in final["native_events"] if v["kind"] == "effect"]
            result["passed"] = (
                barrier["complete"]
                and len(tasks) == len(final["mcp_tasks"]) == len(effects) == 1
                and tasks[0]["status"] == "completed"
                and tasks[0]["result"]["validation"]["exit_code"] == 0
                and all(v["status"] == "completed" for v in barrier["public_tracking"]["items"])
                and (args.mode == "A" or barrier["work"]["data"].get("verified") is True)
            )
    except Exception as error:
        result["failure_kind"] = type(error).__name__
        result["failure_message"] = str(error)[:500]
        try:
            result["retained_failure_probe"] = probe(gateway)
        except Exception as probe_error:
            result["failure_probe_error_kind"] = type(probe_error).__name__
        raise
    finally:
        save(directory / "sample.json", result)
        subprocess.run(
            ["docker", "compose", "--project-directory", str(bundle), "stop", "--timeout", "60"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "formal_batch": False,
                "mode": args.mode,
                "receipt": str(directory / "sample.json"),
                "barrier": result["barrier"]["status"],
            }
        )
    )
    return result["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("A", "B", "C"), required=True)
    parser.add_argument("--scenario", choices=("normal", "S1", "S2"), default="normal")
    parser.add_argument("--seed", type=int, default=1101)
    parser.add_argument("--images-config", type=Path, required=True)
    parser.add_argument("--control-image", required=True)
    parser.add_argument("--control-image-id", required=True)
    parser.add_argument("--go", default="go")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=22045)
    parser.add_argument("--subnet", default="192.168.240.0/24")
    parser.add_argument("--edge-subnet", default="192.168.241.0/24")
    raise SystemExit(0 if run(parser.parse_args()) else 1)
