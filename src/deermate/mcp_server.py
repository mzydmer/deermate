"""Optional stdio MCP facade. Execution belongs to the independent Worker."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .bridge import BridgeError, TaskBridge
from .models import SubmitTask


class TaskLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class RemoteTaskLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(pattern=r"^[0-9a-f]{32}:[0-9a-f]{32}$")


class ConnectionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")


def create_server(token_path: Path, port: int = 18777, *, bridge=None) -> Server:
    remote = bridge is not None
    bridge = bridge if remote else TaskBridge(token_path, port)
    lookup = RemoteTaskLookup if remote else TaskLookup

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield
        finally:
            await bridge.close()

    server = Server("DeerMate tasks", lifespan=lifespan)
    tools = {
        "submit_task": (
            SubmitTask,
            bridge.submit,
            "Submit work to an administrator-registered project using a stable idempotency_key. "
            "Reuse the same key on retries. Returns a durable task_id promptly; "
            "running acknowledges tracking, not actual execution state. "
            "No arbitrary paths, commands or permissions are accepted.",
        ),
        "get_task_status": (
            lookup,
            bridge.status,
            "Read task state and bounded evidence by its saved ID. "
            "A tool error leaves task outcome unknown. input_required can mean "
            "native input, local review or explicit restart recovery; inspect its kind.",
        ),
        "cancel_task": (
            lookup,
            bridge.cancel,
            "Request interruption and return only a confirmed terminal outcome. "
            "Unconfirmed cancellation is a tool error. A completion race can return "
            "completed or failed. Repeating cancellation is safe.",
        ),
        "check_worker_connection": (
            ConnectionCheck,
            bridge.check_connection,
            "Check the administrator-configured Worker connection, identity and protocol. "
            "Read-only; accepts no target or credentials and never submits work. "
            "Returns reachable or blocked with a reason. This does not check native-agent "
            "login, capacity or project grants; existing task outcome is not checked.",
        ),
    }

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name=name,
                description=description,
                inputSchema=model.model_json_schema(),
                annotations=ToolAnnotations(
                    readOnlyHint=name in {"get_task_status", "check_worker_connection"},
                    idempotentHint=True,
                ),
            )
            for name, (model, _, description) in tools.items()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name not in tools:
            return CallToolResult(
                isError=True, content=[TextContent(type="text", text="Unknown DeerMate tool.")]
            )
        model, operation, _ = tools[name]
        request = model.model_validate(arguments)
        try:
            payload = await operation(**request.model_dump())
            return CallToolResult(
                structuredContent=payload,
                content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
            )
        except BridgeError as error:
            return CallToolResult(isError=True, content=[TextContent(type="text", text=str(error))])

    return server


async def run_server(token_path: Path, port: int, *, bridge=None):
    server = create_server(token_path, port, bridge=bridge)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())
