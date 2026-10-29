"""Pinned LangChain/DeerFlow graph verification; offline, zero native/model calls."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace


async def verify():
    with tempfile.TemporaryDirectory(prefix="deermate-chat-graph-") as directory:
        root = Path(directory)
        os.environ["DEER_FLOW_HOME"] = str(root / "home")
        os.environ["DEER_FLOW_CONFIG_PATH"] = str(root / "config.yaml")
        contract = [
            {
                "name": "coding",
                "submit_tool": "submit_task",
                "status_tool": "get_task_status",
                "cancel_tool": "cancel_task",
            },
            {
                "name": "followup",
                "submit_tool": "continue_task",
                "status_tool": "get_continuation_status",
                "cancel_tool": "cancel_continuation_task",
            },
        ]
        (root / "config.yaml").write_text(
            json.dumps(
                {
                    "config_version": 62,
                    "models": [],
                    "tools": [],
                    "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
                    "extensions": {
                        "middlewares": ["deermate.session_middleware:CodingSessionMiddleware"],
                        "mcpServers": {
                            "deermate": {
                                "enabled": True,
                                "command": "unused",
                                "task_toolsets": contract,
                            }
                        },
                    },
                }
            )
        )
        from deerflow.agents.middlewares.configured_extensions import (
            load_configured_extension_middlewares,
        )
        from deerflow.config import get_app_config
        from deerflow.mcp.tasks.runtime import set_mcp_task_submitter
        from deerflow.tools.mcp_metadata import tag_mcp_tool
        from langchain.agents import create_agent
        from langchain.messages import AIMessage, HumanMessage
        from langchain.tools import tool
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from langgraph.checkpoint.memory import InMemorySaver

        from deermate.session_middleware import journal
        from deermate.store import digest
        from deermate.tooling import session_binding

        class Model(FakeMessagesListChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

        @tool("deermate_submit_task")
        def coding(project_id: str, prompt: str, idempotency_key: str) -> str:
            """Submit a coding request; the guard must replace this callable."""
            raise AssertionError("Unguarded tool handler ran")

        tag_mcp_tool(coding, server_name="deermate", transport="stdio")

        class Submitter:
            def __init__(self):
                self.records, self.requests = [], []

            async def list_tasks(self, **scope):
                return [
                    r
                    for r in self.records
                    if r["user_id"] == scope["user_id"]
                    and r["thread_id"] == scope["thread_id"]
                    and r["_thread_incarnation"] == scope["thread_incarnation"]
                ]

            async def submit(self, *, driver_name, request):
                self.requests.append(request)
                record = {
                    "id": request.local_task_id,
                    "user_id": request.user_id,
                    "thread_id": request.thread_id,
                    "_thread_incarnation": request.thread_incarnation,
                    "server_name": request.server_name,
                    "driver_name": driver_name,
                    "driver_data": request.driver_data,
                    "status": "completed",
                    "task_name": request.task_name,
                    "remote_task_id": digest({"id": request.local_task_id})[:32],
                    "created_at": str(len(self.records)),
                    "result": {"session_id": "native"},
                }
                self.records.insert(0, record)
                return record

        submitter = Submitter()
        set_mcp_task_submitter(submitter)
        messages = []
        for project in ("demo", "demo", "another-project"):
            messages.extend(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "deermate_submit_task",
                                "id": "provider-repeated-id",
                                "args": {
                                    "project_id": project,
                                    "prompt": "Explain the code",
                                    "idempotency_key": "model-does-not-control-identity",
                                },
                            }
                        ],
                    ),
                    AIMessage(content="Done"),
                ]
            )
        middleware = load_configured_extension_middlewares(get_app_config())
        assert len(middleware) == 1
        graph = create_agent(
            Model(responses=messages),
            tools=[coding],
            middleware=middleware,
            checkpointer=InMemorySaver(),
        )
        context = {"user_id": "owner", "thread_id": "chat", "thread_incarnation": "inc"}
        config = {"configurable": {"thread_id": "chat"}}
        first = await graph.ainvoke(
            {"messages": [HumanMessage(content="请帮我修复登录问题。补测试")]},
            config,
            context=context | {"run_id": "one"},
        )
        assert first["title"] == "修复登录问题"
        assert first["deermate_coding_session"]["binding_id"]
        graph.update_state(config, {"title": "手动命名"})
        second = await graph.ainvoke(
            {"messages": [HumanMessage(content="继续解释")]},
            config,
            context=context | {"run_id": "two"},
        )
        assert second["title"] == "手动命名"
        third = await graph.ainvoke(
            {"messages": [HumanMessage(content="换项目")]},
            config,
            context=context | {"run_id": "three"},
        )
        assert len(submitter.requests) == 2
        assert [r.driver_data["submit_tool"] for r in submitter.requests] == [
            "submit_task",
            "continue_task",
        ]
        assert any(
            '"status": "not_submitted"' in m.content
            for m in third["messages"]
            if getattr(m, "type", None) == "tool"
        )

        class Runs:
            async def get_state(self, *, thread_id):
                if thread_id != "chat":
                    raise PermissionError("Not owned")
                return {"values": second}

        ctx = SimpleNamespace(
            principal=SimpleNamespace(user_id="owner", is_admin=True, is_internal=False),
            agent_runs=Runs(),
        )
        view = await session_binding({"thread_id": "chat"}, ctx)
        assert view["bound"] and view["executor"] == "codex" and view["round"] == 2
        assert view["title"] == "手动命名" and view["native_session"] == "native"
        try:
            await session_binding({"thread_id": "other-chat"}, ctx)
        except PermissionError:
            pass
        else:
            raise AssertionError("Cross-chat inspection accepted")
        saved = journal()
        assert (
            saved.owned_binding(
                first["deermate_coding_session"]["binding_id"], "another-owner", "chat"
            )
            is None
        )
        from unittest.mock import patch

        from deermate.session_middleware import CodingSessionMiddleware

        called = []

        async def fallback(request):
            called.append(request)
            raise AssertionError("Admission failure must not call the unguarded handler")

        with patch("deermate.session_middleware.journal", side_effect=OSError("private path")):
            failure = await CodingSessionMiddleware().awrap_tool_call(
                SimpleNamespace(
                    tool=coding,
                    tool_call={"name": coding.name, "id": "fail", "args": {}},
                    runtime=SimpleNamespace(context=context | {"run_id": "four"}, config={}),
                ),
                fallback,
            )
        assert '"status": "outcome_unknown"' in failure.content
        assert "private path" not in failure.content and not called
        return {
            "status": "passed",
            "model_calls": 0,
            "native_calls": 0,
            "checks": [
                "configured_middleware_loaded",
                "real_graph_tool_interception",
                "repeat_provider_call_id_across_runs",
                "one_root_then_continuation",
                "automatic_first_message_title",
                "manual_title_preserved",
                "project_switch_rejected",
                "binding_action_uses_host_ownership",
                "canonical_binding_display",
                "journal_failure_never_falls_through",
            ],
        }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify())))
