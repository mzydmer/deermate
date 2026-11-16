import asyncio
import contextlib
import errno
import os
import signal
import sys

import pytest

from deermate.rpc import AppServer, RpcError


async def live_client(tmp_path, *, ignore_term=False):
    fixture = tmp_path / "server.py"
    fixture.write_text(
        "import json,os,signal,sys\n"
        + ("signal.signal(signal.SIGTERM,signal.SIG_IGN)\n" if ignore_term else "")
        + "for line in sys.stdin:\n"
        " m=json.loads(line)\n"
        " if m.get('method')=='fixture/exit': os._exit(0)\n"
        " if 'id' in m: print(json.dumps({'id':m['id'],'result':{}}),flush=True)\n"
    )
    client = AppServer([sys.executable, str(fixture)], str(tmp_path))
    await client.start()
    return client


@pytest.mark.parametrize("error_number", [errno.EPERM, errno.ESRCH])
@pytest.mark.parametrize("error_at", ["lookup", "signal"])
async def test_close_reconciles_reaped_child_before_asyncio_exit_callback(
    tmp_path, monkeypatch, error_number, error_at
):
    client = await live_client(tmp_path)
    process = client.process
    transport = process._transport
    publish_exit = transport._process_exited
    reaped = asyncio.Event()
    codes = []

    def defer_exit(code):
        # Real child watcher has reaped the real subprocess; only publication is held.
        codes.append(code)
        reaped.set()

    monkeypatch.setattr(transport, "_process_exited", defer_exit)
    calls = []

    def publish_and_fail():
        asyncio.get_running_loop().call_soon(publish_exit, codes.pop())
        raise OSError(error_number, os.strerror(error_number))

    def race_lookup(pid):
        assert pid == process.pid
        if error_at == "lookup":
            publish_and_fail()
        return pid

    def race_signal(group, sig):
        calls.append((group, sig))
        publish_and_fail()

    try:
        await client.send({"method": "fixture/exit"})
        async with asyncio.timeout(3):
            await reaped.wait()
        assert process.returncode is None
        with pytest.raises(ProcessLookupError):
            os.getpgid(process.pid)
        # The lookup may have preceded exit; model the resulting signal error exactly.
        monkeypatch.setattr(os, "getpgid", race_lookup)
        monkeypatch.setattr(os, "killpg", race_signal)
        async with asyncio.timeout(3):
            await client.close()
        assert process.returncode == 0
        assert calls == ([(process.pid, signal.SIGTERM)] if error_at == "signal" else [])
        assert client.reader.done() and client.stderr_reader.done()
        await client.close()  # Already closed: no second signal or synthetic process.
        assert len(calls) == (1 if error_at == "signal" else 0)
    finally:
        for code in codes:
            publish_exit(code)
        await process.wait()
        for task in (client.reader, client.stderr_reader):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


@pytest.mark.parametrize("denied_signal", [signal.SIGTERM, signal.SIGKILL])
async def test_live_permission_denial_is_not_an_exit_confirmation(
    tmp_path, monkeypatch, denied_signal
):
    client = await live_client(tmp_path, ignore_term=denied_signal == signal.SIGKILL)
    real_killpg = os.killpg
    denied = PermissionError(errno.EPERM, "fixture signal denied")
    calls = []

    def deny_signal(group, sig):
        calls.append((group, sig))
        if sig == denied_signal:
            raise denied
        real_killpg(group, sig)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "killpg", deny_signal)
            patch.setattr("deermate.rpc.STOP_TIMEOUT_SECONDS", 0.05)
            async with asyncio.timeout(2):
                with pytest.raises(PermissionError) as caught:
                    await client.close()
        assert caught.value is denied
        assert client.process.returncode is None
        assert calls == [
            (client.process.pid, sig)
            for sig in (
                [signal.SIGTERM]
                if denied_signal == signal.SIGTERM
                else [signal.SIGTERM, signal.SIGKILL]
            )
        ]
        assert client.reader.done() and client.stderr_reader.done()
    finally:
        real_killpg(client.process.pid, signal.SIGKILL)
        await client.process.wait()
        await client.close()


async def test_changed_group_never_signals_an_unrelated_live_group(tmp_path, monkeypatch):
    (tmp_path / "owner").mkdir()
    (tmp_path / "peer").mkdir()
    client = await live_client(tmp_path / "owner")
    peer = await live_client(tmp_path / "peer")
    calls = []
    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "getpgid", lambda pid: peer.process.pid)
            patch.setattr(os, "killpg", lambda group, sig: calls.append((group, sig)))
            with pytest.raises(RpcError, match="group changed; stop unconfirmed"):
                await client.close()
        assert not calls and client.process.returncode is None
        assert await peer.request("fixture/ping", {}) == {}
        assert peer.process.returncode is None
    finally:
        await client.close()
        await peer.close()


async def test_term_timeout_escalates_only_the_owned_group(tmp_path, monkeypatch):
    client = await live_client(tmp_path, ignore_term=True)
    real_killpg = os.killpg
    calls = []

    def record_signal(group, sig):
        calls.append((group, sig))
        real_killpg(group, sig)

    try:
        monkeypatch.setattr("deermate.rpc.STOP_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(os, "killpg", record_signal)
        async with asyncio.timeout(2):
            await client.close()
        assert client.process.returncode == -signal.SIGKILL
        assert calls == [(client.process.pid, sig) for sig in [signal.SIGTERM, signal.SIGKILL]]
        assert client.reader.done() and client.stderr_reader.done()
    finally:
        if client.process.returncode is None:
            real_killpg(client.process.pid, signal.SIGKILL)
            await client.process.wait()
        await client.close()


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
