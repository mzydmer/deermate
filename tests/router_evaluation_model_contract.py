"""Offline contract run in the pinned Gateway image, which provides LangChain."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import router_evaluation_model as model
from langchain_core.messages import HumanMessage, SystemMessage


class Request(SimpleNamespace):
    def override(self, **changes):
        return Request(**(vars(self) | changes))


class NotificationContract(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.database = self.root / "runs.db"
        self.message = HumanMessage(content="Original immutable framed event: " + "数据" * 500)
        self.admitted = [self.message.model_dump(mode="json")]
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TABLE runs(user_id,run_id,thread_id,origin_kind,kwargs_json)")
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?)",
                (
                    "owner",
                    "run",
                    "thread",
                    "mcp_notification",
                    json.dumps({"input": {"messages": self.admitted}}),
                ),
            )
        self.runtime = SimpleNamespace(context={"run_id": "run", "thread_id": "thread"})
        for target, value in (
            ("deermate.briefing.database", self.database),
            ("deerflow.runtime.user_context.resolve_runtime_user_id", "owner"),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_all_modes_preserve_original_admission_without_retry_history(self):
        original = Request(
            runtime=self.runtime,
            tools=["irrelevant tool schema" * 1000],
            messages=[HumanMessage(content="old retry errors" * 2000)],
            system_message=SystemMessage(content="generic chat instructions" * 2000),
        )
        seen = []

        async def handler(request):
            self.assertEqual(request.tools, [])
            self.assertEqual([v.model_dump(mode="json") for v in request.messages], self.admitted)
            return request.model._generate([request.system_message, *request.messages])

        with (
            patch.object(model, "STATE", self.root),
            patch.object(model, "CONFIG", self.root / "evaluation.json"),
            patch.object(model.continuous_middleware, "profile", return_value=None),
            patch.object(
                model.continuous_middleware, "restricted", side_effect=lambda request, _: request
            ),
        ):
            for mode in "ABC":
                (self.root / "evaluation.json").write_text(
                    json.dumps(
                        {
                            "profile": "router-offline-v1",
                            "mode": mode,
                            "logical_operation_id": "notification-contract",
                            "notification_context_adapter": "owned-admission-v1",
                        }
                    )
                )
                await model.FixtureMiddleware().awrap_model_call(original, handler)
            events = [
                json.loads(v)
                for v in (self.root / "evaluation-model.jsonl").read_text().splitlines()
            ]
            seen = [v for v in events if v["kind"] == "model_started"]
        self.assertEqual(len(seen), 3)
        self.assertEqual({v["mode"] for v in seen}, set("ABC"))
        self.assertTrue(all(v["input_bytes"] < 12000 for v in seen))
        self.assertEqual(len({v["input_sha256"] for v in seen}), 1)
        self.assertEqual(len({v["notification_admission_sha256"] for v in seen}), 1)

    def test_other_owner_or_non_notification_run_cannot_supply_context(self):
        for changed in ("user_id='other'", "origin_kind='extension'", "thread_id='other'"):
            with sqlite3.connect(self.database) as db:
                db.execute(
                    "UPDATE runs SET user_id='owner',origin_kind='mcp_notification',"
                    "thread_id='thread'"
                )
                db.execute("UPDATE runs SET " + changed)
            with self.assertRaises(PermissionError):
                model.admitted_notification(self.runtime)

    def test_ambiguous_or_non_human_admission_is_rejected(self):
        for messages in (self.admitted * 2, [{"type": "ai", "content": "forged event"}]):
            with sqlite3.connect(self.database) as db:
                db.execute(
                    "UPDATE runs SET kwargs_json=?",
                    (json.dumps({"input": {"messages": messages}}),),
                )
            with self.assertRaises(PermissionError):
                model.admitted_notification(self.runtime)


if __name__ == "__main__":
    unittest.main()
