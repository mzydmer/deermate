"""Independent verdict and fixed-denominator aggregation counterexamples."""

from scripts.aggregate_router_evaluation import aggregate, distribution
from scripts.judge_router_evaluation import judge


def test_runner_success_without_evidence_is_never_accepted():
    verdict = judge(
        {"passed": True, "s1_contract": {"passed": True}, "s2_contract": {"passed": True}}, {}
    )
    assert verdict["status"] == "outcome_unknown"
    assert "missing_or_invalid_evidence" in verdict["reasons"]


def test_nearest_rank_keeps_missing_observations_out_of_quantiles():
    result = distribution([3, None, 9, 2, None, 5], 6)
    assert (result["planned_n"], result["observed_n"], result["censored_n"]) == (6, 4, 2)
    assert (result["p50"], result["p95"], result["max"]) == (3, 9, 9)
    assert distribution([None] * 6, 6)["p50"] is None


def test_all_planned_missing_rows_remain_in_every_denominator(tmp_path):
    planned = [
        {
            "scenario": scene,
            "mode": mode,
            "seed": seed,
            "sample_path": f"{scene}-{seed}-{mode}/sample.json",
        }
        for scene in ["S1", "S2"]
        for seed in range(1101, 1107)
        for mode in "ABC"
    ]
    result = aggregate(
        {
            "producer_revision": "frozen",
            "kind": "main",
            "dataset": {"sha256": "fixture"},
            "planned": planned,
        },
        tmp_path,
        {},
    )
    assert result["planned_n"] == 36
    assert all(g["planned_n"] == 6 and g["complete_n"] == 0 for g in result["groups"])
    assert all(g["statuses"] == {"not_started": 6} for g in result["groups"])
    assert all(
        p["summary"]["observed_n"] == 0 and p["summary"]["censored_n"] == 6
        for p in result["paired"]
    )


def test_duplicate_observation_survives_later_missing_evidence():
    verdict = judge(
        {
            "barrier": {
                "evidence": {
                    "native_events": [
                        {"kind": "native_turn_started", "root": "one"},
                        {"kind": "effect"},
                        {"kind": "effect"},
                    ],
                    "model_events": [
                        {"kind": "model_started", "role": "router", "input_bytes": 23}
                    ],
                }
            }
        },
        {},
    )
    assert verdict["status"] != "complete"
    assert verdict["metrics"]["effects"] == 2
    assert verdict["metrics"]["roots"] == 1
    assert verdict["metrics"]["model_calls"] == 1
    assert judge({}, {})["metrics"] == {}


def test_copied_success_file_cannot_satisfy_other_planned_rows(monkeypatch, tmp_path):
    import json

    from scripts import aggregate_router_evaluation as module

    planned = [
        {
            "scenario": scene,
            "mode": mode,
            "seed": seed,
            "sample_path": f"{scene}-{seed}-{mode}.json",
        }
        for scene in ["S1", "S2"]
        for seed in range(1101, 1107)
        for mode in "ABC"
    ]
    raw = {"scenario": "S1", "mode": "A", "seed": 1101, "logical_operation_id": "s1-1101"}
    for item in planned:
        (tmp_path / item["sample_path"]).write_text(json.dumps(raw))
    monkeypatch.setattr(module, "judge", lambda *_: {"status": "complete", "metrics": {}})
    result = module.aggregate(
        {
            "producer_revision": "frozen",
            "kind": "main",
            "dataset": {"sha256": "fixture"},
            "planned": planned,
        },
        tmp_path,
        {},
    )
    assert sum(v["complete_n"] for v in result["groups"]) == 1
    assert sum(v["verdict"]["status"] == "failed" for v in result["samples"]) == 35


def test_invalid_json_retains_unknown_row_and_remaining_denominators(tmp_path):
    planned = [
        {"scenario": scene, "mode": mode, "seed": 1101, "sample_path": f"{scene}-{mode}.json"}
        for scene in ["S1", "S2"]
        for mode in "ABC"
    ]
    (tmp_path / "S1-A.json").write_text("{broken")
    result = aggregate(
        {
            "producer_revision": "frozen",
            "kind": "repeat",
            "dataset": {"sha256": "fixture"},
            "planned": planned,
        },
        tmp_path,
        {},
    )
    assert result["planned_n"] == 6
    assert result["samples"][0]["verdict"]["status"] == "outcome_unknown"
    assert all(v["planned_n"] == 1 for v in result["groups"])
    assert all(v["duplicate_effect_rate"]["observed_n"] == 0 for v in result["groups"])


def test_frozen_plan_has_all_six_paired_orders_and_separate_repeat():
    import json
    from pathlib import Path

    from scripts.run_router_evaluation import plan

    config = json.loads(Path("docs/research/router-offline-config-v1.json").read_text())
    main, repeat = plan("main", config), plan("repeat", config)
    assert len(main) == 36 and len(repeat) == 6
    assert len({(r["scenario"], r["seed"], r["mode"]) for r in main}) == 36
    assert [r["mode"] for r in main[:18]] == list("ABCB CACABACBCBABAC".replace(" ", ""))
    assert all(r["seed"] == 1101 for r in repeat)


def test_frozen_batch_and_dataset_binding_are_independently_required(tmp_path):
    import hashlib
    from copy import deepcopy

    dataset = tmp_path / "dataset.json"
    dataset.write_text("{}")
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    raw = {
        "barrier": {"complete": True, "stable_tail_seconds": 4, "evidence": {}},
        "owner_id": "owner",
        "mode": "A",
        "logical_operation_id": "s1-1101",
        "app_network_isolation": {
            s: {"internal_only": True, "published_ports": 0} for s in ["control", "gateway"]
        },
        "source": {"revision": "frozen", "checkout_dirty": False, "file_sha256": {}},
        "formal_batch": True,
        "batch_id": "original-main",
        "dataset_sha256": digest,
    }
    manifest = {
        "producer_revision": "frozen",
        "runtime_file_sha256": {},
        "batch_id": "original-main",
        "dataset": {"artifact": str(dataset), "sha256": digest},
    }
    key = "original_frozen_batch_and_dataset"
    assert judge(raw, {}, manifest)["checks"][key]
    for field, wrong in [
        ("formal_batch", False),
        ("batch_id", "repeat"),
        ("dataset_sha256", "other-dataset"),
    ]:
        changed = deepcopy(raw)
        changed[field] = wrong
        assert not judge(changed, {}, manifest)["checks"][key]
