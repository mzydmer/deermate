import json

import httpx
import pytest

from scripts import verify_conversation as conversation
from scripts import verify_secretary as live


def test_followup_uses_exact_public_task_and_message():
    value = {
        "parent_tracking_id": "mcp-task-existing",
        "message": "Recall the previous marker.",
        "key": "stable",
    }
    body = conversation.followup_body(value, "configured-model")
    prompt = body["input"]["messages"][0]["content"]
    assert json.dumps({"task": value["parent_tracking_id"], "message": value["message"]}) in prompt
    assert body["context"]["subagent_enabled"] is False
    assert "worker" not in body["context"] and "user_id" not in body["context"]


def test_lost_followup_response_persists_whole_ledger_and_never_replays(tmp_path):
    path = tmp_path / "conversation.json"
    value = {
        "key": "stable",
        "parent_tracking_id": "mcp-task-existing",
        "message": "next",
        "run_attempted": False,
    }
    state = {"marker": "private-test-marker", "rounds": [value], "thread_id": "chat"}
    live.save_private(path, state)
    posts = []

    def respond(request):
        if request.method == "POST":
            saved = live.private_json(path)
            assert saved["rounds"][0]["run_attempted"] and saved["marker"] == state["marker"]
            posts.append(request.url.path)
            raise httpx.ReadTimeout("lost response")
        return httpx.Response(
            200,
            json=[
                {
                    "run_id": "existing-run",
                    "metadata": {"deermate_conversation_acceptance": "stable"},
                }
            ],
        )

    with httpx.Client(
        base_url="https://example.invalid", transport=httpx.MockTransport(respond)
    ) as client:
        with pytest.raises(httpx.ReadTimeout):
            conversation.ensure_round(client, path, state, 0, "model", "/api/threads/chat")
        saved = live.private_json(path)
        assert (
            conversation.ensure_round(client, path, saved, 0, "model", "/api/threads/chat")
            == "existing-run"
        )
    assert len(posts) == 1


def test_uncertain_followup_refuses_a_replacement_run(tmp_path):
    state = {"rounds": [{"key": "stable", "run_attempted": True}]}
    with httpx.Client(
        base_url="https://example.invalid",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    ) as client:
        with pytest.raises(live.AcceptanceError, match="no replay"):
            conversation.ensure_round(
                client, tmp_path / "state.json", state, 0, "model", "/api/threads/chat"
            )
