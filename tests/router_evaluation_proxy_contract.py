"""Real loopback HTTP/socket contracts in an isolated Linux Gateway image."""

import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from router_evaluation_proxy import ProxyHandler, ProxyState


class ProxyContract(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "data").mkdir()
        self.database = self.root / "data/deerflow.db"
        self.journal = self.root / "data/deermate-chat-sessions.sqlite3"

    def start(self, mode, durable=True):
        with sqlite3.connect(self.database) as db:
            db.executescript("""
                CREATE TABLE deermate_work_records(owner,kind,id,parent,state,data);
                CREATE TABLE runs(run_id,user_id,thread_id,idempotency_key);
                CREATE TABLE mcp_tasks(id,user_id,thread_id,thread_incarnation,
                    run_id,status,remote_task_id);
            """)
            for identifier, message in [
                ("original", "EVAL_START logical"),
                ("wrong", "EVAL_START some-other-goal"),
            ]:
                data = {
                    "kind": "router",
                    "origin": "user",
                    "message": message,
                    "thread_id": "router",
                    "_tool_done": True,
                    "_tool_result": {"id": "native-original"},
                }
                db.execute(
                    "INSERT INTO deermate_work_records VALUES(?,?,?,?,?,?)",
                    (
                        "owner",
                        "operation",
                        identifier,
                        "original-inbox",
                        "dispatching",
                        json.dumps(data),
                    ),
                )
            db.execute(
                "INSERT INTO deermate_work_records VALUES(?,?,?,?,?,?)",
                (
                    "owner",
                    "operation",
                    "native-original",
                    "original-work",
                    "dispatching",
                    json.dumps(
                        {
                            "kind": "execute",
                            "thread_id": "work-thread",
                            "message": "Fix the toy. EVAL_OPERATION=logical",
                        }
                    ),
                ),
            )
        with sqlite3.connect(self.journal) as db:
            db.executescript("""
                CREATE TABLE bindings(scope,user_id,thread_id,incarnation,head,pending,round);
                CREATE TABLE turns(scope,tracking_id,confirmed);
            """)
        owner = self

        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path.endswith("/perform"):
                    self.server.perform_calls += 1
                    op = body["operation_id"]
                    canonical = (
                        "http-run:"
                        + hashlib.sha256(
                            ("owner\0router\0extension:deermate.continuous:" + op).encode()
                        ).hexdigest()
                    )
                    thread = "router" if mode == "A" else "work-thread"
                    task_run = "run-original" if mode == "A" else "continuous:native-original"
                    with sqlite3.connect(owner.database) as db:
                        db.execute("DELETE FROM runs")
                        db.execute(
                            "INSERT INTO runs VALUES(?,?,?,?)",
                            ("run-original", "owner", "router", canonical),
                        )
                        if durable:
                            db.execute("DELETE FROM mcp_tasks")
                            db.execute(
                                "INSERT INTO mcp_tasks VALUES(?,?,?,?,?,?,?)",
                                (
                                    "tracked-original",
                                    "owner",
                                    thread,
                                    "incarnation",
                                    task_run,
                                    "working",
                                    "fixture-instance:original-worker",
                                ),
                            )
                    if durable:
                        with sqlite3.connect(owner.journal) as db:
                            db.execute("DELETE FROM bindings")
                            db.execute("DELETE FROM turns")
                            db.execute(
                                "INSERT INTO bindings VALUES(?,?,?,?,?,?,?)",
                                (
                                    "scope",
                                    "owner",
                                    thread,
                                    "incarnation",
                                    "tracked-original",
                                    None,
                                    1,
                                ),
                            )
                            db.execute(
                                "INSERT INTO turns VALUES(?,?,1)", ("scope", "tracked-original")
                            )
                raw = json.dumps(
                    {"known": True, "accepted": True, "run_id": "run-original", "status": "working"}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        backend = ThreadingHTTPServer(("127.0.0.1", 8001), Backend)
        backend.daemon_threads = True
        backend.perform_calls = 0
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
        proxy.daemon_threads = True
        state = ProxyState(
            self.root, {"mode": mode, "logical_operation_id": "logical"}, max_hold_seconds=0.2
        )
        proxy.fixture_state = state
        for server in [backend, proxy]:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(
                lambda server=server, thread=thread: (
                    server.shutdown(),
                    server.server_close(),
                    thread.join(timeout=2),
                )
            )
        return (
            httpx.Client(
                base_url=f"http://127.0.0.1:{proxy.server_port}", trust_env=False, timeout=5
            ),
            backend,
            state,
        )

    def events(self, state):
        return (
            [json.loads(v) for v in state.log.read_text().splitlines()]
            if state.log.exists()
            else []
        )

    def test_actual_socket_loses_one_coordinator_ack_after_all_three_durable_records(self):
        # Separate fixtures avoid conflating the modes' different task/run association.
        for mode in "ABC":
            with self.subTest(mode=mode):
                case = ProxyContract()
                case.setUp()
                try:
                    client, backend, state = case.start(mode)
                    with client:
                        with self.assertRaises(httpx.RemoteProtocolError):
                            client.post(
                                "/api/plugins/deermate.continuous/actions/perform",
                                json={"operation_id": "original"},
                            )
                        events = case.events(state)
                        proof = next(v for v in events if v["kind"] == "durable_barrier")["proof"]
                        self.assertEqual(proof["original_go_state"], "dispatching")
                        self.assertEqual(proof["chat_head"], "tracked-original")
                        self.assertTrue(proof["chat_turn_confirmed"])
                        self.assertEqual(backend.perform_calls, 1)
                        query = client.post(
                            "/api/plugins/deermate.continuous/actions/query",
                            json={"operation_id": "original"},
                        )
                        self.assertEqual(query.json()["run_id"], "run-original")
                        self.assertEqual(backend.perform_calls, 1)
                        # Explicit test-only second response proves one-shot injection.
                        again = client.post(
                            "/api/plugins/deermate.continuous/actions/perform",
                            json={"operation_id": "original"},
                        )
                        self.assertEqual(again.status_code, 200)
                    events = case.events(state)
                    self.assertEqual(sum(v["kind"] == "durable_barrier" for v in events), 1)
                    self.assertEqual(sum(v["kind"] == "ack_dropped" for v in events), 1)
                    self.assertEqual(
                        next(v for v in events if v["kind"] == "ack_dropped")[
                            "response_bytes_sent_to_go"
                        ],
                        0,
                    )
                finally:
                    case.doCleanups()

    def test_incomplete_durability_forwards_success_without_fabricating_a_drop(self):
        client, backend, state = self.start("C", durable=False)
        with client:
            response = client.post(
                "/api/plugins/deermate.continuous/actions/perform",
                json={"operation_id": "original"},
            )
            self.assertEqual(response.status_code, 200)
        events = self.events(state)
        self.assertEqual(sum(v["kind"] == "barrier_not_reached" for v in events), 1)
        self.assertFalse(any(v["kind"] in {"durable_barrier", "ack_dropped"} for v in events))
        self.assertEqual(backend.perform_calls, 1)

    def test_wrong_original_operation_does_not_arm_fault(self):
        client, _, state = self.start("B")
        with client:
            response = client.post(
                "/api/plugins/deermate.continuous/actions/perform", json={"operation_id": "wrong"}
            )
            self.assertEqual(response.status_code, 200)
        self.assertFalse(state.reserved)
        self.assertFalse(self.events(state))


if __name__ == "__main__":
    unittest.main()
