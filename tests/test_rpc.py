import asyncio
import sys

import pytest

from deermate.rpc import AppServer, RpcError


async def test_malformed_json_fails_without_hanging(tmp_path):
    fixture = tmp_path / "bad.py"
    fixture.write_text("print('[]',flush=True)\n")
    client = AppServer([sys.executable, str(fixture)], str(tmp_path))
    try:
        async with asyncio.timeout(3):
            with pytest.raises((RpcError, BrokenPipeError)):
                await client.start()
    finally:
        await client.close()


async def test_stderr_is_drained_and_output_is_bounded(tmp_path):
    fixture = tmp_path / "noisy.py"
    fixture.write_text(
        "import sys,json\n"
        "sys.stderr.write('x'*200000); sys.stderr.flush()\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line)\n"
        " if 'id' in m: print(json.dumps({'id':m['id'],'result':{}}),flush=True)\n"
    )
    client = AppServer([sys.executable, str(fixture)], str(tmp_path))
    try:
        async with asyncio.timeout(3):
            await client.start()
        assert len(client.stderr_tail) <= 4096
    finally:
        await client.close()
