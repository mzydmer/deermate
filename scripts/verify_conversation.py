#!/usr/bin/env python3
"""Two opt-in model-selected follow-ups to a previously verified demo task; no replay."""

import argparse
import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from deermate.bridge import BridgeError, read_token
from deermate.config import load_settings

if __package__:
    from . import verify_secretary as live
else:
    import verify_secretary as live


def followup_body(value, model):
    arguments = {"task": value["parent_tracking_id"], "message": value["message"]}
    return {
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Continue the authorized demo Codex conversation. Call continue_codex "
                        "exactly once with these exact arguments: "
                        + json.dumps(arguments)
                        + ". Do not answer it yourself, create another session, submit a new "
                        "task, or use another tool. If blocked, report it without retrying. "
                        "The runtime tracks the result and notification."
                    ),
                }
            ]
        },
        "context": {"model_name": model, "thinking_enabled": False, "subagent_enabled": False},
        "config": {"recursion_limit": 128},
        "metadata": {"deermate_conversation_acceptance": value["key"]},
    }


def ensure_round(client, path, state, index, model, thread):
    value = state["rounds"][index]
    if value["run_attempted"]:
        matches = [
            r
            for r in live.request(client, "GET", thread + "/runs")
            if r.get("metadata", {}).get("deermate_conversation_acceptance") == value["key"]
        ]
        if len(matches) != 1:
            raise live.AcceptanceError("Attempted follow-up cannot be reconciled; no replay.")
        return matches[0]["run_id"]
    value["run_attempted"] = True
    live.save_private(path, state)
    result = live.request(
        client,
        "POST",
        thread + "/runs",
        json=followup_body(value, model),
        headers={"Idempotency-Key": value["key"]},
    )
    return result["run_id"]


def calls(state):
    result = []
    for message in state.get("values", {}).get("messages", []):
        data = message.get("data", message)
        if data.get("type", data.get("role")) in {"ai", "assistant"}:
            result.extend(data.get("tool_calls", []))
    return result


