#!/usr/bin/env python3
"""Run one fresh offline calibration through the complete tracking barrier.

S1 sends the reviewed event table; S2 loses one durable coordinator admission ACK.
Calibration runs are never included in the frozen formal sample matrix.
"""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

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
    fixture.docker_python(
        gateway,
        "from pathlib import Path; p=Path('/app/backend/.deer-flow/evaluation-secrets');"
        "p.mkdir(mode=0o700); f=p/'github-read-token';"
        "f.write_text('synthetic-fixture-only-read-token');f.chmod(0o600);print('true')",
    )
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
    if cfg["scenario"] == "S1":
        api(
            "POST",
            "me/automation-rules",
            {
                "operation_id": "observe-" + cfg["logical_operation_id"],
                "source_id": "github",
                "mode": "observe",
                "instruction": "Read references only. No execution is authorized.",
                "event_kinds": ["comment"],
                "native_budget": 0,
            },
        )
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


def observe_foreground(api, inbox, logical, deadline):
    while time.monotonic() < deadline:
        view = api("GET", "me/router")
        item = next(v for v in view["items"] if v["id"] == inbox)
        if "EVAL_VISIBLE " + logical in item["data"].get("reply", ""):
            return time.monotonic_ns(), view
        time.sleep(0.02)
    raise RuntimeError("No actual foreground response within its deadline")


def second_owner(client, api, work_id):
    """Create and authenticate a distinct synthetic admin, without Worker grants."""
    email = "outside-owner-fixture@example.com"
    password = secrets.token_urlsafe(24)
    created = api(
        "POST",
        "v1/admin/users",
        {
            "email": email,
            "password": password,
            "system_role": "admin",
        },
    )
    with httpx.Client(base_url=str(client.base_url), trust_env=False, timeout=20) as outside:
        outside.post(
            "/api/v1/auth/login/local",
            data={
                "username": email,
                "password": password,
            },
        ).raise_for_status()
        me = outside.get("/api/v1/auth/me")
        me.raise_for_status()
        user = me.json()
        if (
            user["id"] != created["id"]
            or user.get("needs_setup")
            or user["id"] == client.headers["X-Expected-User-Id"]
        ):
            raise RuntimeError("The distinct synthetic owner did not authenticate")
        outside.headers.update(
            {
                "X-CSRF-Token": outside.cookies["csrf_token"],
                "X-Expected-User-Id": user["id"],
                "X-DeerMate-Evaluation": client.headers["X-DeerMate-Evaluation"],
            }
        )
        read = outside.get("/api/me/work-orders/" + work_id)
        if read.status_code != 403:
            raise RuntimeError("The authenticated outside owner could access the original work")
        return {
            "user_id": user["id"],
            "cookies": dict(outside.cookies),
            "headers": dict(outside.headers),
            "original_work_read_status": read.status_code,
        }


def s1_plan(cfg, seed):
    plan = [(index / 10, "bound", index) for index in range(1, 7)]
    plan += [(0.25, "foreground", 0), (0.7, "unbound", 8), (0.8, "wrong_owner", 99)]
    rows = []
    for offset, kind, index in sorted(plan):
        body = (
            {
                "operation_id": "front-" + cfg["logical_operation_id"],
                "text": "EVAL_FRONT " + cfg["logical_operation_id"],
            }
            if kind == "foreground"
            else {
                "id": seed * 100 + index,
                "number": 7 if kind in {"bound", "wrong_owner"} else 8,
                "text": (
                    f"Bound {seed}/{index}: reference only for the original work."
                    if kind == "bound"
                    else f"{kind} {seed}: reference only. No execution."
                ),
                "revision": f"revision-{seed}-{index}",
            }
        )
        rows.append(
            {
                "kind": kind,
                "index": index,
                "intended_offset_seconds": offset,
                "input": body,
                "clock_domain": "runner-monotonic",
                "attempt_status": "not_started",
                "sent_runner_ns": None,
                "response_status": None,
                "received_runner_ns": None,
                "error_kind": None,
                "drift_ms": None,
                "due_runner_ns": None,
            }
        )
    return rows


