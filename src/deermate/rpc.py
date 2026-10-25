import asyncio
import contextlib
import json
import os
import signal


class RpcError(RuntimeError):
    pass


class AppServer:
    """Bounded JSON Lines transport, with responses demultiplexed from notifications."""

    def __init__(self, argv: list[str], cwd: str):
        self.argv, self.cwd = argv, cwd
        self.process: asyncio.subprocess.Process | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.events: asyncio.Queue = asyncio.Queue(maxsize=512)
        self.sequence = 0
        self.reader: asyncio.Task | None = None
        self.stderr_reader: asyncio.Task | None = None
        self.stderr_tail = b""

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            *self.argv,
            cwd=self.cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=2 * 1024 * 1024,
            start_new_session=True,
        )
        self.reader = asyncio.create_task(self._read())
        self.stderr_reader = asyncio.create_task(self._stderr())
        await self.request(
            "initialize",
            {"clientInfo": {"name": "deermate", "title": "DeerMate", "version": "0.1.0a1"}},
        )
        await self.send({"method": "initialized"})

    async def _stderr(self):
        while chunk := await self.process.stderr.read(4096):
            self.stderr_tail = (self.stderr_tail + chunk)[-4096:]

    async def _read(self):
        reason = "app-server closed its output"
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if not isinstance(message, dict) or not isinstance(message.get("params", {}), dict):
                    raise ValueError("JSON-RPC messages and params must be objects")
                if "id" in message and not isinstance(message["id"], (int, str)):
                    raise ValueError("JSON-RPC IDs must be strings or integers")
                if "method" not in message and "id" in message:
                    future = self.pending.get(message["id"])
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(RpcError(str(message["error"])[:2000]))
                        else:
                            future.set_result(message.get("result", {}))
                else:
                    self.events.put_nowait(message)
        except (ValueError, json.JSONDecodeError, asyncio.QueueFull) as error:
            reason = f"invalid or excessive app-server output: {type(error).__name__}"
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RpcError(reason))
            # A full queue is a terminal transport error, never silent event loss.
            if self.events.full():
                self.events.get_nowait()
            self.events.put_nowait(
                {"method": "deermate/transportClosed", "params": {"reason": reason}}
            )

    async def send(self, message: dict):
        if not self.process or self.process.returncode is not None:
            raise RpcError("app-server is not running")
        self.process.stdin.write(json.dumps(message, ensure_ascii=False).encode() + b"\n")
        await self.process.stdin.drain()

    async def request(self, method: str, params: dict, *, timeout_seconds: float = 30):
        self.sequence += 1
        request_id = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({"id": request_id, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout_seconds)
        finally:
            self.pending.pop(request_id, None)

    async def respond(self, request_id, result: dict):
        await self.send({"id": request_id, "result": result})

    async def close(self):
        if self.process and self.process.returncode is None:
            # Only this instance's owned process group is signalled, never a persisted PID.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
                await self.process.wait()
        for task in (self.reader, self.stderr_reader):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
