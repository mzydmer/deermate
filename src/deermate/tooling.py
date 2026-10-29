"""Trusted, read-only diagnostics installed through DeerFlow's extension API.

Go still authenticates and admits public requests. These actions inspect the
existing runtime/configuration; they do not enroll servers or invoke MCP tools.
"""

import asyncio
from collections.abc import Mapping
from pathlib import Path

_discovering: set[str] = set()


def runtime_config() -> dict:
    """Shared minimal deployment additions (no host shell or filesystem tools)."""
    return {
        "tools": [
            {
                "name": "web_search",
                "group": "web",
                "use": "deerflow.community.ddg_search.tools:web_search_tool",
            },
            {"name": "web_fetch", "group": "web", "use": "deermate.web_tools:web_fetch"},
        ],
        "tool_groups": [{"name": "web"}],
        "plugins": [
            {
                "name": "deermate-tooling",
                "use": "deermate.tooling:install",
                "required": True,
            }
        ],
    }


def _admin(context):
    principal = context.principal
    if not principal.user_id or not principal.is_admin or principal.is_internal:
        raise PermissionError("An administrator account is required")
    return principal


async def _snapshot(scope, owner):
    if scope == "platform":
        from deerflow.config.extensions_config import ExtensionsConfig

        return await asyncio.to_thread(ExtensionsConfig.from_file)
    if scope == "personal":
        from deerflow.mcp.user_config import load_user_mcp_config

        return await asyncio.to_thread(load_user_mcp_config, owner)
    raise ValueError("Unknown connection scope")


async def inventory(payload: Mapping, context) -> dict:
    principal = _admin(context)
    from deerflow.config import get_app_config
    from deerflow.reflection import resolve_variable
    from langchain_core.tools import BaseTool

    config = get_app_config()
    native = []
    for entry in config.tools[:128]:
        try:
            tool = resolve_variable(entry.use, BaseTool)
            ready = tool.name == entry.name
        except Exception:
            ready = False
        native.append({"name": entry.name, "status": "loaded" if ready else "unavailable"})
    connections = []
    for scope in ("platform", "personal"):
        snapshot = await _snapshot(scope, principal.user_id)
        for name, server in list(snapshot.mcp_servers.items())[:128]:
            connections.append({"name": name, "scope": scope, "enabled": server.enabled})
    return {"native": native, "connections": connections}


async def discover(payload: Mapping, context) -> dict:
    principal = _admin(context)
    if principal.user_id in _discovering:
        return {"status": "busy", "tools": []}
    _discovering.add(principal.user_id)
    try:
        return await _discover(payload, principal.user_id)
    finally:
        _discovering.discard(principal.user_id)


async def _discover(payload, owner):
    scope, name = payload.get("scope"), payload.get("name")
    if scope not in {"platform", "personal"} or not isinstance(name, str) or not name:
        raise ValueError("Choose a saved connection")
    config = await _snapshot(scope, owner)
    server = config.mcp_servers.get(name)
    if server is None:
        return {"status": "not_configured", "tools": []}
    if not server.enabled:
        return {"status": "disabled", "tools": []}
    from deerflow.mcp.tools import get_mcp_tools_by_server

    try:
        # Exact saved definition, existing auth/lifecycle/session machinery.
        # No URL/command/header comes from the browser, and no call_tool occurs.
        groups = await asyncio.wait_for(
            get_mcp_tools_by_server(
                config,
                server_names=[name],
                personal_user_id=owner if scope == "personal" else None,
            ),
            timeout=20,
        )
    except TimeoutError:
        return {"status": "timeout", "tools": []}
    except Exception:
        # Transport exceptions can contain credential-bearing URLs/headers.
        return {"status": "unavailable", "tools": []}
    result = groups.get(name)
    if result is None:
        return {"status": "unavailable", "tools": []}
    names = [tool.name[:160] for tool in result.tools]
    return {"status": "discovered", "tools": names[:128], "total": len(names)}


def install(registry, config):
    from deerflow_extension_api import BackendAction, BrowserAssets, PluginContribution

    accepted = registry.plugin(
        PluginContribution(
            namespace="deermate.tooling",
            title="工具与连接 / Tools & connections",
            description="Inspect loaded tools and test saved MCP connections without running them.",
            enabled=True,
            frontend=BrowserAssets(
                module="deermate-tooling", root=Path(__file__).parent / "tooling_ui"
            ),
            backend=(BackendAction("inventory", inventory), BackendAction("discover", discover)),
        )
    )
    if not accepted:
        raise RuntimeError("Pinned DeerFlow plugin UI support is required")