def s2_plan(cfg):
    foreground = next(v for v in s1_plan(cfg, 0) if v["kind"] == "foreground")
    duplicate = dict(foreground)
    duplicate.update(
        kind="duplicate_start",
        intended_offset_seconds=0.5,
        input={
            "operation_id": "start-" + cfg["logical_operation_id"],
            "text": "EVAL_START " + cfg["logical_operation_id"],
        },
    )
    return [foreground, duplicate]


def run_scheduled(client, api, cfg, anchor_ns, deadline, directory, result, outside=None):
    """Each offset owns a sender; HTTP responses never gate later input sends."""
    foreground = {}
    ready = Event()
    deliveries = result["scheduled_deliveries"]
    result["schedule_origin_runner_ns"] = anchor_ns
    result["schedule_origin"] = "runner receipt of actual original Native turn/start"
    log_lock = Lock()

    def send_one(record):
        kind = record["kind"]
        due = anchor_ns + int(record["intended_offset_seconds"] * 1e9)
        record["due_runner_ns"] = due
        identity = (
            outside
            if kind == "wrong_owner"
            else {
                "user_id": client.headers["X-Expected-User-Id"],
                "headers": dict(client.headers),
                "cookies": dict(client.cookies),
            }
        )
        record["actor_user_id"] = identity["user_id"]
        record["expected_user_id_matches_authenticated_user"] = True
        try:
            with httpx.Client(
                base_url=str(client.base_url),
                trust_env=False,
                timeout=20,
                headers=identity["headers"],
                cookies=identity["cookies"],
            ) as sending:
                time.sleep(max(0, (due - time.monotonic_ns()) / 1e9))
                if time.monotonic() >= deadline:
                    record["attempt_status"] = "not_started_deadline"
                    raise TimeoutError("Common sample deadline exhausted before this send")
                sent = time.monotonic_ns()
                record.update(
                    sent_runner_ns=sent, drift_ms=(sent - due) / 1e6, attempt_status="sent"
                )
                path = (
                    "/api/me/router/messages"
                    if kind in {"foreground", "duplicate_start"}
                    else "/__deermate_evaluation/events"
                )
                response = sending.post(
                    path,
                    json=record["input"],
                    timeout=max(0.1, min(20, deadline - time.monotonic())),
                )
                record.update(
                    response_status=response.status_code,
                    received_runner_ns=time.monotonic_ns(),
                    attempt_status="responded",
                )
                record["receipt"] = response.json()
                if kind == "wrong_owner":
                    if response.status_code != 403:
                        raise RuntimeError("The distinct authenticated non-owner was not rejected")
                else:
                    response.raise_for_status()
                if kind == "foreground":
                    foreground.update(inbox=record["receipt"]["id"], runner_send=sent)
        except Exception as error:
            record["error_kind"] = type(error).__name__
            if record["attempt_status"] != "not_started_deadline":
                record["attempt_status"] = (
                    "failed" if record["sent_runner_ns"] else "not_started_error"
                )
        finally:
            record["completed_runner_ns"] = time.monotonic_ns()
            # One final record per planned attempt, including HTTP errors,
            # timeouts and unsent slots. No failed request is retried.
            with log_lock, (directory / "schedule.jsonl").open("a") as out:
                out.write(json.dumps(record) + "\n")
            if kind == "foreground":
                ready.set()

    with ThreadPoolExecutor(max_workers=len(deliveries)) as executor:
        futures = [executor.submit(send_one, record) for record in deliveries]
        try:
            while not ready.wait(0.02):
                if time.monotonic() >= deadline:
                    raise TimeoutError("No foreground admission before the common sample deadline")
            if not foreground:
                raise RuntimeError("Foreground admission failed; see the retained schedule")
            result["foreground_inbox"] = foreground["inbox"]
            first, view = observe_foreground(
                api,
                foreground["inbox"],
                cfg["logical_operation_id"],
                min(deadline, foreground["runner_send"] / 1e9 + 30),
            )
        finally:
            for future in futures:
                future.result()
    if any(row["error_kind"] for row in deliveries):
        raise RuntimeError("At least one scheduled delivery failed; all attempts are retained")
    return {"id": foreground["inbox"]}, foreground["runner_send"], first, view


