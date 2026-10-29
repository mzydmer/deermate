"""Fail-closed configured middleware for the pinned DeerFlow coding tools.

Deliberately not an observation-plugin middleware: those isolate failures by
passing through, which cannot enforce a single-session admission policy.
"""

import json
from typing import NotRequired

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.messages import ToolMessage
from langgraph.types import Command

from .chat_sessions import (
    ChatScope,
    SessionJournal,
    SessionUnknown,
    ask_in_chat,
    title_from_messages,
)
from .conversation import ConversationError

DEFAULT_PROFILES = {"deermate": "codex", "deermate-home": "codex"}


def journal():
    from deerflow.config.paths import get_paths

    return SessionJournal(get_paths().base_dir / "data/deermate-chat-sessions.sqlite3")


class CodingSessionState(AgentState):
    title: NotRequired[str | None]
    deermate_coding_session: NotRequired[dict | None]


class CodingSessionMiddleware(AgentMiddleware[CodingSessionState]):
    state_schema = CodingSessionState

    def __init__(self, profiles=None):
        self.profiles = dict(DEFAULT_PROFILES if profiles is None else profiles)
        if not self.profiles or any(v not in {"codex", "claude"} for v in self.profiles.values()):
            raise ValueError("Explicit registered coding executor profiles are required")

    def before_agent(self, state, runtime):
        if not str(state.get("title") or "").strip():
            title = title_from_messages(state.get("messages", []))
            if title:
                return {"title": title}
        return None

    async def abefore_agent(self, state, runtime):
        return self.before_agent(state, runtime)

    async def awrap_tool_call(self, request, handler):
        from deerflow.config import get_app_config
        from deerflow.mcp.tasks.models import TaskSubmitRequest
        from deerflow.mcp.tasks.runtime import get_mcp_task_submitter
        from deerflow.mcp_scope import runtime_thread_incarnation
        from deerflow.tools.builtins.list_uploaded_files_tool import (
            _resolve_thread_id,
            _resolve_user_id,
        )
        from deerflow.tools.mcp_metadata import get_mcp_source

        tool, call, runtime = request.tool, request.tool_call, request.runtime
        source = get_mcp_source(tool) if tool is not None else None
        server = source.get("server_name") if source else None
        role = None
        if server in self.profiles:
            for raw in ("submit_task", "continue_task"):
                if call["name"] in {raw, f"{server}_{raw}"}:
                    role = raw
        elif tool is not None and call["name"] == "continue_codex" and not source:
            role = "continue_codex"
        if role is None:
            return await handler(request)
        try:
            scope = ChatScope(
                _resolve_user_id(runtime),
                _resolve_thread_id(runtime),
                runtime_thread_incarnation(runtime),
            )
            saved = journal()
            if role == "continue_codex":
                binding = saved.binding(scope)
                if binding:
                    server = binding["server"]
                else:
                    # Legacy adoption can only select one actually observed server.
                    from .chat_sessions import coding_records

                    records = await get_mcp_task_submitter().list_tasks(
                        **scope.query(), limit=50, active_only=False
                    )
                    servers = {
                        r["server_name"] for r in coding_records(records, scope, self.profiles)
                    }
                    if len(servers) != 1:
                        raise ConversationError("No single coding session exists in this chat.")
                    server = servers.pop()
            config = get_app_config().extensions.mcp_servers.get(server)
            if config is None or not config.enabled:
                raise ConversationError("The bound coding connection is disabled or unavailable.")
            starts = [
                t
                for t in config.task_toolsets
                if (t.submit_tool, t.status_tool, t.cancel_tool)
                == ("submit_task", "get_task_status", "cancel_task")
            ]
            follows = [
                t
                for t in config.task_toolsets
                if (t.submit_tool, t.status_tool, t.cancel_tool)
                == ("continue_task", "get_continuation_status", "cancel_continuation_task")
            ]
            if len(starts) != 1 or len(follows) != 1:
                raise ConversationError(
                    "The coding connection needs both task lifecycle contracts."
                )
            args = call.get("args") or {}
            result = await ask_in_chat(
                saved,
                get_mcp_task_submitter(),
                TaskSubmitRequest,
                scope=scope,
                profiles=self.profiles,
                call_id=call["id"],
                run_id=(runtime.context or {}).get("run_id"),
                server=server,
                message=args.get("prompt") if role == "submit_task" else args.get("message"),
                project=args.get("project_id") if role == "submit_task" else None,
                explicit_task=args.get("task") if role == "continue_codex" else None,
                remote_parent=args.get("task_id") if role == "continue_task" else None,
                root_task_name=starts[0].name,
            )
        except SessionUnknown as error:
            result = {"status": "outcome_unknown", "message": str(error)}
        except ConversationError as error:
            result = {"status": "not_submitted", "message": str(error)}
        except Exception:
            # Never fall through to the original unguarded coding tool on failure.
            result = {
                "status": "outcome_unknown",
                "message": "Coding session admission "
                "is unavailable. Inspect this chat's tasks; do not create a replacement.",
            }
        message = ToolMessage(
            content=json.dumps(result), name=call["name"], tool_call_id=call["id"]
        )
        if result.get("binding_id"):
            return Command(
                update={
                    "messages": [message],
                    "deermate_coding_session": {
                        "binding_id": result["binding_id"],
                    },
                }
            )
        return message
