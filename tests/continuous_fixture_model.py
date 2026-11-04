"""Explicit offline fixture only; never installed in the production wheel."""

import asyncio

from deerflow_extension_api import BackendAction, PluginContribution
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from deermate import continuous, continuous_middleware


class FixtureModel(FakeMessagesListChatModel):
    responses: list = [AIMessage(content="这是离线验收回复。秘书会话已连接，你可以继续交代工作。")]

    def bind_tools(self, tools, **kwargs):
        return self


def fixture_model(name):
    if name != "continuous-fixture":
        raise PermissionError("This isolated fixture only permits its Fake model")
    return FixtureModel()


class FixtureMiddleware(continuous_middleware.ContinuousMiddleware):
    pass


async def delayed_perform(payload, context):
    with continuous.gate(context.principal.user_id) as (db, _):
        db.execute(
            "CREATE TABLE IF NOT EXISTS continuous_fixture_deliveries("
            "operation TEXT PRIMARY KEY,deliveries INTEGER NOT NULL)"
        )
        db.execute(
            "INSERT INTO continuous_fixture_deliveries VALUES(?,1) "
            "ON CONFLICT(operation) DO UPDATE SET deliveries=deliveries+1",
            (payload["operation_id"],),
        )
    result = await continuous.perform(payload, context)
    op = continuous.load(context.principal.user_id, payload)
    if op["data"].get("message") == "fixture-lost-ack":
        await asyncio.sleep(15)  # Let the verifier terminate Go after durable admission.
    return result


def install(registry, config):
    continuous_middleware.bounded_model = fixture_model
    if not registry.plugin(
        PluginContribution(
            namespace=continuous.NAMESPACE,
            title="ISOLATED OFFLINE FIXTURE",
            enabled=True,
            backend=(
                BackendAction("perform", delayed_perform),
                BackendAction("query", continuous.query),
                BackendAction("capabilities", continuous.capabilities),
            ),
        )
    ):
        raise RuntimeError("The pinned extension contracts are required")
