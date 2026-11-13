from . import telemetry
from .config import Settings
from .models import Task
from .rpc import AppServer, RpcError


class CodexAdapter:
    def __init__(self, settings: Settings, task: Task, record):
        self.settings, self.task, self.record = settings, task, record
        self.rpc = AppServer(settings.codex_command, task.workspace)
        self.session_id = task.session_id
        self.turn_id: str | None = None
        self.pending_input = None
        self.summary = ""
        self.policy_denied = False
        self.item_spans = {}

    @property
    def sandbox(self) -> dict:
        if self.settings.projects[self.task.project_id].allow_write:
            return {
                "type": "workspaceWrite",
                "writableRoots": [self.task.workspace],
                "networkAccess": False,
                "excludeTmpdirEnvVar": True,
                "excludeSlashTmp": True,
            }
        return {"type": "readOnly", "networkAccess": False}

    @telemetry.observed("codex.session.open")
    async def start(self):
        await self.rpc.start()
        params = {
            "cwd": self.task.workspace,
            "approvalPolicy": "never",
            "sandbox": "workspace-write"
            if self.sandbox["type"] == "workspaceWrite"
            else "read-only",
        }
        if self.settings.model:
            params["model"] = self.settings.model
        if self.session_id:
            params["threadId"] = self.session_id
            result = await self.rpc.request("thread/resume", params)
        else:
            result = await self.rpc.request("thread/start", params)
        thread = result["thread"]
        if thread.get("status", {}).get("type") == "active":
            raise RpcError("native thread is still active; refusing to start another turn")
        self.session_id = thread["id"]
        # Persist identity BEFORE turn/start; a lost acknowledgement is then reconcilable.
        await self.record("session.ready", {"session_id": self.session_id})
        telemetry.current_attributes({"deermate.native_session_id": self.session_id})
        turn = await self.rpc.request(
            "turn/start",
            {
                "threadId": self.session_id,
                "input": [{"type": "text", "text": self.task.prompt}],
                "cwd": self.task.workspace,
                "approvalPolicy": "never",
                "sandboxPolicy": self.sandbox,
            },
        )
        self.turn_id = turn["turn"]["id"]
        await self.record("turn.ready", {"turn_id": self.turn_id})
        telemetry.current_attributes({"deermate.native_turn_id": self.turn_id})

    @telemetry.observed("codex.turn")
    async def run(self) -> str:
        telemetry.current_attributes(
            {"deermate.native_session_id": self.session_id, "deermate.native_turn_id": self.turn_id}
        )
        while True:
            message = await self.rpc.events.get()
            method = message.get("method", "")
            params = message.get("params", {})
            if method == "deermate/transportClosed":
                raise RpcError(params["reason"])
            if params.get("threadId") not in (None, self.session_id):
                continue
            if params.get("turnId") not in (None, self.turn_id):
                continue
            if "id" in message:
                await self._server_request(message)
                continue
            # Keep bounded, completed evidence rather than token-by-token deltas.
            if method == "item/started":
                item = params.get("item", {})
                if (
                    item.get("type")
                    in {"commandExecution", "fileChange", "mcpToolCall", "webSearch"}
                    and isinstance(item.get("id"), str)
                    and item["id"] not in self.item_spans
                    and len(self.item_spans) < 128
                    and telemetry._provider is not None
                ):
                    self.item_spans[item["id"]] = telemetry.begin_item(
                        {
                            "gen_ai.operation.name": "execute_tool",
                            "deermate.native_session_id": self.session_id,
                            "deermate.native_turn_id": self.turn_id,
                            "deermate.native_item_id": item["id"],
                            "deermate.item_type": item["type"],
                        }
                    )
            elif method == "item/completed":
                item = params.get("item", {})
                telemetry.end_item(
                    self.item_spans.pop(item["id"], None)
                    if isinstance(item.get("id"), str)
                    else None,
                    item.get("status", "completed"),
                )
                telemetry.current_attributes({"deermate.item_type": item.get("type")})
                if item.get("type") == "agentMessage":
                    self.summary = item.get("text", "")[:64_000]
                await self.record("codex.item", {"item": self._bounded(item)})
            elif method == "thread/tokenUsage/updated":
                value = params.get("tokenUsage")
                usage = value.get("last") if isinstance(value, dict) else None
                if isinstance(usage, dict):
                    telemetry.current_attributes(
                        {
                            "gen_ai.usage.input_tokens": usage.get("inputTokens"),
                            "gen_ai.usage.output_tokens": usage.get("outputTokens"),
                        }
                    )
            elif method == "turn/completed":
                turn = params["turn"]
                if turn.get("id") != self.turn_id:
                    continue
                await self.record(
                    "codex.turn", {"status": turn["status"], "error": turn.get("error")}
                )
                telemetry.current_attributes({"deermate.status": turn["status"]})
                if turn["status"] == "failed":
                    raise RpcError(str(turn.get("error") or "native turn failed")[:2000])
                if turn["status"] not in {"completed", "interrupted"}:
                    raise RpcError("unknown native turn completion status")
                return turn["status"]

    @staticmethod
    def _bounded(item: dict) -> dict:
        return {
            key: value[:64_000] if isinstance(value, str) else value for key, value in item.items()
        }

    async def _server_request(self, message: dict):
        method, params, request_id = message["method"], message.get("params", {}), message["id"]
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            self.policy_denied = True
            await self.rpc.respond(request_id, {"decision": "decline"})
            await self.record("policy.denied", {"method": method})
        elif method == "item/permissions/requestApproval":
            self.policy_denied = True
            await self.rpc.respond(request_id, {"permissions": {}, "scope": "turn"})
            await self.record("policy.denied", {"method": method})
        elif method == "item/tool/requestUserInput":
            if self.pending_input is not None:
                raise RpcError("multiple simultaneous input requests are unsupported")
            self.pending_input = request_id
            await self.record("input.required", {"questions": params.get("questions", [])})
        else:
            self.policy_denied = True
            # Unknown tools/auth requests must never hang or gain authority by default.
            await self.rpc.send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": "DeerMate does not support this server request",
                    },
                }
            )
            await self.record("policy.denied", {"method": method})

    async def answer(self, answers: dict[str, list[str]]):
        if self.pending_input is None:
            raise ValueError("no live input request")
        await self.rpc.respond(
            self.pending_input,
            {"answers": {key: {"answers": values} for key, values in answers.items()}},
        )
        self.pending_input = None

    async def interrupt(self):
        if not self.turn_id:
            return
        await self.rpc.request(
            "turn/interrupt",
            {"threadId": self.session_id, "turnId": self.turn_id},
            timeout_seconds=5,
        )

    @telemetry.observed("worker.validation")
    async def validate(self, command: list[str]) -> dict:
        result = await self.rpc.request(
            "command/exec",
            {
                "command": command,
                "cwd": self.task.workspace,
                "sandboxPolicy": self.sandbox,
                "timeoutMs": self.settings.test_timeout_seconds * 1000,
            },
            timeout_seconds=self.settings.test_timeout_seconds + 10,
        )
        telemetry.current_attributes(
            {"deermate.validation_status": "passed" if result["exitCode"] == 0 else "failed"}
        )
        if result["exitCode"] != 0:
            telemetry.mark_error()
        return {
            "command": command,
            "exit_code": result["exitCode"],
            "stdout": result.get("stdout", "")[:64_000],
            "stderr": result.get("stderr", "")[:64_000],
        }

    async def close(self):
        for current in self.item_spans.values():
            telemetry.end_item(current, "incomplete")
        self.item_spans.clear()
        await self.rpc.close()
