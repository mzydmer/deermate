"""Read-only synthetic evidence collection; never exports auth/capability fields."""

import hashlib
import json
import re
import sqlite3
import subprocess
import time
from pathlib import Path

ROOT = Path("/app/backend/.deer-flow")
ALLOWED = {
    "kind",
    "origin",
    "thread_id",
    "inbox_id",
    "work_id",
    "project",
    "stage",
    "status",
    "run_id",
    "tracking_id",
    "native_session",
    "verified",
    "outcome",
    "active_operation",
    "head",
    "event_batch",
    "event_id",
    "event_revision",
    "rule_id",
    "rule_revision",
    "source_id",
    "source_generation",
    "thread_key",
    "title",
    "preview",
    "remote_id",
    "remote_revision",
    "reply",
    "has_update",
}


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def native_rpc():
    records = []
    for original in lines(ROOT / "continuous-native-fixture/native/trace.jsonl"):
        if not original.get("method"):
            continue
        params = original.get("params", {})
        row = {"id": original.get("id"), "method": original["method"]}
        row.update(
            {key: params[key] for key in ("cwd", "threadId", "turnId", "command") if key in params}
        )
        if original["method"] == "turn/start":
            text = "".join(v.get("text", "") for v in params.get("input", []))
            row["input_text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            row["logical_markers"] = re.findall(r"EVAL_OPERATION=([A-Za-z0-9_-]+)", text)
        records.append(row)
    return records


def collect():
    with sqlite3.connect((ROOT / "data/deerflow.db").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        records = []
        for row in db.execute(
            "SELECT owner,id,kind,state,parent,revision,data "
            "FROM deermate_work_records ORDER BY kind,id"
        ):
            item = dict(row)
            item["data"] = {
                key: value for key, value in json.loads(item["data"]).items() if key in ALLOWED
            }
            records.append(item)
        tasks = [
            dict(r)
            for r in db.execute(
                "SELECT id,user_id,thread_id,run_id,status,remote_task_id,notification_status,"
                "notification_run_id,event_version,notified_version FROM mcp_tasks ORDER BY id"
            )
        ]
        runs = []
        for row in db.execute(
            "SELECT run_id,thread_id,user_id,status,origin_kind,kwargs_json "
            "FROM runs ORDER BY run_id"
        ):
            item = dict(row)
            kwargs = json.loads(item.pop("kwargs_json") or "{}")
            if item["origin_kind"] == "mcp_notification":
                encoded = json.dumps(
                    (kwargs.get("input") or {}).get("messages", []),
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode()
                item["notification_admission_sha256"] = hashlib.sha256(encoded).hexdigest()
            runs.append(item)
        deliveries = []
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='continuous_fixture_deliveries'"
        ).fetchone():
            deliveries = [
                list(r)
                for r in db.execute(
                    "SELECT operation,deliveries FROM continuous_fixture_deliveries "
                    "ORDER BY operation"
                )
            ]
    worker = ROOT / "continuous-native-fixture/state/tasks.sqlite3"
    workers = []
    if worker.exists():
        with sqlite3.connect(worker.as_uri() + "?mode=ro", uri=True) as db:
            for row in db.execute("SELECT data FROM tasks ORDER BY id"):
                item = json.loads(row[0])
                prompt = item.pop("prompt", "")
                item.pop("policy", None)
                item["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
                item["logical_markers"] = re.findall(r"EVAL_OPERATION=([A-Za-z0-9_-]+)", prompt)
                if item.get("workspace"):
                    answer = Path(item["workspace"]) / "answer.py"
                    if answer.exists():
                        item["actual_answer_sha256"] = hashlib.sha256(
                            answer.read_bytes()
                        ).hexdigest()
                    workspace = Path(item["workspace"])

                    def git(*args, location=workspace):
                        return subprocess.check_output(["git", "-C", str(location), *args])

                    paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
                    names = sorted(set(v.decode() for v in paths.split(b"\0") if v))
                    item["actual_files_sha256"] = {
                        name: hashlib.sha256((workspace / name).read_bytes()).hexdigest()
                        if (workspace / name).is_file() and not (workspace / name).is_symlink()
                        else None
                        for name in names
                    }
                    changed = git("diff", "HEAD", "--name-only", "-z")
                    untracked = git("ls-files", "--others", "--exclude-standard", "-z")
                    item["actual_changed_paths"] = sorted(
                        set(v.decode() for v in (changed + untracked).split(b"\0") if v)
                    )
                    item["actual_diff"] = subprocess.check_output(
                        ["git", "-C", str(workspace), "diff", "HEAD"], text=True
                    )
                    test = workspace / "tests/test_answer.py"
                    if test.exists():
                        item["actual_test_sha256"] = hashlib.sha256(test.read_bytes()).hexdigest()
                workers.append(item)
    return {
        "clock_domain": "linux-monotonic:"
        + Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "clock_ns": time.monotonic_ns(),
        "go_records": records,
        "mcp_tasks": tasks,
        "runs": runs,
        "deliveries": deliveries,
        "worker_tasks": workers,
        "native_events": lines(ROOT / "continuous-native-fixture/native/evaluation-events.jsonl"),
        "native_rpc": native_rpc(),
        "model_events": lines(ROOT / "evaluation-model.jsonl"),
        "observation_presence": {
            "native_events": (
                ROOT / "continuous-native-fixture/native/evaluation-events.jsonl"
            ).exists(),
            "native_rpc": (ROOT / "continuous-native-fixture/native/trace.jsonl").exists(),
            "model_events": (ROOT / "evaluation-model.jsonl").exists(),
        },
    }
