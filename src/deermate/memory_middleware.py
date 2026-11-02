"""Budgeted personal-fact injection; no global summaries or automatic backfill."""

import asyncio
import sqlite3

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage


class PersonalMemoryMiddleware(AgentMiddleware):
    @staticmethod
    def _context(request):
        from deerflow.runtime.user_context import resolve_runtime_user_id

        from .memory import runtime_memory

        owner = resolve_runtime_user_id(request.runtime)
        latest = next(
            (m for m in reversed(request.messages) if getattr(m, "type", "") == "human"),
            None,
        )
        if latest is None:
            return ""
        content = latest.content
        if isinstance(content, list):
            content = " ".join(
                block["text"]
                for block in content
                if isinstance(block, dict)
                and block.get("type") in {"text", "input_text"}
                and isinstance(block.get("text"), str)
            )
        if not isinstance(content, str):
            return ""
        try:
            return runtime_memory().context(owner, content[:512])
        except (PermissionError, sqlite3.OperationalError):
            # Missing Go profile/schema is disabled, never a default-user bucket.
            return ""

    @staticmethod
    def _inject(request, context):
        if not context:
            return request
        previous = request.system_message.content if request.system_message else ""
        if isinstance(previous, str):
            content = previous + "\n\n" + context
        else:
            content = list(previous) + [{"type": "text", "text": context}]
        return request.override(system_message=SystemMessage(content=content))

    def wrap_model_call(self, request, handler):
        return handler(self._inject(request, self._context(request)))

    async def awrap_model_call(self, request, handler):
        context = await asyncio.to_thread(self._context, request)
        return await handler(self._inject(request, context))
