"""Run with the pinned DeerFlow Python; offline by default, no model calls.

--live-web additionally sends a fixed public query/URL to search/Jina providers.
All configuration, MCP metadata fixtures and files live in a temporary home.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from deermate.tooling import discover, inventory, runtime_config


async def verify(live):
    with tempfile.TemporaryDirectory(prefix="deermate-tooling-") as directory:
        root = Path(directory)
        config = root / "config.yaml"
        config.write_text(json.dumps({
            "config_version": 62,
            "models": [],
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            **runtime_config(),
        }))
        os.environ["DEER_FLOW_CONFIG_PATH"] = str(config)
        os.environ["DEER_FLOW_HOME"] = str(root / "home")
        from deerflow.config import get_app_config
        from deerflow.config.extensions_config import ExtensionsConfig
        from deerflow.extensions.browser_assets import load_browser_assets
        from deerflow.extensions.loader import load_extensions
        from deerflow.mcp.tools import get_mcp_tools_by_server
        from deerflow.tools import get_available_tools

        loaded, diagnostics = load_extensions(get_app_config().plugins)
        assert not any(d.level == "error" for d in diagnostics)
        plugin = loaded.plugins[0][1]
        assets = load_browser_assets(plugin.frontend)
        assert assets.entry == "index.mjs"
        native = get_available_tools(include_mcp=False)
        assert {"web_search", "web_fetch"} <= {t.name for t in native}
        reader = next(t for t in native if t.name == "web_fetch")
        for url in (
            "http://127.0.0.1", "http://100.100.100.200/latest/meta-data",
            "http://[::1]", "file:///etc/passwd", "https://user:secret@example.com",
            "http://2130706433", "http://example.com:18777",
        ):
            assert (await reader.ainvoke({"url": url})).startswith("Error:")
        context = SimpleNamespace(principal=SimpleNamespace(
            user_id="tooling-test", is_admin=True, is_internal=False
        ))
        current = await inventory({}, context)
        assert all(t["status"] == "loaded" for t in current["native"])
        assert current["connections"] == []

        fixture = root / "fixture_server.py"
        marker = root / "must-not-call"
        fixture.write_text(
            "from mcp.server.fastmcp import FastMCP\nfrom pathlib import Path\n"
            "server=FastMCP('metadata-fixture')\n@server.tool()\n"
            "def read_fixture() -> str:\n"
            f" Path({str(marker)!r}).touch()\n return 'must not run'\n"
            "server.run()\n"
        )
        snapshot = ExtensionsConfig.model_validate({"mcpServers": {"fixture": {
            "enabled": True, "command": sys.executable, "args": [str(fixture)],
        }}})
        groups = await asyncio.wait_for(get_mcp_tools_by_server(
            snapshot, server_names=["fixture"]
        ), 20)
        assert len(groups["fixture"].tools) == 1
        assert not marker.exists()
        assert (await discover({"scope": "platform", "name": "unknown"}, context))[
            "status"
        ] == "not_configured"
        checks = ["plugin_assets_loaded", "native_tools_assembled", "private_urls_rejected",
                  "inventory_loaded", "real_mcp_metadata_only", "unknown_server_not_contacted"]
        if live:
            search = next(t for t in native if t.name == "web_search")
            result = json.loads(await asyncio.wait_for(search.ainvoke({
                "query": "DeerFlow GitHub ByteDance", "max_results": 2,
            }), 45))
            assert result.get("results") and not result.get("error")
            # A public literal also works on development networks using fake-IP DNS.
            result = await reader.ainvoke({"url": "https://1.1.1.1/"})
            assert "1.1.1.1" in result and not result.startswith("Error:")
            checks.extend(["live_public_search", "live_public_page_read"])
        return {"status": "passed", "checks": checks, "model_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-web", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.live_web)), ensure_ascii=False))