def run_s1(client, api, cfg, seed, anchor_ns, deadline, directory, result, outside):
    result.setdefault("scheduled_deliveries", s1_plan(cfg, seed))
    return run_scheduled(client, api, cfg, anchor_ns, deadline, directory, result, outside)


def collect_fault(gateway):
    # Called only after the public recovery driver has finished (or failed).
    # The driver cannot consume the observer's tracking IDs or run handles.
    return fixture.docker_python(
        gateway,
        "import json;from pathlib import Path;"
        "p=Path('/app/backend/.deer-flow/evaluation-fault.jsonl');"
        "print(json.dumps([json.loads(v) for v in p.read_text().splitlines()] "
        "if p.exists() else []))",
    )


def s2_contract(result):
    events = result["fault_events"]
    barriers = [v for v in events if v["kind"] == "durable_barrier"]
    drops = [v for v in events if v["kind"] == "ack_dropped"]
    conditions = {
        "exactly_one_actual_durable_barrier": len(barriers) == 1,
        "exactly_one_actual_ack_drop": len(drops) == 1,
        "no_injection_errors": not any(
            v["kind"]
            in {
                "observer_error",
                "barrier_not_reached",
                "upstream_not_success",
                "upstream_not_admitted",
                "proxy_request_error",
            }
            for v in events
        ),
    }
    if len(barriers) == len(drops) == 1:
        durable, drop = barriers[0], drops[0]
        proof = durable["proof"]
        original = proof["original_go_operation"]
        final = result["barrier"]
        operations = [v for v in final["evidence"]["go_records"] if v["kind"] == "operation"]
        op = next((v for v in operations if v["id"] == original), None)
        duplicate = next(
            v for v in result["scheduled_deliveries"] if v["kind"] == "duplicate_start"
        )
        conditions.update(
            zero_response_bytes_before_close=drop.get("response_bytes_sent_to_go") == 0,
            barrier_precedes_drop=(
                durable["clock_domain"] == drop["clock_domain"] and durable["ns"] <= drop["ns"]
            ),
            original_operation_recovered=(
                op is not None
                and op["parent"] == result["start_inbox"]
                and op["state"] == "settled"
                and op["owner"] == result["owner_id"]
                and op["data"].get("run_id") == proof["original_run_id"]
            ),
            normal_query_recovers_original_run=any(
                v["kind"] == "original_query"
                and v["ns"] > drop["ns"]
                and v["clock_domain"] == drop["clock_domain"]
                and v.get("upstream_status") == 200
                and v.get("known") is True
                and v.get("original_go_operation") == original
                and v.get("run_id") == proof["original_run_id"]
                for v in events
            ),
            duplicate_owner_input_same_original_inbox=(
                duplicate.get("response_status") == 200
                and duplicate.get("receipt", {}).get("id") == result["start_inbox"]
            ),
            public_tracking_recovers_original_task=(
                {v["task_id"] for v in final["public_tracking"]["items"]} == {proof["tracking_id"]}
                and final["public_tracking"]["thread_id"] == proof["tracking_thread"]
            ),
            full_tracking_barrier=final["complete"],
        )
    return {
        "target": "initial Router/coordinator admission ACK",
        "conditions": conditions,
        "passed": all(conditions.values()),
    }


