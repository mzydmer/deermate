#!/usr/bin/env python3
"""Verify a named synthetic database survives a specific old Go image and restoration."""

import argparse
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

SNAPSHOT = """
import hashlib,json,sqlite3
from pathlib import Path
home=Path('/app/backend/.deer-flow/data')
d=sqlite3.connect('file:'+str(home/'deerflow.db')+'?mode=ro',uri=True)
def hash_rows(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
records=d.execute(
 'SELECT id,kind,state,data FROM deermate_work_records ORDER BY owner,kind,id').fetchall()
v={'work_count':len(records),'work_digest':hash_rows(records),
   'users':hash_rows(d.execute('SELECT id FROM users ORDER BY id').fetchall()),
   'threads':hash_rows(d.execute(
      'SELECT thread_id FROM threads_meta ORDER BY thread_id').fetchall()),
   'tasks':hash_rows(d.execute('SELECT id FROM mcp_tasks ORDER BY id').fetchall()),
   'uncertain':sum(r[1]=='operation' and r[2]=='uncertain' for r in records)}
p=home/'deermate-chat-sessions.sqlite3'
if p.exists():
 j=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
 names=[r[0] for r in j.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
 rows=[(n,j.execute('SELECT * FROM "'+n+'" ORDER BY rowid').fetchall()) for n in names]
 v['native_journal']=hash_rows(rows)
print(json.dumps(v))
"""


def verify(args):
    url = urlsplit(args.url)
    assert url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"} and url.port != 2026
    project = json.loads((args.bundle / "bundle.json").read_text())["project"]
    assert project.startswith("deermate-") and project.endswith(("-check", "-fixture"))
    assert args.previous_image.startswith("deermate.local/")
    subprocess.run(
        ["docker", "image", "inspect", args.previous_image], check=True, stdout=subprocess.DEVNULL
    )
    gateway = project + "-gateway-1"
    owner = json.loads(args.owner_file.read_text())

    def snapshot():
        return json.loads(
            subprocess.check_output(
                ["docker", "exec", gateway, "/app/backend/.venv/bin/python", "-c", SNAPSHOT],
                text=True,
            )
        )

    with httpx.Client(base_url=args.url, trust_env=False, timeout=20) as client:

        def login():
            client.post(
                "/api/v1/auth/login/local",
                data={"username": owner["email"], "password": owner["password"]},
            ).raise_for_status()
            user = client.get("/api/v1/auth/me").json()
            client.headers.update(
                {"X-CSRF-Token": client.cookies["csrf_token"], "X-Expected-User-Id": user["id"]}
            )
            return user["id"]

        identity = login()
        assert [v["name"] for v in client.get("/api/models").json()["models"]] == [
            "continuous-fixture"
        ]
        cfg = client.get("/api/me/continuous-config").json()["config"]
        client.patch(
            "/api/me/continuous-config",
            json={
                "enabled": False,
                "model": "continuous-fixture",
                "native_budget": 0,
                "expected_revision": cfg["revision"],
            },
        ).raise_for_status()
        rejected = client.post(
            "/api/me/router/messages",
            json={"operation_id": "disabled-rollback-probe", "text": "Synthetic disabled probe"},
        )
        assert rejected.status_code == 409
        before = snapshot()
        override = args.output.with_suffix(".override.yaml").resolve()
        override.parent.mkdir(parents=True, exist_ok=True)
        override.write_text(
            yaml.safe_dump({"services": {"control": {"image": args.previous_image}}})
        )

        def switch(old):
            command = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml"]
            if old:
                command.extend(["-f", str(override)])
            command.extend(["up", "-d", "--no-deps", "--wait", "--wait-timeout", "90", "control"])
            subprocess.run(command, cwd=args.bundle, check=True, stdout=subprocess.DEVNULL)
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                try:
                    if client.get("/health/live").status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            raise AssertionError("Go did not return after image switch")

        try:
            switch(True)
            assert login() == identity
            during = snapshot()
            assert during == before, "Old image changed continuous/native identity data"
        finally:
            switch(False)
        assert login() == identity
        after = snapshot()
        assert after == before
        assert client.get("/api/me/continuous-config").json()["config"]["data"]["enabled"] is False
        args.output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "passed": True,
                    "profile": "synthetic-specific-go-image-rollback",
                    "previous_image": args.previous_image,
                    "disabled_rejects_new_input": True,
                    "identity_and_records_preserved": after,
                    "restored_new_image": True,
                    "database_restored_or_overwritten": False,
                    "limits": (
                        "Specific local Go image only; not a cloud/full-stack rollback claim."
                    ),
                },
                indent=2,
            )
            + "\n"
        )
        override.unlink()
        print(
            "Specific old Go image and restoration preserved synthetic records and native journal"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--previous-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    verify(parser.parse_args())
