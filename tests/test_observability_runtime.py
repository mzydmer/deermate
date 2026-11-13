"""Run in the pinned Gateway environment; actual LangChain graph, synthetic model."""

import pytest

pytest.importorskip("langchain.agents")

from langchain.agents import create_agent  # noqa: E402
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from test_observability import traced as traced  # noqa: E402

from deermate import telemetry  # noqa: E402
from deermate.observability_middleware import TelemetryMiddleware  # noqa: E402


@pytest.mark.asyncio
async def test_actual_graph_model_tool_usage_and_content_privacy(traced):
    @tool
    def fixture_lookup(query: str) -> str:
        """Return a synthetic lookup result."""
        assert query == "PRIVATE_TOOL_INPUT"
        return "PRIVATE_TOOL_OUTPUT"

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = Model(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fixture_lookup",
                        "args": {"query": "PRIVATE_TOOL_INPUT"},
                        "id": "tool-one",
                        "type": "tool_call",
                    }
                ],
                usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
            ),
            AIMessage(
                content="PRIVATE_MODEL_REPLY",
                usage_metadata={"input_tokens": 20, "output_tokens": 4, "total_tokens": 24},
            ),
        ]
    )
    graph = create_agent(model, tools=[fixture_lookup], middleware=[TelemetryMiddleware()])
    with telemetry.span("graph.fixture", refs={"operation_id": "graph-operation"}):
        result = await graph.ainvoke({"messages": [HumanMessage(content="PRIVATE_USER_INPUT")]})
    assert result["messages"][-1].content == "PRIVATE_MODEL_REPLY"
    spans = traced.get_finished_spans()
    models = [s for s in spans if s.name == "agent.model"]
    tools = [s for s in spans if s.name == "agent.tool"]
    assert len(models) == 2 and len(tools) == 1
    assert [s.attributes["gen_ai.usage.input_tokens"] for s in models] == [12, 20]
    assert [s.attributes["gen_ai.usage.output_tokens"] for s in models] == [3, 4]
    assert len({s.context.trace_id for s in spans}) == 1
    assert all(s.attributes["deermate.operation_id"] == "graph-operation" for s in spans)
    assert "PRIVATE_" not in "".join(s.to_json() for s in spans)