def s1_contract(barrier, deliveries, work_id, owner, mode):
    evidence = barrier["evidence"]
    events = [v for v in evidence["go_records"] if v["kind"] == "event"]
    bound_inputs = [v for v in deliveries if v["kind"] == "bound"]
    bound_ids = {v["receipt"]["event"]["id"] for v in bound_inputs}
    unbound = next(v for v in deliveries if v["kind"] == "unbound")
    unbound_id = unbound["receipt"]["event"]["id"]
    calls = [v for v in evidence["model_events"] if v["kind"] == "model_started"]
    bound_read, unbound_read, exact_bodies = set(), False, True
    for call in calls:
        refs = {v["id"] for v in call.get("event_refs", [])}
        bound_read |= refs & bound_ids
        unbound_read |= unbound_id in refs
        for delivered in bound_inputs + [unbound]:
            if delivered["receipt"]["event"]["id"] in refs:
                exact_bodies &= delivered["input"]["text"] in call.get("event_context_text", "")
    conditions = {
        "all_seven_inputs_preserved": len(events) == 7 and len(bound_ids) == 6,
        "bound_events_same_original_work": all(
            v["owner"] == owner and v["parent"] == work_id and v["state"] == "context"
            for v in events
            if v["id"] in bound_ids
        )
        and len([v for v in events if v["id"] in bound_ids]) == 6,
        "outside_owner_rejected": next(v for v in deliveries if v["kind"] == "wrong_owner")[
            "response_status"
        ]
        == 403
        and next(v for v in deliveries if v["kind"] == "wrong_owner")["actor_user_id"] != owner
        and next(v for v in deliveries if v["kind"] == "wrong_owner")[
            "expected_user_id_matches_authenticated_user"
        ],
        "all_accepted_events_owned_by_original_owner": all(v["owner"] == owner for v in events),
        "unbound_has_no_work_association": any(
            v["id"] == unbound_id and not v["parent"] and v["state"] not in {"context", "attached"}
            for v in events
        ),
        "unbound_event_traversed_router": unbound_read,
        "exact_bounded_bodies_read": exact_bodies,
        "bound_router_factor": not bound_read if mode == "C" else bound_read == bound_ids,
    }
    return {
        "conditions": conditions,
        "passed": all(conditions.values()),
        "bound_event_ids": sorted(bound_ids),
        "bound_read_ids": sorted(bound_read),
        "unbound_event_id": unbound_id,
        "bound_router_model_calls": sum(
            bool({v["id"] for v in c.get("event_refs", [])} & bound_ids) for c in calls
        ),
    }


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


