"""Explicitly enrolled SSH forwarding to an independent loopback Worker."""

import asyncio
import contextlib
import hashlib
import os
import stat
import time
from datetime import UTC, datetime
from pathlib import Path

import asyncssh
import httpx

from .bridge import BridgeError, TaskBridge, TaskMissing, read_token, task_path
from .remote_config import enrolled_worker


def _read_file(path: Path, *, private: bool) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            forbidden = 0o077 if private else 0o022
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & forbidden:
                raise BridgeError("SSH credential/trust file has unsafe type or permissions.")
            data = source.read(64_001)
            if not data or len(data) > 64_000:
                raise BridgeError("SSH credential/trust file is empty or oversized.")
            return data
    except OSError as error:
        raise BridgeError("SSH credential/trust file is unavailable.") from error


class SSHTransport(httpx.AsyncBaseTransport):
    """No mutation retries. Only fresh, admitted connections may forward HTTP."""

    def __init__(self, config: Path, worker_id: str):
        self.config = config.absolute()
        self.worker_id = worker_id
        self.settings = enrolled_worker(self.config, worker_id)
        self.state = "disconnected"
        self.lock = asyncio.Lock()
        self.connection = None
        self.listener = None
        self.http = None
        self.fingerprint = None
        self.connected_at = 0.0
        self.expiry_task = None

    def _material(self):
        current = enrolled_worker(self.config, self.worker_id)
        current.admit()
        if current != self.settings:
            raise BridgeError("SSH enrollment changed; restart this controller/MCP process.")
        private_key = _read_file(current.client_key, private=True)
        trust = _read_file(current.known_hosts, private=False)
        token = read_token(current.token_file)
        passphrase = None
        if current.passphrase_env:
            passphrase = os.environ.get(current.passphrase_env)
            if not passphrase:
                raise BridgeError("Configured SSH key passphrase is unavailable.")
        fingerprint = hashlib.sha256(
            private_key
            + b"\0"
            + trust
            + b"\0"
            + token.encode()
            + b"\0"
            + (passphrase or "").encode()
        ).digest()
        return private_key, trust, token, passphrase, fingerprint

    async def _drop(self):
        expiry, self.expiry_task = self.expiry_task, None
        if expiry and expiry is not asyncio.current_task():
            expiry.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await expiry
        connection, listener, http = self.connection, self.listener, self.http
        self.connection = self.listener = self.http = None
        self.fingerprint = None
        if connection:
            connection.close()
        if listener:
            listener.close()
        try:
            async with asyncio.timeout(2):
                if http:
                    await http.aclose()
                if listener:
                    await listener.wait_closed()
                if connection:
                    await connection.wait_closed()
        except (TimeoutError, OSError, asyncssh.Error):
            if connection:
                connection.abort()

    async def aclose(self):
        async with self.lock:
            await self._drop()
            self.state = "closed"

    async def _connect(self, private_key, trust, passphrase, fingerprint):
        worker = self.settings
        if (
            self.connection
            and not self.connection.is_closed()
            and fingerprint == self.fingerprint
            and time.monotonic() - self.connected_at < worker.max_connection_age_seconds
        ):
            return
        await self._drop()
        self.state = "connecting"
        key = await asyncio.to_thread(asyncssh.import_private_key, private_key, passphrase)
        known_hosts = asyncssh.import_known_hosts(trust.decode("utf-8"))
        async with asyncio.timeout(worker.connect_timeout_seconds + 1):
            self.connection = await asyncssh.connect(
                worker.host,
                worker.port,
                username=worker.username,
                known_hosts=known_hosts,
                client_keys=[key],
                client_certs=[],
                config=[],
                agent_path=None,
                agent_forwarding=False,
                password_auth=False,
                kbdint_auth=False,
                host_based_auth=False,
                gss_auth=False,
                gss_kex=False,
                preferred_auth=["publickey"],
                public_key_auth=True,
                disable_trivial_auth=True,
                x509_trusted_certs=[],
                x509_trusted_cert_paths=[],
                connect_timeout=worker.connect_timeout_seconds,
                login_timeout=worker.connect_timeout_seconds,
                keepalive_interval=15,
                keepalive_count_max=2,
            )
            self.listener = await self.connection.forward_local_port(
                "127.0.0.1", 0, "127.0.0.1", worker.worker_port
            )
        self.http = httpx.AsyncHTTPTransport(
            trust_env=False,
            retries=0,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )
        self.fingerprint = fingerprint
        self.connected_at = time.monotonic()
        connection = self.connection

        async def expire():
            remaining = (worker.expires_at - datetime.now(UTC)).total_seconds()
            await asyncio.sleep(max(0, min(worker.max_connection_age_seconds, remaining)))
            async with self.lock:
                if self.connection is connection:
                    await self._drop()
                    self.state = "disconnected"

        self.expiry_task = asyncio.create_task(expire())

    async def _exchange(self, request):
        url = request.url.copy_with(host="127.0.0.1", port=self.listener.get_port())
        headers = httpx.Headers(request.headers)
        headers["Host"] = f"127.0.0.1:{self.listener.get_port()}"
        forwarded = httpx.Request(
            request.method,
            url,
            headers=headers,
            stream=request.stream,
            extensions=request.extensions,
        )
        response = await self.http.handle_async_request(forwarded)
        try:
            chunks, size = [], 0
            async for chunk in response.aiter_raw():
                size += len(chunk)
                if size > 2_000_000:
                    raise BridgeError("SSH Worker response exceeded the transport limit.")
                chunks.append(chunk)
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                stream=httpx.ByteStream(b"".join(chunks)),
                request=request,
            )
        finally:
            await response.aclose()

    async def handle_async_request(self, request):
        if request.url.scheme != "http" or request.url.host != "127.0.0.1":
            raise BridgeError("SSH transport accepts only the configured loopback Worker API.")
        async with self.lock:
            try:
                private_key, trust, token, passphrase, fingerprint = await asyncio.to_thread(
                    self._material
                )
                await self._connect(private_key, trust, passphrase, fingerprint)
                headers = {"Authorization": f"Bearer {token}"}
                capabilities = await self._exchange(
                    httpx.Request(
                        "GET",
                        "http://127.0.0.1/capabilities",
                        headers=headers,
                        extensions=request.extensions,
                    )
                )
                await capabilities.aread()
                if capabilities.status_code != 200:
                    raise BridgeError("SSH Worker credential or local access check was rejected.")
                payload = capabilities.json()
                if (
                    not isinstance(payload, dict)
                    or payload.get("instance_id") != self.settings.expected_instance_id
                ):
                    raise BridgeError("SSH Worker instance identity did not match enrollment.")
                self.settings.admit()
                request.headers["Authorization"] = f"Bearer {token}"
                result = await self._exchange(request)
                self.state = "ready"
                return result
            except asyncio.CancelledError:
                self.state = "outcome_unknown"
                await self._drop()
                raise
            except asyncssh.HostKeyNotVerifiable as error:
                self.state = "host_key_rejected"
                await self._drop()
                raise BridgeError(
                    "SSH host key was rejected; verify trusted host identity."
                ) from error
            except asyncssh.PermissionDenied as error:
                self.state = "authentication_rejected"
                await self._drop()
                raise BridgeError("SSH dedicated client key was rejected.") from error
            except BridgeError:
                self.state = "access_rejected"
                await self._drop()
                raise
            except (OSError, TimeoutError, asyncssh.Error, httpx.HTTPError, ValueError) as error:
                self.state = "offline"
                await self._drop()
                raise BridgeError(
                    "SSH Worker unavailable; task outcome is unknown. No mutation was retried."
                ) from error


