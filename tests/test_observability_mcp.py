import asyncio
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from otel_receiver import Receiver
from test_observability import traced as traced

from deermate import telemetry


@pytest.mark.asyncio
async def test_actual_mcp_stdio_metadata_reaches_worker(local_server, traced):
    config, port, _ = local_server
    with Receiver() as receiver:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "deermate.cli", "--config", str(config), "--port", str(port), "mcp"],
            env={
                "DEERMATE_TELEMETRY_ENABLED": "true",
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": receiver.endpoint,
                "OTEL_SERVICE_NAME": "deermate-mcp-fixture",
                "OTEL_TRACES_SAMPLER": "always_on",
            },
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                with telemetry.span("fixture.entry", refs={"operation_id": "mcp-operation"}):
                    original = telemetry.metadata()
                    result = await session.call_tool(
                        "submit_task",
                        {
                            "project_id": "demo",
                            "prompt": "PRIVATE_MCP_PROMPT",
                            "idempotency_key": "mcp-once",
                        },
                        meta={"headers": telemetry.headers()},
                    )
                    assert not result.isError
                    task = result.structuredContent["task_id"]
                async with asyncio.timeout(10):
                    while True:
                        response = await session.call_tool("get_task_status", {"task_id": task})
                        if response.structuredContent["worker_status"] == "completed":
                            break
                        await asyncio.sleep(0.02)
                invalid_meta = await session.call_tool(
                    "get_task_status", {"task_id": task}, meta={"headers": []}
                )
                assert not invalid_meta.isError
                assert await asyncio.to_thread(receiver.wait_for_span, "mcp.server", 8)
        received = receiver.spans()
        assert received and any(s.name == "mcp.server" for s in received)
        native = next(s for s in traced.get_finished_spans() if s.name == "worker.execute")
        assert f"{native.context.trace_id:032x}" == original["traceparent"][3:35]
        assert native.attributes["deermate.operation_id"] == "mcp-operation"
        assert any(s.trace_id.hex() == original["traceparent"][3:35] for s in received)
        assert "PRIVATE_MCP_PROMPT" not in "".join(str(p) for p in receiver.payloads)