def verify(args):
    url = live.origin(args.url)
    seed = live.private_json(args.parent_state / "intent.json")
    if seed.get("origin") != url or seed.get("mode") != "dispatch" or seed.get("project") != "demo":
        raise live.AcceptanceError("Use the saved verified demo dispatch on this origin.")
    settings = load_settings(args.worker_config)
    report = asyncio.run(live.worker_check(settings, args.worker_port))
    if (
        report["status"] != "reachable"
        or report["capabilities"].get("continuation") != "child-tasks-v1"
    ):
        raise live.AcceptanceError("Upgrade/check the enrolled Worker before model follow-ups.")
    route = asyncio.run(
        live.remote_route_check(
            args.ssh_controller_config, args.ssh_worker, url, report["capabilities"]["instance_id"]
        )
    )
    native_id = live.native_reference(settings, seed, report["capabilities"]["instance_id"])
    account = live.private_json(args.account_file)
    if set(account) != {"email", "password"}:
        raise live.AcceptanceError("Use the existing private owner account file.")
    thread = "/api/threads/" + seed["thread_id"]
    scope = {
        "origin": url,
        "thread_id": seed["thread_id"],
        "model": seed["model"],
        "native_id": native_id,
    }
    path = args.state_dir / "conversation.json"
    if path.exists():
        state = live.private_json(path)
        if any(state.get(k) != v for k, v in scope.items()):
            raise live.AcceptanceError("Saved conversation has another scope; no replay.")
    else:
        state = {**scope, "marker": "DEERMATE_QA_" + uuid.uuid4().hex[:16], "rounds": []}
        live.save_private(path, state)
    with (
        httpx.Client(
            base_url=url,
            trust_env=False,
            follow_redirects=False,
            timeout=30,
            headers={"Origin": url},
        ) as client,
        httpx.Client(
            base_url=f"http://127.0.0.1:{args.worker_port}",
            trust_env=False,
            timeout=15,
            headers={"Authorization": "Bearer " + read_token(settings.state_dir / "api.token")},
        ) as worker,
    ):
        response = client.post(
            "/api/v1/auth/login/local",
            data={"username": account["email"], "password": account["password"]},
        )
        if response.status_code != 200:
            raise live.AcceptanceError("Owner login failed; credentials withheld.")
        client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token", "")
        me = live.request(client, "GET", "/api/v1/auth/me")
        if me.get("system_role") != "admin" or me.get("id") != seed.get("owner_id"):
            raise live.AcceptanceError("Conversation belongs to another owner.")
        root = live.request(worker, "GET", "/tasks/" + native_id)
        if not root.get("session_id") or root["status"] != "completed":
            raise live.AcceptanceError("Original demo task is not confirmed complete.")
        root_rows = live.request(client, "GET", thread + "/mcp-tasks")
        roots = [
            r
            for r in root_rows
            if (
                live.request(client, "GET", thread + "/mcp-tasks/" + r["task_id"]).get("result")
                or {}
            ).get("conversation_round", 1)
            == 1
        ]
        if len(roots) != 1 or (not state["rounds"] and len(root_rows) != 1):
            raise live.AcceptanceError("Original chat is ambiguous; no new model run attempted.")
        parent_tracking, parent_native = roots[0]["task_id"], root
        results = []
        messages = [
            "Remember this marker for our next turn: "
            + state["marker"]
            + ". Explain why the earlier addition fix works. Do not edit files or run commands.",
            "What marker did I ask you to remember in our previous turn? Quote it exactly "
            "and explain how our addition fix handles negative numbers. "
            "Do not edit files or run commands.",
        ]
        for index, message in enumerate(messages):
            if len(state["rounds"]) == index:
                state["rounds"].append(
                    {
                        "key": uuid.uuid4().hex,
                        "message": message,
                        "parent_tracking_id": parent_tracking,
                        "run_attempted": False,
                    }
                )
                live.save_private(path, state)
            value = state["rounds"][index]
            if value["message"] != message or value["parent_tracking_id"] != parent_tracking:
                raise live.AcceptanceError("Follow-up identity changed; no replay.")
            run_id = ensure_round(client, path, state, index, seed["model"], thread)
            run = live.wait_read(
                lambda run_id=run_id: live.request(client, "GET", thread + "/runs/" + run_id),
                lambda r: r["status"] not in {"pending", "running"},
            )
            if run["status"] != "success":
                raise live.AcceptanceError(
                    "Follow-up model run failed; inspect admitted tasks, no replay."
                )
            matching_calls = [
                c
                for c in calls(live.request(client, "GET", thread + "/state"))
                if c.get("name") == "continue_codex"
                and c.get("args") == {"task": parent_tracking, "message": message}
            ]
            if len(matching_calls) != 1:
                raise live.AcceptanceError("Exact scoped continuation tool call was not confirmed.")

            def find_round(round_number=index + 2):
                found = []
                for item in live.request(client, "GET", thread + "/mcp-tasks"):
                    detail = live.request(client, "GET", thread + "/mcp-tasks/" + item["task_id"])
                    result = detail.get("result") or {}
                    if (
                        result.get("conversation_round") == round_number
                        and result.get("session_id") == root["session_id"]
                    ):
                        found.append(detail)
                if len(found) > 1:
                    raise live.AcceptanceError("Several rounds matched; no replay.")
                return found[0] if found else None

            task = live.wait_read(
                find_round,
                lambda t: (
                    t and t["status"] == "completed" and t["notification_status"] == "delivered"
                ),
                240,
            )
            children = [
                t
                for t in live.request(worker, "GET", "/tasks")["tasks"]
                if t.get("parent_task_id") == parent_native["task_id"]
            ]
            if len(children) != 1:
                raise live.AcceptanceError("Native child mapping was not unique.")
            child = children[0]
            if not (
                child["prompt"] == message
                and child["session_id"] == root["session_id"]
                and child["workspace"] == root["workspace"]
                and child["attempt"] == 1
                and child["result"]["validation"]["exit_code"] == 0
                and child["result"]["summary"][:2000] == task["result"]["summary"]
                and live.request(worker, "GET", "/tasks/" + parent_native["task_id"])
                == parent_native
            ):
                raise live.AcceptanceError("Native session/workspace/evidence did not match.")
            recalled = state["marker"] in child["result"]["summary"]
            if index == 1 and not recalled:
                raise live.AcceptanceError("Native follow-up did not recall the previous marker.")
            results.append(
                {
                    "round": index + 2,
                    "run_status": run["status"],
                    "llm_call_count": run["llm_call_count"],
                    "native_attempt": 1,
                    "independent_validation_exit_code": 0,
                    "notification_status": task["notification_status"],
                    "previous_evidence_preserved": True,
                    "exact_native_message_verified": True,
                    "previous_marker_recalled": recalled,
                }
            )
            parent_tracking, parent_native = task["task_id"], child
        if len(live.request(client, "GET", thread + "/mcp-tasks")) != 3:
            raise live.AcceptanceError("Expected exactly three tracked conversation rounds.")
    receipt = {
        "schema_version": 1,
        "checked_at": datetime.now(UTC).isoformat(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "normal_run_api": True,
        "submit_shim_used": False,
        "cloud_to_home_verified": True,
        "network_evidence": route,
        "total_conversation_rounds": 3,
        "new_native_tasks": 2,
        "one_native_session_and_workspace": True,
        "rounds": results,
        "passed": True,
    }
    live.save_private(args.receipt, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", required=True, help="uses real model/native quota"
    )
    parser.add_argument("--url", required=True)
    for name in (
        "account-file",
        "parent-state",
        "worker-config",
        "ssh-controller-config",
        "state-dir",
        "receipt",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--worker-port", type=int, default=18777)
    parser.add_argument("--ssh-worker", default="home")
    args = parser.parse_args()
    try:
        with live.state_lock(args.state_dir):
            result = verify(args)
        print(json.dumps(result, indent=2))
    except (
        live.AcceptanceError,
        BridgeError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        httpx.HTTPError,
    ) as error:
        raise SystemExit(
            "Conversation acceptance stopped; inspect private state. " + type(error).__name__
        ) from None


if __name__ == "__main__":
    main()
