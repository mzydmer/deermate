"""Offline protocol fixture. This is not a Codex implementation or a live model demo."""

import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

storage = Path(sys.argv[1])
storage.mkdir(parents=True, exist_ok=True)
write_lock = threading.Lock()
stops = {}
inputs = {}
workspace = None
session_id = None


def send(message):
    with write_lock:
        print(json.dumps(message), flush=True)


def finish(turn_id, prompt, path, sid):
    stop = stops[turn_id]
    if "approval" in prompt:
        inputs[999] = threading.Event()
        send(
            {
                "id": 999,
                "method": "item/commandExecution/requestApproval",
                "params": {"threadId": sid, "command": "attempted escalation"},
            }
        )
        while not inputs[999].wait(0.02):
            if stop.is_set():
                break
    if "question" in prompt:
        inputs[1000] = threading.Event()
        send(
            {
                "id": 1000,
                "method": "item/tool/requestUserInput",
                "params": {
                    "threadId": sid,
                    "questions": [{"id": "choice", "question": "Continue?"}],
                },
            }
        )
        while not inputs[1000].wait(0.02):
            if stop.is_set():
                break
    end = time.monotonic() + (15 if "slow" in prompt else 0.08)
    while time.monotonic() < end and not stop.is_set():
        time.sleep(0.01)
    if not stop.is_set():
        if "bad-fix" not in prompt:
            (path / "answer.py").write_text("def add(a, b):\n    return a + b\n")
        (path / "notes.txt").write_text("offline protocol fixture\n")
        send(
            {
                "method": "item/completed",
                "params": {
                    "threadId": sid,
                    "item": {
                        "type": "agentMessage",
                        "id": "message-1",
                        "text": "Fixture patch prepared.",
                    },
                },
            }
        )
    send(
        {
            "method": "turn/completed",
            "params": {
                "threadId": sid,
                "turn": {"id": turn_id, "status": "interrupted" if stop.is_set() else "completed"},
            },
        }
    )


for line in sys.stdin:
    message = json.loads(line)
    with (storage / "trace.jsonl").open("a") as trace:
        trace.write(json.dumps(message) + "\n")
    if "method" not in message:
        if message.get("id") in inputs:
            inputs[message["id"]].set()
        continue
    method, params = message["method"], message.get("params", {})
    result = {}
    match method:
        case "initialize":
            result = {"userAgent": "offline-fixture"}
        case "initialized":
            continue
        case "thread/start":
            assert params["sandbox"] in {"workspace-write", "read-only"}
            workspace = Path(params["cwd"])
            session_id = uuid.uuid4().hex
            (storage / session_id).write_text(str(workspace))
            result = {"thread": {"id": session_id, "status": {"type": "idle"}}}
        case "thread/resume":
            session_id = params["threadId"]
            workspace = Path((storage / session_id).read_text())
            result = {"thread": {"id": session_id, "status": {"type": "idle"}}}
        case "turn/start":
            turn_id = uuid.uuid4().hex
            stops[turn_id] = threading.Event()
            send({"id": message["id"], "result": {"turn": {"id": turn_id}}})
            threading.Thread(
                target=finish,
                daemon=True,
                args=(turn_id, params["input"][0]["text"], workspace, session_id),
            ).start()
            continue
        case "turn/interrupt":
            stops[params["turnId"]].set()
        case "command/exec":
            completed = subprocess.run(
                params["command"], cwd=params["cwd"], capture_output=True, text=True, timeout=10
            )
            result = {
                "exitCode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
    send({"id": message["id"], "result": result})
