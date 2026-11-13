"""DeerFlow boundary instrumentation through its public middleware/interceptor APIs."""

from langchain.agents.middleware import AgentMiddleware

from . import telemetry
from .runtime_telemetry import operation_parent


def runtime_parent(runtime):
    if telemetry._provider is None:
        return {}
    try:
        from .continuous_middleware import profile

        return operation_parent(profile(runtime))
    except Exception:
        # The policy middleware still makes its independent fail-closed decision.
        return {}


def usage(response):
    messages = getattr(response, "result", []) or []
    if not isinstance(messages, list):
        return
    for message in messages:
        value = getattr(message, "usage_metadata", None)
        if isinstance(value, dict):
            telemetry.current_attributes(
                {
                    "gen_ai.usage.input_tokens": value.get("input_tokens"),
                    "gen_ai.usage.output_tokens": value.get("output_tokens"),
                }
            )


class TelemetryMiddleware(AgentMiddleware):
    def __init__(self):
        telemetry.configure("deermate-gateway")

    def wrap_model_call(self, request, handler):
        with telemetry.span(
            "agent.model",
            parent=runtime_parent(request.runtime),
            attributes={"gen_ai.operation.name": "chat"},
        ):
            result = handler(request)
            usage(result)
            return result

    async def awrap_model_call(self, request, handler):
        with telemetry.span(
            "agent.model",
            parent=runtime_parent(request.runtime),
            attributes={"gen_ai.operation.name": "chat"},
        ):
            result = await handler(request)
            usage(result)
            return result

    def wrap_tool_call(self, request, handler):
        with telemetry.span(
            "agent.tool",
            parent=runtime_parent(request.runtime),
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "deermate.tool_name": request.tool_call.get("name"),
            },
        ):
            return handler(request)

    async def awrap_tool_call(self, request, handler):
        with telemetry.span(
            "agent.tool",
            parent=runtime_parent(request.runtime),
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "deermate.tool_name": request.tool_call.get("name"),
            },
        ):
            return await handler(request)


def build_mcp_interceptor():
    async def intercept(request, handler):
        with telemetry.span("mcp.client", attributes={"deermate.tool_name": request.name}):
            values = dict(request.headers or {})
            for key in list(values):
                if key.lower() in {"traceparent", "tracestate", "baggage", "x-deermate-trace-refs"}:
                    del values[key]
            values.update(telemetry.headers())
            return await handler(request.override(headers=values))

    return intercept
