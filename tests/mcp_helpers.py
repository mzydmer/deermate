import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def mcp_session(config, port):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deermate.cli", "--config", str(config), "--port", str(port), "mcp"],
        env={"HTTP_PROXY": "http://127.0.0.1:1", "ALL_PROXY": "http://127.0.0.1:1"},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(
            reader, writer, read_timeout_seconds=timedelta(seconds=15)
        ) as session:
            await session.initialize()
            yield session


async def call(session, name, **arguments):
    result = await session.call_tool(name, arguments)
    assert not result.isError, result.content
    assert result.structuredContent is not None
    return result.structuredContent


async def wait_status(session, task_id, states):
    async with asyncio.timeout(10):
        while True:
            result = await call(session, "get_task_status", task_id=task_id)
            if result["worker_status"] in states:
                return result
            await asyncio.sleep(0.02)
