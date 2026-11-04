"""State-only UI samples. Run inside the named offline fixture, never production."""

import json
import sqlite3
import sys
from pathlib import Path

import yaml

config = yaml.safe_load(Path("/etc/deermate/config.yaml").read_text())
assert [model["name"] for model in config["models"]] == ["continuous-fixture"]
assert Path("/etc/deermate/continuous_fixture_model.py").is_file()
owner = json.load(sys.stdin)["owner"]
db = sqlite3.connect("/app/backend/.deer-flow/data/deerflow.db")
assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
assert db.execute("SELECT id FROM users").fetchone()[0] == owner
assert (
    db.execute(
        "SELECT count(*) FROM deermate_agent_grants WHERE json_extract(data,'$.revoked')=0"
    ).fetchone()[0]
    == 0
)
assert (
    db.execute(
        "SELECT count(*) FROM mcp_tasks WHERE status IN ('submitted','running','input_required')"
    ).fetchone()[0]
    == 0
)
states = {
    "ready": "待执行",
    "queued": "等待接纳",
    "input_required": "等待输入",
    "uncertain": "回执未知",
    "cancel_requested": "停止待确认",
    "cancelled": "停止已确认",
    "verification_required": "尚待验证",
    "handoff": "范围变化",
}
for index, (stage, title) in enumerate(states.items()):
    data = {
        "title": "合成状态样本 · " + title,
        "goal": "UI 状态验收样本，不接入设备、不执行任务。",
        "stage": stage,
        "project": "ui-fixture",
        "grant_id": "unconfigured-ui-fixture",
        "executor": "codex",
        "thread_id": "ui-fixture-" + stage,
        "verified": False,
    }
    if stage in {"queued", "input_required", "uncertain", "cancel_requested"}:
        data["active_operation"] = "ui-state-only-" + stage
    db.execute(
        "INSERT OR IGNORE INTO deermate_work_records VALUES(?,?,?,?,?,?,?,?,?)",
        (
            "ui-state-" + stage,
            "work",
            owner,
            "",
            "active",
            1,
            100 + index,
            100 + index,
            json.dumps(data, ensure_ascii=False),
        ),
    )
db.commit()
print(json.dumps({"synthetic_state_cards": len(states), "native_submissions": 0}))