def await_barrier(api, gateway, thread, work_id, mode, owner, directory, deadline=None):
    deadline = deadline if deadline is not None else time.monotonic() + 90
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
    if getattr(args, "formal_batch", False) and args.duplicate_effect_negative_control:
        raise ValueError("Negative controls must stay separate from formal batches")
    startup_started = time.monotonic()
    if args.port == 2026 or not 1024 <= args.port <= 65535:
        raise ValueError("Use a separate unprivileged fixture port")
    args.logical_operation_id = args.scenario.lower() + "-" + str(args.seed)
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
                        "router_evaluation_proxy.py",
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
        "profile": "single offline " + args.scenario + " calibration",
        "formal_batch": getattr(args, "formal_batch", False),
        "batch_id": getattr(args, "batch_id", None),
        "dataset_sha256": getattr(args, "dataset_sha256", None),
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
    if args.scenario == "S1":
        result["scheduled_deliveries"] = s1_plan(cfg, args.seed)
    elif args.scenario == "S2":
        result["scheduled_deliveries"] = s2_plan(cfg)
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
            outside = None
            if args.scenario == "S1":
                outside = second_owner(client, api, work["id"])
                result["outside_owner"] = {
                    "user_id": outside["user_id"],
                    "authenticated": True,
                    "original_work_read_status": outside["original_work_read_status"],
                }
                result["scheduled_deliveries"] = s1_plan(cfg, args.seed)
            sample_deadline = time.monotonic() + 90
            result["startup_elapsed_seconds"] = time.monotonic() - startup_started
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
            deadline = min(sample_deadline, time.monotonic() + 30)
            while time.monotonic() < deadline:
                observation_started = time.monotonic_ns()
                evidence = probe(gateway)
                observations.append(
                    {
                        "probe_started_runner_ns": observation_started,
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
            if args.scenario in {"S1", "S2"}:
                front, runner_send, first, view = run_scheduled(
                    client,
                    api,
                    cfg,
                    observations[-1]["runner_ns"],
                    sample_deadline,
                    directory,
                    result,
                    outside,
                )
            else:
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
                first, view = observe_foreground(
                    api,
                    front["id"],
                    cfg["logical_operation_id"],
                    min(sample_deadline, time.monotonic() + 30),
                )
            thread = (
                view["session"]["data"]["thread_id"]
                if args.mode == "A"
                else work["data"]["thread_id"]
            )
            result.update(
                coordinator_thread=view["session"]["data"]["thread_id"], tracking_thread=thread
            )
            barrier = await_barrier(
                api,
                gateway,
                thread,
                work["id"],
                args.mode,
                uid,
                directory,
                deadline=sample_deadline,
            )
            result["barrier"] = barrier
            service = client.get("/__deermate_evaluation/evidence")
            service.raise_for_status()
            result["service_evidence"] = service.json()
            timing = next(v for v in service.json()["items"] if v["inbox"] == front["id"])
            result["service_admission_to_reply_flush_ms"] = (
                (timing["first_visible_ns"] - timing["admitted_ns"]) / 1e6
                if timing.get("first_visible_ns") is not None
                else None
            )
            result["client_send_to_complete_read_ms"] = (first - runner_send) / 1e6
            result["foreground_sent_runner_ns"] = runner_send
            result["foreground_complete_read_runner_ns"] = first
            result["metric_semantics"] = {
                "service": "durable admission -> successful flush of actual complete JSON reply",
                "visibility_limit": "transport boundary; not exact browser display timing",
                "client": "send -> complete JSON read containing the original foreground marker",
                "clock_domains": "Linux service and client clocks stay separate; no subtraction",
                "no_streaming_token_claim": True,
            }
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
            if args.scenario == "S1":
                result["s1_contract"] = s1_contract(
                    barrier,
                    result["scheduled_deliveries"],
                    work["id"],
                    uid,
                    args.mode,
                )
                result["passed"] = result["passed"] and result["s1_contract"]["passed"]
            elif args.scenario == "S2":
                result["fault_events"] = collect_fault(gateway)
                result["fault_evidence_collected_after_recovery_driver"] = True
                result["s2_contract"] = s2_contract(result)
                result["passed"] = result["passed"] and result["s2_contract"]["passed"]
    except Exception as error:
        result["failure_kind"] = type(error).__name__
        result["failure_message"] = str(error)[:500]
        try:
            result["retained_failure_probe"] = probe(gateway)
        except Exception as probe_error:
            result["failure_probe_error_kind"] = type(probe_error).__name__
        raise
    finally:
        if args.scenario == "S2" and "fault_events" not in result:
            try:
                result["fault_events"] = collect_fault(gateway)
                result["fault_evidence_collected_after_recovery_driver"] = True
            except Exception as fault_error:
                result["fault_evidence_error_kind"] = type(fault_error).__name__
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
                "formal_batch": result["formal_batch"],
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
    parser.add_argument("--duplicate-effect-negative-control", action="store_true")
    parser.add_argument("--formal-batch", action="store_true")
    parser.add_argument("--batch-id")
    parser.add_argument("--dataset-sha256")
    parser.add_argument("--images-config", type=Path, required=True)
    parser.add_argument("--control-image", required=True)
    parser.add_argument("--control-image-id", required=True)
    parser.add_argument("--go", default="go")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=22045)
    parser.add_argument("--subnet", default="192.168.240.0/24")
    parser.add_argument("--edge-subnet", default="192.168.241.0/24")
    raise SystemExit(0 if run(parser.parse_args()) else 1)
