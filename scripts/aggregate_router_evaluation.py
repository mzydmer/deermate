#!/usr/bin/env python3
"""Rejudge every planned row; retain failures and censoring in fixed denominators."""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

if __package__:
    from .judge_router_evaluation import judge, sha
else:
    from judge_router_evaluation import judge, sha

LATENCIES = [
    "service_admission_to_reply_flush_ms",
    "client_send_to_complete_read_ms",
    "foreground_queue_ms",
    "native_validation_ms",
]


def distribution(values, planned):
    observed = sorted(v for v in values if v is not None and math.isfinite(v))
    count = len(observed)
    return {
        "planned_n": planned,
        "observed_n": count,
        "censored_n": planned - count,
        "values": observed,
        "p50": observed[math.ceil(0.5 * count) - 1] if count else None,
        "p95": observed[math.ceil(0.95 * count) - 1] if count else None,
        "max": max(observed) if count else None,
        "algorithm": "nearest-rank ceil(q*n)",
    }


def rate(affected, observed, planned):
    return {
        "affected_n": affected,
        "observed_n": observed,
        "planned_n": planned,
        "unobserved_n": planned - observed,
        "observed_rate": affected / observed if observed else None,
        "planned_rate": affected / planned if planned else None,
    }


def aggregate(manifest, directory, dataset):
    rows = []
    for item in manifest["planned"]:
        path = directory / item["sample_path"]
        if path.exists():
            raw_hash = sha(path.read_bytes())
            try:
                raw = json.loads(path.read_text())
                if not isinstance(raw, dict):
                    raise ValueError("A sample must be an object")
                verdict = judge(raw, dataset, manifest)
                expected = {
                    "scenario": item["scenario"],
                    "mode": item["mode"],
                    "seed": item["seed"],
                    "logical_operation_id": item["scenario"].lower() + "-" + str(item["seed"]),
                }
                if any(raw.get(key) != value for key, value in expected.items()):
                    verdict = {
                        "status": "failed",
                        "metrics": {},
                        "reasons": ["raw_identity_differs_from_planned_row"],
                        "unassigned_observed_metrics": verdict["metrics"],
                    }
            except (ValueError, TypeError, UnicodeError, OSError) as error:
                verdict = {
                    "status": "outcome_unknown",
                    "metrics": {},
                    "reasons": ["invalid_raw_evidence"],
                    "evidence_error_kind": type(error).__name__,
                }
        else:
            verdict = {
                "status": "not_started",
                "metrics": {},
                "reasons": ["planned_sample_missing"],
            }
            raw_hash = None
        rows.append({**item, "verdict": verdict, "sample_sha256": raw_hash})
    groups = []
    for scenario in ["S1", "S2"]:
        for mode in "ABC":
            group = [v for v in rows if v["scenario"] == scenario and v["mode"] == mode]
            metrics = [v["verdict"]["metrics"] for v in group]
            complete = sum(v["verdict"]["status"] == "complete" for v in group)
            groups.append(
                {
                    "scenario": scenario,
                    "mode": mode,
                    "planned_n": len(group),
                    "complete_n": complete,
                    "verified_completion_rate": complete / len(group),
                    "statuses": dict(Counter(v["verdict"]["status"] for v in group)),
                    "latencies": {
                        key: distribution([v.get(key) for v in metrics], len(group))
                        for key in LATENCIES
                    },
                    "overlap_n": sum(
                        v.get("reply_flush_before_validation") is True for v in metrics
                    ),
                    "overlap_denominator": len(group),
                    "extra_effects": sum(
                        max(0, v["effects"] - 1) for v in metrics if "effects" in v
                    ),
                    "extra_roots": sum(max(0, v["roots"] - 1) for v in metrics if "roots" in v),
                    "effect_observed_n": sum("effects" in v for v in metrics),
                    "call_observed_n": sum("model_calls" in v for v in metrics),
                    "model_calls_observed_total": sum(v.get("model_calls", 0) for v in metrics),
                    "role_call_totals": dict(
                        sum((Counter(v.get("roles_calls", {})) for v in metrics), Counter())
                    ),
                    "role_input_bytes_totals": dict(
                        sum((Counter(v.get("roles_input_bytes", {})) for v in metrics), Counter())
                    ),
                    "recovered_original_n": sum(v["verdict"]["status"] == "complete" for v in group)
                    if scenario == "S2"
                    else None,
                    "duplicate_execution_rate": rate(
                        sum(v.get("roots", 0) > 1 for v in metrics),
                        sum("roots" in v for v in metrics),
                        len(group),
                    ),
                    "duplicate_effect_rate": rate(
                        sum(v.get("effects", 0) > 1 for v in metrics),
                        sum("effects" in v for v in metrics),
                        len(group),
                    ),
                    "original_recovery_rate": rate(
                        complete,
                        sum(v.get("recovery_observed") is True for v in metrics),
                        len(group),
                    )
                    if scenario == "S2"
                    else None,
                }
            )
    paired = []
    for scenario in ["S1", "S2"]:
        seeds = sorted({v["seed"] for v in rows if v["scenario"] == scenario})
        for left, right in [("A", "B"), ("B", "C")]:
            for key in LATENCIES[:2]:
                pairs = []
                for seed in seeds:
                    a = next(
                        v
                        for v in rows
                        if (v["scenario"], v["mode"], v["seed"]) == (scenario, left, seed)
                    )["verdict"]["metrics"].get(key)
                    b = next(
                        v
                        for v in rows
                        if (v["scenario"], v["mode"], v["seed"]) == (scenario, right, seed)
                    )["verdict"]["metrics"].get(key)
                    pairs.append(
                        {
                            "seed": seed,
                            "difference": b - a if a is not None and b is not None else None,
                        }
                    )
                paired.append(
                    {
                        "scenario": scenario,
                        "contrast": right + "-" + left,
                        "metric": key,
                        "pairs": pairs,
                        "summary": distribution([v["difference"] for v in pairs], len(seeds)),
                    }
                )
    return {
        "schema_version": 1,
        "producer_revision": manifest["producer_revision"],
        "dataset_sha256": manifest["dataset"]["sha256"],
        "kind": manifest["kind"],
        "planned_n": len(rows),
        "groups": groups,
        "paired": paired,
        "samples": rows,
        "limitations": [
            "Offline fixed scripted Provider and fake Native protocol only.",
            "Small observed sample, no population significance or performance generalization.",
            "Missing timings are censored, never zero; queries do not count as mutations.",
            "No real model quality, billing, human attention or cloud capacity claims.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    dataset = json.loads(Path(manifest["dataset"]["artifact"]).read_text())
    result = aggregate(manifest, args.directory, dataset)
    with args.output.open("x") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print(
        json.dumps(
            {
                "planned_n": result["planned_n"],
                "groups": [
                    {k: g[k] for k in ["scenario", "mode", "planned_n", "complete_n"]}
                    for g in result["groups"]
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
