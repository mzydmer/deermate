"""Optional durable context lookup at the existing Go/DeerFlow boundary."""

import json
import sqlite3

from . import telemetry


def operation_parent(op):
    if telemetry._provider is None or not op:
        return {}
    try:
        from .briefing import database

        with sqlite3.connect(
            database().resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1
        ) as db:
            row = db.execute(
                "SELECT context FROM deermate_operation_trace WHERE owner=? AND record=?",
                (op["owner"], op["id"]),
            ).fetchone()
            return json.loads(row[0]) if row else {}
    except Exception:
        # Observability lookup must not change the independent authorization path.
        return {}
