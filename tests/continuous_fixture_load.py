"""Synthetic loader used only after isolated fixture validation."""

import hashlib
import json
import sqlite3
import sys

p = json.load(sys.stdin)
db = sqlite3.connect("/app/backend/.deer-flow/data/deerflow.db", timeout=15)
assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
assert db.execute("SELECT count(*) FROM mcp_tasks").fetchone()[0] == 0
assert db.execute("SELECT count(*) FROM deermate_agent_devices").fetchone()[0] == 0
owner = p["owner"]
table = "deermate_work_fts_" + hashlib.sha256(owner.encode()).hexdigest()[:24]
db.execute(
    "CREATE VIRTUAL TABLE IF NOT EXISTS "
    + table
    + " USING fts5(id UNINDEXED,kind UNINDEXED,title,body,tokenize='trigram')"
)
db.execute("BEGIN IMMEDIATE")
for kind, total in [("work", 1000), ("event", 10000)]:
    for i in range(total):
        identifier = "load-" + kind + "-" + str(i).zfill(5)
        data = {
            "title": "Synthetic " + kind + " " + str(i),
            "preview": "Bounded synthetic reference " + str(i) + " " + "x" * 256,
        }
        if kind == "work":
            data.update(
                goal="Synthetic historical goal",
                stage="closed",
                executor="codex",
                thread_id="load-thread-" + str(i),
                project="demo",
            )
            data["refs"] = [
                {"kind": "event", "id": "load-event-" + str(n).zfill(5), "revision": 1}
                for n in range(2)
            ]
        body = json.dumps(data, separators=(",", ":"))
        db.execute(
            "INSERT OR IGNORE INTO deermate_work_records VALUES(?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                kind,
                owner,
                "",
                "closed" if kind == "work" else "assessed",
                1,
                1,
                1,
                body,
            ),
        )
        db.execute("DELETE FROM " + table + " WHERE id=? AND kind=?", (identifier, kind))
        db.execute(
            "INSERT INTO " + table + " VALUES(?,?,?,?)",
            (identifier, kind, data["title"], data["preview"]),
        )
db.commit()
plans = {
    "list": [
        list(r)
        for r in db.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM deermate_work_records "
            "WHERE owner=? AND kind=? ORDER BY updated DESC,id DESC LIMIT 20",
            (owner, "work"),
        )
    ],
    "fts": [
        list(r)
        for r in db.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM "
            + table
            + " WHERE "
            + table
            + " MATCH ? ORDER BY rowid DESC LIMIT 20",
            ("synthetic",),
        )
    ],
}
print(
    json.dumps(
        {
            "work_records": 1000,
            "event_records": 10000,
            "page_count": db.execute("PRAGMA page_count").fetchone()[0],
            "page_size": db.execute("PRAGMA page_size").fetchone()[0],
            "query_plans": plans,
        }
    )
)