class RemoteTaskBridge(TaskBridge):
    def __init__(self, config: Path, worker_id: str, *, transport=None):
        self.transport = transport if transport else SSHTransport(config, worker_id)
        self.instance_id = self.transport.settings.expected_instance_id
        self.worker_id = worker_id
        super().__init__(self.transport.settings.token_file, transport=self.transport)

    async def _request(self, method, path, body=None):
        try:
            return await super()._request(method, path, body)
        except BridgeError as error:
            if not isinstance(error, TaskMissing):
                await self.transport.aclose()
            raise

    def native_id(self, handle):
        prefix, separator, task_id = handle.partition(":")
        if separator != ":" or prefix != self.instance_id:
            raise BridgeError("Task handle belongs to a different Worker instance.")
        task_path(task_id)
        return task_id

    def _bound(self, result):
        task_id = result["task_id"]
        result["task_id"] = f"{self.instance_id}:{task_id}"
        result["worker_id"] = self.worker_id
        command = f"deermate --config CONTROLLER_TOML --worker {self.worker_id}"
        if "input_required" in result:
            result["input_required"].update(
                {
                    "inspect_command": f"{command} status {task_id}",
                    "events_command": f"{command} events {task_id}",
                }
            )
        if "result" in result:
            result["result"]["diff_command"] = f"{command} diff {task_id}"
        return result

    async def submit(self, project_id, prompt, idempotency_key):
        return self._bound(await super().submit(project_id, prompt, idempotency_key))

    async def status(self, task_id):
        return self._bound(await super().status(self.native_id(task_id)))

    async def cancel(self, task_id):
        return self._bound(await super().cancel(self.native_id(task_id)))
