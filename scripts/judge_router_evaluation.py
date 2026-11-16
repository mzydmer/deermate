#!/usr/bin/env python3
"""Independently judge synthetic Router records; never trust runner verdict fields."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def observed_counts(raw):
    barrier = raw.get("barrier") if isinstance(raw.get("barrier"), dict) else {}
    evidence = barrier.get("evidence") or raw.get("retained_failure_probe", {})
    if not isinstance(evidence, dict):
        return {}
    result = {}
    presence = evidence.get("observation_presence", {})
    native = evidence.get("native_events")
    if (
        isinstance(native, list)
        and all(isinstance(v, dict) for v in native)
        and presence.get("native_events", bool(native))
    ):
        result["effects"] = sum(v.get("kind") == "effect" for v in native)
        result["roots"] = len(
            {
                v.get("root")
                for v in native
                if v.get("kind") == "native_turn_started" and v.get("root")
            }
        )
    rpc = evidence.get("native_rpc")
    if (
        isinstance(rpc, list)
        and all(isinstance(v, dict) for v in rpc)
        and presence.get("native_rpc", bool(rpc))
    ):
        result["roots"] = sum(v.get("method") == "thread/start" for v in rpc)
    model = evidence.get("model_events")
    if (
        isinstance(model, list)
        and all(isinstance(v, dict) for v in model)
        and presence.get("model_events", bool(model))
    ):
        calls = [v for v in model if v.get("kind") == "model_started"]
        result["model_calls"] = len(calls)
        result["roles_calls"] = dict(Counter(v.get("role", "unknown") for v in calls))
        result["roles_input_bytes"] = {
            role: sum(
                v.get("input_bytes", 0)
                for v in calls
                if v.get("role", "unknown") == role and isinstance(v.get("input_bytes"), int)
            )
            for role in result["roles_calls"]
        }
    if "fault_events" in raw:
        result["recovery_observed"] = any(
            v.get("kind") == "fault_reserved" for v in raw["fault_events"]
        )
    return result


def judge(raw, dataset, manifest=None):
    checks, metrics = {}, observed_counts(raw)

    def require(name, value):
        checks[name] = bool(value)

    try:
        b = raw["barrier"]
        e = b["evidence"]
        owner, mode, logical = raw["owner_id"], raw["mode"], raw["logical_operation_id"]
        require("full_completion_and_quiet_tail", b["complete"] and b["stable_tail_seconds"] >= 4)
        require(
            "internal_only_application_networks",
            all(
                raw["app_network_isolation"][s] == {"internal_only": True, "published_ports": 0}
                for s in ["control", "gateway"]
            ),
        )
        require("clean_producer", raw["source"]["checkout_dirty"] is False)
        if manifest:
            require(
                "original_frozen_batch_and_dataset",
                raw.get("formal_batch") is True
                and raw.get("batch_id") == manifest["batch_id"]
                and raw.get("dataset_sha256") == manifest["dataset"]["sha256"],
            )
            require("frozen_source", raw["source"]["revision"] == manifest["producer_revision"])
            require(
                "frozen_runtime_files",
                all(
                    raw["source"]["file_sha256"].get(p) == digest
                    for p, digest in manifest["runtime_file_sha256"].items()
                ),
            )
            require(
                "frozen_dataset",
                sha(Path(manifest["dataset"]["artifact"]).read_bytes())
                == manifest["dataset"]["sha256"],
            )
        workers = e["worker_tasks"]
        require("one_original_worker_task", len(workers) == 1)
        w = workers[0]
        require(
            "worker_completed_once",
            w["status"] == "completed"
            and w["attempt"] == 1
            and w["conversation_round"] == 1
            and not w["root_task_id"]
            and not w["parent_task_id"],
        )
        require("fixed_project_snapshot", w["base_commit"] == dataset["initial_git_commit"])
        require("original_logical_operation", w["logical_markers"] == [logical])
        validation = w["result"]["validation"]
        require(
            "independent_test_succeeded",
            validation["exit_code"] == 0
            and validation["command"] == dataset["validation_command"]
            and w["result"]["validation_status"] == "passed",
        )
        require("actual_workspace_files", w["actual_files_sha256"] == dataset["final_files_sha256"])
        require(
            "only_allowed_changes",
            sorted(w["actual_changed_paths"]) == sorted(dataset["allowed_changed_paths"]),
        )
        require(
            "real_answer_diff",
            "-    return a - b" in w["actual_diff"]
            and "+    return a + b" in w["actual_diff"]
            and "diff --git a/notes.txt b/notes.txt" in w["result"]["diff"],
        )
        require(
            "actual_test_unchanged",
            w["actual_test_sha256"] == dataset["final_files_sha256"]["tests/test_answer.py"],
        )
        native = e["native_events"]
        starts = [v for v in native if v["kind"] == "native_turn_started"]
        ends = [v for v in native if v["kind"] == "native_turn_finished"]
        effects = [v for v in native if v["kind"] == "effect"]
        tested = [v for v in native if v["kind"] == "validation_finished"]
        require("one_actual_mutation_effect", len(effects) == 1)
        require("one_actual_native_turn", len(starts) == len(ends) == 1)
        require(
            "same_root_turn_workspace",
            all(
                v.get("root") == w["session_id"]
                and v.get("workspace") == w["workspace"]
                and (v.get("turn", w["turn_id"]) == w["turn_id"])
                and v["logical_operation"] == logical
                for v in starts + ends + effects + tested
            ),
        )
        require(
            "native_order_and_clock",
            starts[0]["ns"] <= effects[0]["ns"] <= ends[0]["ns"]
            and not ends[0]["cancelled"]
            and len({v["clock_domain"] for v in native}) == 1,
        )
        require(
            "actual_validation_exit",
            len(tested) == 1
            and tested[0]["exit_code"] == 0
            and tested[0]["command"] == validation["command"]
            and tested[0]["stdout_sha256"] == sha(validation["stdout"].encode())
            and tested[0]["stderr_sha256"] == sha(validation["stderr"].encode())
            and tested[0]["ns"] >= ends[0]["ns"],
        )
        rpc = e["native_rpc"]
        opened = [v for v in rpc if v.get("method") == "thread/start"]
        turns = [v for v in rpc if v.get("method") == "turn/start"]
        commands = [v for v in rpc if v.get("method") == "command/exec"]
        require(
            "actual_inbound_rpc_identity",
            len(opened) == len(turns) == len(commands) == 1
            and not any(v.get("method") == "thread/resume" for v in rpc)
            and opened[0]["cwd"] == turns[0]["cwd"] == commands[0]["cwd"] == w["workspace"]
            and turns[0]["threadId"] == w["session_id"]
            and turns[0]["logical_markers"] == [logical]
            and turns[0]["input_text_sha256"] == w["prompt_sha256"]
            and commands[0]["command"] == validation["command"],
        )
        tasks, public = e["mcp_tasks"], b["public_tracking"]
        require(
            "same_original_public_tracking",
            len(tasks) == len(public["items"]) == 1
            and tasks[0]["id"] == public["items"][0]["task_id"]
            and tasks[0]["user_id"] == owner
            and tasks[0]["thread_id"] == public["thread_id"] == raw["tracking_thread"]
            and tasks[0]["remote_task_id"].split(":")[-1] == w["task_id"]
            and tasks[0]["status"] == public["items"][0]["status"] == "completed"
            and tasks[0]["notification_status"]
            == public["items"][0]["notification_status"]
            == "delivered"
            and tasks[0]["notified_version"] >= tasks[0]["event_version"],
        )
        records = e["go_records"]
        ops = [v for v in records if v["kind"] == "operation"]
        native_ops = [v for v in ops if v["data"].get("kind") not in {"router", "assessor"}]
        require(
            "all_original_go_records_settled",
            bool(ops)
            and all(v["state"] == "settled" and v["owner"] == owner for v in ops)
            and all(v["state"] == "settled" for v in b["router_view"]["items"])
            and len(native_ops) == (0 if mode == "A" else 1),
        )
        require("work_verified", mode == "A" or b["work"]["data"].get("verified") is True)
        require(
            "runs_success_and_owned",
            bool(e["runs"])
            and all(v["user_id"] == owner and v["status"] == "success" for v in e["runs"]),
        )
        calls = [v for v in e["model_events"] if v["kind"] == "model_started"]
        finished = [v for v in e["model_events"] if v["kind"] == "model_finished"]
        require(
            "model_calls_complete_and_bounded",
            len(calls) == len(finished)
            and not any(v["kind"] == "model_rejected" for v in e["model_events"])
            and all(0 < v["input_bytes"] <= 12000 for v in calls)
            and sum(v["role"] == "assessor" for v in calls) <= 4
            and sum(v["role"] != "assessor" for v in calls) <= 20,
        )
        run_map = {v["run_id"]: v for v in e["runs"]}
        require(
            "actual_model_run_binding",
            all(
                v["run_id"] in run_map
                and run_map[v["run_id"]]["thread_id"] == v["thread_id"]
                and run_map[v["run_id"]]["user_id"] == owner
                and (
                    v["role"] != "notification"
                    or v["notification_admission_sha256"]
                    == run_map[v["run_id"]]["notification_admission_sha256"]
                )
                for v in calls
            ),
        )
        foreground = next(
            v for v in b["router_view"]["items"] if v["id"] == raw["foreground_inbox"]
        )
        require(
            "actual_original_foreground_reply",
            "EVAL_VISIBLE " + logical in foreground["data"].get("reply", ""),
        )
        service = raw["service_evidence"]
        timing = next(v for v in service["items"] if v["inbox"] == raw["foreground_inbox"])
        if timing.get("first_visible_ns") is not None:
            require(
                "reply_timing_same_domain",
                timing["admitted_ns"] <= timing["first_visible_ns"] == timing["complete_ns"]
                and service["clock_domain"] == starts[0]["clock_domain"],
            )
            metrics["service_admission_to_reply_flush_ms"] = (
                timing["first_visible_ns"] - timing["admitted_ns"]
            ) / 1e6
            metrics["reply_flush_before_validation"] = timing["first_visible_ns"] < tested[0]["ns"]
            forecalls = [v for v in calls if v.get("inbox") == raw["foreground_inbox"]]
            metrics["foreground_queue_ms"] = (
                ((min(v["ns"] for v in forecalls) - timing["admitted_ns"]) / 1e6)
                if forecalls
                else None
            )
        metrics["client_send_to_complete_read_ms"] = (
            raw["foreground_complete_read_runner_ns"] - raw["foreground_sent_runner_ns"]
        ) / 1e6
        metrics["native_validation_ms"] = (tested[0]["ns"] - starts[0]["ns"]) / 1e6
        rows = raw["scheduled_deliveries"]
        require(
            "all_planned_sends_retained",
            len(rows) == (9 if raw["scenario"] == "S1" else 2)
            and all(
                v["attempt_status"] == "responded" and v["sent_runner_ns"] and not v["error_kind"]
                for v in rows
            ),
        )
        if raw["scenario"] == "S1":
            judge_s1(raw, e, calls, require)
        else:
            judge_s2(raw, tasks, ops, require)
        state = "complete" if all(checks.values()) else "failed"
        return {
            "status": state,
            "checks": checks,
            "metrics": metrics,
            "reasons": [k for k, v in checks.items() if not v],
        }
    except (KeyError, IndexError, TypeError, StopIteration, ValueError, AttributeError) as error:
        return {
            "status": "failed" if any(not v for v in checks.values()) else "outcome_unknown",
            "checks": checks,
            "metrics": metrics,
            "reasons": [k for k, v in checks.items() if not v] + ["missing_or_invalid_evidence"],
            "evidence_error_kind": type(error).__name__,
        }


def judge_s1(raw, evidence, calls, require):
    rows, owner = raw["scheduled_deliveries"], raw["owner_id"]
    bound = [v for v in rows if v["kind"] == "bound"]
    unbound = next(v for v in rows if v["kind"] == "unbound")
    outside = next(v for v in rows if v["kind"] == "wrong_owner")
    ids = {v["receipt"]["event"]["id"] for v in bound}
    unbound_id = unbound["receipt"]["event"]["id"]
    events = [v for v in evidence["go_records"] if v["kind"] == "event"]
    require(
        "seven_original_owned_events",
        len(events) == 7 and len(ids) == 6 and all(v["owner"] == owner for v in events),
    )
    require(
        "bound_context_same_original_work",
        len([v for v in events if v["id"] in ids]) == 6
        and all(
            v["parent"] == raw["work_id"] and v["state"] == "context"
            for v in events
            if v["id"] in ids
        ),
    )
    require(
        "real_outside_owner_forbidden",
        raw["outside_owner"]["authenticated"]
        and raw["outside_owner"]["original_work_read_status"] == 403
        and outside["response_status"] == 403
        and outside["actor_user_id"] == raw["outside_owner"]["user_id"] != owner
        and outside["expected_user_id_matches_authenticated_user"],
    )
    require(
        "unbound_not_attached",
        any(
            v["id"] == unbound_id and not v["parent"] and v["state"] not in {"context", "attached"}
            for v in events
        ),
    )
    read = {r["id"] for c in calls for r in c.get("event_refs", [])}
    require("unbound_actual_router_read", unbound_id in read)
    require("bound_mode_factor", not (ids & read) if raw["mode"] == "C" else ids <= read)
    require(
        "exact_original_event_bodies",
        all(
            row["input"]["text"] in call.get("event_context_text", "")
            for call in calls
            for row in bound + [unbound]
            if row["receipt"]["event"]["id"] in {v["id"] for v in call.get("event_refs", [])}
        ),
    )


def judge_s2(raw, tasks, ops, require):
    events = raw["fault_events"]
    durable = [v for v in events if v["kind"] == "durable_barrier"]
    drops = [v for v in events if v["kind"] == "ack_dropped"]
    require("actual_durable_barrier_and_drop_once", len(durable) == len(drops) == 1)
    require(
        "no_failed_injection",
        not any(
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
    )
    proof, drop = durable[0]["proof"], drops[0]
    require(
        "zero_bytes_real_drop_after_durable",
        drop["response_bytes_sent_to_go"] == 0
        and durable[0]["clock_domain"] == drop["clock_domain"]
        and durable[0]["ns"] <= drop["ns"],
    )
    require(
        "proof_collected_after_public_recovery",
        raw["fault_evidence_collected_after_recovery_driver"] is True,
    )
    original = next(v for v in ops if v["id"] == proof["original_go_operation"])
    require(
        "same_original_coordinator_recovered",
        original["parent"] == raw["start_inbox"]
        and original["owner"] == proof["owner_id"] == raw["owner_id"]
        and original["data"]["run_id"] == proof["original_run_id"]
        and proof["coordinator_thread"] == raw["coordinator_thread"]
        and proof["original_go_state"] == "dispatching"
        and proof["chat_turn_confirmed"]
        and proof["chat_pending"] is None
        and proof["chat_head"] == proof["tracking_id"] == tasks[0]["id"]
        and proof["remote_handle_sha256"] == sha(tasks[0]["remote_task_id"].encode()),
    )
    require(
        "normal_original_query_after_drop",
        any(
            v["kind"] == "original_query"
            and v["ns"] > drop["ns"]
            and v["clock_domain"] == drop["clock_domain"]
            and v["original_go_operation"] == original["id"]
            and v["upstream_status"] == 200
            and v["known"]
            and v["run_id"] == proof["original_run_id"]
            for v in events
        ),
    )
    duplicate = next(v for v in raw["scheduled_deliveries"] if v["kind"] == "duplicate_start")
    require(
        "duplicate_input_same_identity",
        duplicate["receipt"]["id"] == raw["start_inbox"]
        and duplicate["input"]
        == {
            "operation_id": "start-" + raw["logical_operation_id"],
            "text": "EVAL_START " + raw["logical_operation_id"],
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.sample.read_text())
    result = judge(
        raw,
        json.loads(args.dataset.read_text()),
        json.loads(args.manifest.read_text()) if args.manifest else None,
    )
    result["sample_sha256"] = sha(args.sample.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print(json.dumps({"status": result["status"], "reasons": result["reasons"]}))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
