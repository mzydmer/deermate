"""Opt-in real-provider memory acceptance against an isolated loopback instance.

Uses synthetic statements and the instance's configured model. Journals each run
before submission; an unknown acknowledgement stops instead of replaying it.
Never point this at an account containing personal data or an active Worker.
"""

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def save(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def verify(args):
    assert urlsplit(args.url).hostname in {"localhost", "127.0.0.1"}
    owner = json.loads(args.account_file.read_text())
    assert owner.get("synthetic_owner") is True and owner["origin"] == args.url
    args.work_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    journal = args.work_dir / "state.json"
    state = json.loads(journal.read_text()) if journal.exists() else {"steps": {}, "checks": []}
    assert state.get("origin", args.url) == args.url
    state["origin"] = args.url
    client = httpx.Client(base_url=args.url, timeout=45, trust_env=False)
    response = client.post(
        "/api/v1/auth/login/local", data={"username": owner["email"], "password": owner["password"]}
    )
    assert response.status_code == 200, "Synthetic account login failed"
    user = client.get("/api/v1/auth/me").json()["id"]
    client.headers.update(
        {"X-CSRF-Token": client.cookies["csrf_token"], "X-Expected-User-Id": user}
    )

    def request(method, path, body=None):
        result = client.request(method, path, json=body)
        assert result.is_success, f"{method} {path}: HTTP {result.status_code}"
        return result.json()

    def check(name, value):
        assert value, name
        if name not in state["checks"]:
            state["checks"].append(name)
            save(journal, state)
        print("PASS " + name, flush=True)

    def wait(read, predicate, seconds=100):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = read()
            if predicate(value):
                return value
            time.sleep(0.4)
        raise RuntimeError("Acceptance deadline reached; original operation was not replayed")

    def facts():
        return request("GET", "/api/me/memories")["items"]

    def chat(name, text, *, thread=None):
        step = state["steps"].setdefault(
            name,
            {"thread": thread or "wsv2-" + uuid.uuid4().hex, "message": uuid.uuid4().hex},
        )
        save(journal, state)
        tid = step["thread"]
        if not step.get("thread_created"):
            existing = client.get("/api/threads/" + tid)
            if existing.status_code == 404:
                request("POST", "/api/threads", {"thread_id": tid})
            else:
                assert existing.status_code == 200
            step["thread_created"] = True
            save(journal, state)
        if "run" not in step:
            assert not step.get("attempted"), (
                "Unknown run acknowledgement; inspect instead of replay"
            )
            step["attempted"] = True
            save(journal, state)
            result = request(
                "POST",
                f"/api/threads/{tid}/runs",
                {
                    "input": {
                        "messages": [{"id": step["message"], "type": "human", "content": text}]
                    },
                    "context": {
                        "model_name": model,
                        "thinking_enabled": False,
                        "subagent_enabled": False,
                    },
                    "config": {"recursion_limit": 128},
                },
            )
            step["run"] = result["run_id"]
            save(journal, state)
        run = wait(
            lambda: request("GET", f"/api/threads/{tid}/runs/{step['run']}"),
            lambda v: v["status"] not in {"pending", "running"},
        )
        assert run["status"] in {"success", "completed"}, "The original model run failed"
        snapshot = request("GET", f"/api/threads/{tid}/state")
        answers = []
        for message in snapshot.get("values", {}).get("messages", []):
            data = message.get("data", message)
            if data.get("type", data.get("role")) in {"ai", "assistant"} and isinstance(
                data.get("content"), str
            ):
                answers.append(data["content"])
        assert answers, "No actual provider answer"
        return tid, answers[-1]

    models = request("GET", "/api/models")["models"]
    model = args.model or models[0]["name"]
    check("configured_model_available", any(v["name"] == model for v in models))
    profile = request("GET", "/api/me/personal-profile")
    check(
        "versioned_defaults_enabled", profile["memory_enabled"] and profile["auto_capture_enabled"]
    )
    if args.resume_semantic:
        assert "final_router_prompt_real_answer_uses_memory" in state["checks"]
        chat(
            args.semantic_case,
            "我的答复习惯是简短直接，尽量不要写很长的解释。只需确认，不调用工具。",
        )
        semantic = wait(
            facts,
            lambda values: any(
                ("简短" in f["content"] or "直接" in f["content"])
                and "首页已收" not in f["content"]
                for f in values
            ),
        )
        check("bounded_real_provider_extraction_completed", bool(semantic))
        for _ in range(3):
            request("GET", "/api/me/workspace-snapshot")
        check(
            "home_snapshot_has_at_most_three_items",
            len(request("GET", "/api/me/workspace-snapshot")["items"]) <= 3,
        )
        save(
            args.receipt,
            {
                "passed": True,
                "checks": state["checks"],
                "ordinary_runs": sum("run" in value for value in state["steps"].values()),
                "model_kind": "real configured provider",
                "native_calls": 0,
                "scope": "Loopback synthetic account; no production data or Worker grants.",
            },
        )
        client.close()
        return
    first, _ = chat(
        "ordinary", "以后回答先写 已核对 这三个字，再给结论。只需简短确认，不调用工具。"
    )
    saved = wait(facts, lambda v: any("已核对" in f["content"] for f in v))
    fact = next(v for v in saved if "已核对" in v["content"])
    check("ordinary_expression_canonical_write", fact["scope"] == "personal")
    _, answer = chat("reuse", "我的回答开头偏好是什么？请按已经保存的偏好简短回答，不调用工具。")
    check("new_conversation_real_answer_uses_memory", answer.lstrip().startswith("已核对"))
    chat(
        "correction",
        "以后回答改为先写 简答 这两个字，再给结论。只需简短确认，不调用工具。",
        thread=first,
    )
    updated = wait(facts, lambda v: any("简答" in f["content"] for f in v))
    corrected = next(v for v in updated if "简答" in v["content"])
    check(
        "correction_preserves_fact_and_advances_revision",
        corrected["id"] == fact["id"] and corrected["revision"] > fact["revision"],
    )
    _, answer = chat("corrected-reuse", "按已保存的回答开头偏好，简短说一句你好，不调用工具。")
    check("corrected_preference_used_in_real_answer", answer.lstrip().startswith("简答"))
    source = request("GET", f"/api/me/memories/{corrected['id']}/source")
    check("source_and_context_usage_visible", source["kind"] == "chat" and bool(source["uses"]))

    if "temporary" not in state:
        state["temporary_operation"] = state.get("temporary_operation", uuid.uuid4().hex)
        save(journal, state)
        temporary = request(
            "POST", "/api/me/temporary-topics", {"operation_id": state["temporary_operation"]}
        )
        state["temporary"] = temporary["thread_id"]
        save(journal, state)
    temporary = state["temporary"]
    _, answer = chat(
        "temporary-read",
        "你保存的回答开头偏好是什么？如果没有信息，只回答没有记录。不要调用工具。",
        thread=temporary,
    )
    check(
        "temporary_topic_real_answer_excludes_memory",
        "简答" not in answer and "已核对" not in answer,
    )
    chat(
        "temporary-capture",
        "以后回答先写 临时验收 这四个字，再给结论。只需确认，不调用工具。",
        thread=temporary,
    )
    time.sleep(3)
    check(
        "whole_temporary_topic_never_captures", not any("临时验收" in v["content"] for v in facts())
    )
    profile = request("GET", "/api/me/personal-profile")
    request(
        "PATCH",
        "/api/me/personal-profile",
        {"auto_capture_enabled": False, "expected_revision": profile["revision"]},
    )
    chat("paused", "以后回答先写 不应保存 这四个字。只需确认，不调用工具。")
    time.sleep(3)
    check(
        "paused_capture_keeps_management_and_old_facts",
        not any("不应保存" in v["content"] for v in facts()),
    )
    profile = request("GET", "/api/me/personal-profile")
    request(
        "PATCH",
        "/api/me/personal-profile",
        {"auto_capture_enabled": True, "expected_revision": profile["revision"]},
    )
    corrected = next(v for v in facts() if v["id"] == fact["id"])
    deletion = request(
        "DELETE",
        f"/api/me/memories/{corrected['id']}",
        {"operation_id": "wsv2-forget", "expected_revision": corrected["revision"]},
    )
    wait(
        lambda: request("GET", "/api/me/memory-operations/" + deletion["id"]),
        lambda v: v["status"] == "completed",
    )
    check("forget_removes_canonical_fact", not any(v["id"] == fact["id"] for v in facts()))
    _, answer = chat(
        "forgotten-reuse",
        "你保存的回答开头偏好是什么？如果没有信息，只回答没有记录。不要调用工具。",
    )
    check("forgotten_fact_not_in_real_answer", "简答" not in answer and "已核对" not in answer)

    def inbox(name, text):
        step = state["steps"].setdefault(name, {"operation": uuid.uuid4().hex})
        save(journal, state)
        if "inbox" not in step:
            value = request(
                "POST", "/api/me/router/messages", {"operation_id": step["operation"], "text": text}
            )
            step["inbox"] = value["id"]
            save(journal, state)
        return wait(
            lambda: next(
                v for v in request("GET", "/api/me/router")["items"] if v["id"] == step["inbox"]
            ),
            lambda v: bool(v["data"].get("reply")) or v["state"] in {"failed", "rejected"},
        )

    inbox("inbox-pref", "以后回答先写 首页已收 这四个字，再给结论。只需简短确认。")
    current = wait(facts, lambda v: any("首页已收" in f["content"] for f in v))
    inbox_fact = next(v for v in current if "首页已收" in v["content"])
    check(
        "home_inbox_has_distinct_canonical_source",
        request("GET", f"/api/me/memories/{inbox_fact['id']}/source")["kind"] == "inbox",
    )
    reply = inbox("inbox-reuse", "我之前说的答复开头是什么？请按已保存的偏好简短回答。")
    check(
        "final_router_prompt_real_answer_uses_memory", "首页已收" in reply["data"].get("reply", "")
    )
    chat("semantic", "我的答复习惯是简短直接。只需确认，不调用工具。")
    semantic = wait(
        facts,
        lambda v: any(
            ("简短" in f["content"] or "直接" in f["content"]) and "首页已收" not in f["content"]
            for f in v
        ),
    )
    check("bounded_real_provider_extraction_completed", bool(semantic))
    for _ in range(3):
        request("GET", "/api/me/workspace-snapshot")
    check(
        "home_snapshot_has_at_most_three_items",
        len(request("GET", "/api/me/workspace-snapshot")["items"]) <= 3,
    )
    result = {
        "passed": True,
        "checks": state["checks"],
        "ordinary_runs": sum("run" in v for v in state["steps"].values()),
        "model_kind": "real configured provider",
        "native_calls": 0,
        "scope": "Isolated loopback account; synthetic statements; no production data or grants.",
    }
    save(args.receipt, result)
    print(json.dumps({"passed": True, "checks": len(state["checks"])}))
    client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--account-file", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--model")
    parser.add_argument("--resume-semantic", action="store_true")
    parser.add_argument("--semantic-case", default="semantic-stream")
    verify(parser.parse_args())


if __name__ == "__main__":
    main()
