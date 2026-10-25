import os
import re
import secrets
import stat
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.datastructures import Headers

from .config import Settings
from .models import AnswerInput, Conflict, ResumeTask, SubmitTask
from .worker import Worker


class LocalBoundary:
    """Check local Host/Origin and bound the body before JSON parsing or authentication."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        host = headers.get("host", "")
        error = None
        if not re.fullmatch(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?", host):
            error = Response("Invalid local Host", status_code=403)
        elif headers.get("origin"):
            error = Response("Browser origins are not supported by this local API", status_code=403)
        if error:
            await error(scope, receive, send)
            return
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > 64_000:
                await Response("Request body exceeds 64 KB", status_code=413)(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        async def no_cache(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-store")]
            await send(message)

        await self.app(scope, bounded_receive, no_cache)


def token_file(state_dir: Path) -> str:
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state_dir / "api.token"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("API token must be a regular file")
        os.fchmod(f.fileno(), 0o600)
        token = f.read(1024).strip()
    if len(token) < 32:
        raise ValueError("API token must be at least 32 characters")
    return token


def create_app(settings: Settings, token: str | None = None) -> FastAPI:
    access_token = token if token is not None else token_file(settings.state_dir)
    bearer = HTTPBearer(auto_error=False)

    @asynccontextmanager
    async def lifespan(app):
        worker = Worker(settings)
        app.state.worker = worker
        await worker.start()
        try:
            yield
        finally:
            await worker.close()

    app = FastAPI(
        title="DeerMate local worker",
        version="0.1.0a1",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    async def authorized(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if not credentials or not secrets.compare_digest(credentials.credentials, access_token):
            raise HTTPException(401, "A valid local API bearer token is required")

    def worker(request: Request) -> Worker:
        return request.app.state.worker

    app.add_middleware(LocalBoundary)

    @app.exception_handler(KeyError)
    async def missing_task(request, error):
        return Response("Task or project not found", status_code=404)

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(error)}, status_code=409)

    auth = [Depends(authorized)]

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0a1", "mode": "local-only"}

    @app.get("/capabilities", dependencies=auth)
    async def capabilities(request: Request):
        return {
            "protocol_version": 1,
            "instance_id": worker(request).store.instance_id,
            "adapter": "codex-app-server",
            "operations": ["submit", "status", "events", "cancel", "resume", "input"],
            "remote": False,
        }

    @app.post("/tasks", dependencies=auth)
    async def submit(body: SubmitTask, request: Request, response: Response):
        if body.project_id not in settings.projects:
            raise HTTPException(404, "Project is not registered")
        task, created = worker(request).store.submit(body, settings.policy(body.project_id))
        response.status_code = 201 if created else 200
        return task

    @app.get("/tasks", dependencies=auth)
    async def tasks(request: Request, limit: int = Query(default=100, ge=1, le=100)):
        return {"tasks": worker(request).store.list_tasks(limit)}

    @app.get("/tasks/{task_id}", dependencies=auth)
    async def status(task_id: str, request: Request):
        return worker(request).store.get(task_id)

    @app.get("/tasks/{task_id}/events", dependencies=auth)
    async def events(
        task_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=100),
    ):
        rows = worker(request).store.events(task_id, after, limit)
        return {"events": rows, "next_cursor": rows[-1]["cursor"] if rows else after}

    @app.get("/tasks/{task_id}/diff", dependencies=auth)
    async def diff(task_id: str, request: Request):
        task = worker(request).store.get(task_id)
        if not task.result:
            raise HTTPException(409, "Task has no collected evidence yet")
        return Response(task.result.get("diff", ""), media_type="text/plain")

    @app.post("/tasks/{task_id}/cancel", dependencies=auth)
    async def cancel(task_id: str, request: Request):
        return await worker(request).cancel(task_id)

    @app.post("/tasks/{task_id}/resume", dependencies=auth)
    async def resume(task_id: str, body: ResumeTask, request: Request):
        return worker(request).store.resume(task_id, body)

    @app.post("/tasks/{task_id}/input", dependencies=auth)
    async def answer(task_id: str, body: AnswerInput, request: Request):
        try:
            return await worker(request).answer(task_id, body.answers)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    return app
