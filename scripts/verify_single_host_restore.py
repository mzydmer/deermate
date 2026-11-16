"""Exercise cold snapshots and real API restore using isolated synthetic Docker state."""

import argparse
import copy
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import httpx
import yaml

if __package__:
    from . import prepare_continuous_fixture, single_host, single_host_backup
else:
    import prepare_continuous_fixture
    import single_host
    import single_host_backup

ROOT = Path(__file__).resolve().parents[1]
STATE = "/app/backend/.deer-flow"
PROBE = r"""
import hashlib,json,sqlite3
from pathlib import Path
root=Path('/app/backend/.deer-flow')
d=sqlite3.connect('file:'+str(root/'data/deerflow.db')+'?mode=ro',uri=True)
tables={r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def rows(sql):return d.execute(sql).fetchall()
data={
 'users':rows('SELECT id FROM users ORDER BY id'),
 'threads':rows('SELECT thread_id,user_id FROM threads_meta ORDER BY thread_id'),
 'tasks':rows('SELECT id,thread_id,remote_task_id,status FROM mcp_tasks ORDER BY id'),
 'operations':rows("SELECT id,state FROM deermate_work_records WHERE kind='operation' ORDER BY id"),
 'runs':rows('SELECT run_id FROM runs ORDER BY run_id')}
trace=root/'continuous-native-fixture/native/trace.jsonl'
data['native_trace_sha256']=(
    hashlib.sha256(trace.read_bytes()).hexdigest() if trace.exists() else None)
data['native_requests']=len(trace.read_text().splitlines()) if trace.exists() else 0
data['dispatches']=rows(
    'SELECT operation,deliveries FROM continuous_fixture_deliveries ORDER BY operation')
calls=root/'fixture-model-calls.jsonl'
data['model_calls_sha256']=(
    hashlib.sha256(calls.read_bytes()).hexdigest() if calls.exists() else None)
data['model_calls']=len(calls.read_text().splitlines()) if calls.exists() else 0
data['memory_jobs']=rows('SELECT id,status,provider_state FROM deermate_memory_jobs ORDER BY id')
worker=root/'continuous-native-fixture/state/tasks.sqlite3'
if worker.exists():
    w=sqlite3.connect('file:'+str(worker)+'?mode=ro',uri=True)
    fields=('task_id','session_id','turn_id','parent_task_id','status','attempt','workspace','base_commit')
    data['worker_tasks']=[{key:value.get(key) for key in fields} for value in
        (json.loads(row[0]) for row in w.execute('SELECT data FROM tasks ORDER BY id'))]
print(json.dumps(data,sort_keys=True))
"""


def docker_python(container, code, value=None):
    return json.loads(
        single_host_backup.command(
            [
                "docker",
                "exec",
                "--interactive",
                container,
                "/app/backend/.venv/bin/python",
                "-c",
                code,
            ],
            data=json.dumps(value).encode() if value is not None else None,
        )
    )


@contextmanager
def logged_in(origin, owner):
    client = httpx.Client(base_url=origin, trust_env=False, timeout=30)
    response = client.post(
        "/api/v1/auth/login/local",
        data={"username": owner["email"], "password": owner["password"]},
    )
    if response.status_code != 200:
        client.close()
        raise RuntimeError("Synthetic owner login failed")
    client.headers["X-CSRF-Token"] = client.cookies["csrf_token"]
    client.headers["X-Expected-User-Id"] = client.get("/api/v1/auth/me").json()["id"]
    try:
        yield client
    finally:
        client.close()


def network_fixture(bundle, subnets):
    if not subnets:
        return
    path = bundle / "compose.yaml"
    data = yaml.safe_load(path.read_text())
    for name, subnet in zip(("default", "edge"), subnets, strict=True):
        data["networks"][name]["ipam"] = {"config": [{"subnet": subnet}]}
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def memory_source_from_db(db, owner, fact):
    """Expected public source for this fixture's captured inbox at the cold point."""
    db.row_factory = sqlite3.Row
    ref = db.execute(
        "SELECT * FROM deermate_memory_refs WHERE owner=? AND id=? AND status='active'",
        (owner, fact),
    ).fetchone()
    if ref is None:
        raise RuntimeError("Cold point does not contain the active fixture fact")
    source = db.execute(
        "SELECT * FROM deermate_memory_sources WHERE owner=? AND operation_id=?",
        (owner, ref["source_id"]),
    ).fetchone()
    if source is None or not source["run_id"].startswith("inbox:") or source["invalidated_at"]:
        raise RuntimeError("The fixture requires an actual available inbox source")
    inbox = db.execute(
        "SELECT data FROM deermate_work_records WHERE owner=? AND kind='inbox' AND id=?",
        (owner, source["message_id"]),
    ).fetchone()
    data = json.loads(inbox["data"]) if inbox else {}
    text = data.get("text", "")
    if (
        data.get("origin") != "user"
        or not data.get("_memory_eligible")
        or data.get("_memory_thread") != source["thread_id"]
        or source["run_id"] != "inbox:" + source["message_id"]
        or hashlib.sha256(text.encode()).hexdigest() != source["message_hash"]
    ):
        raise RuntimeError("Cold-point source text or its owner/thread/message binding changed")
    uses = []
    for row in db.execute(
        "SELECT u.thread_id,u.last_used,t.incarnation,t.project_id,t.display_name,t.metadata_json "
        "FROM deermate_memory_usage u JOIN threads_meta t "
        "ON t.thread_id=u.thread_id AND t.user_id=u.owner "
        "WHERE u.owner=? AND u.fact_id=? ORDER BY u.last_used DESC LIMIT 10",
        (owner, fact),
    ):
        metadata = json.loads(row["metadata_json"] or "{}")
        if row["incarnation"] and not row["project_id"] and not metadata.get("deerflow_archived"):
            uses.append(
                {
                    "thread_id": row["thread_id"],
                    "title": metadata.get("title") or row["display_name"] or "",
                    "included_at": row["last_used"],
                }
            )
    return {
        "fact_id": fact,
        "scope": ref["scope"],
        "expires_at": ref["expires_at"],
        "updated_at": ref["updated_at"],
        "kind": "inbox",
        "state": "available",
        "text": text,
        "thread_id": source["thread_id"],
        "message_id": source["message_id"],
        "observed_at": source["observed_at"],
        "uses": uses,
    }


def snapshot_memory_source(snapshot, owner, fact):
    # Read the verified, closed database from the frozen archive, not the live
    # source or an API sample collected before the final common stopping point.
    with tempfile.TemporaryDirectory(prefix="deermate-source-proof-") as directory:
        path = Path(directory) / "deerflow.db"
        with single_host_backup.validated_snapshot(snapshot) as (archive, _, _):
            for suffix in ("", "-wal", "-shm", "-journal"):
                name = "home/data/deerflow.db" + suffix
                try:
                    member = archive.getmember(name)
                except KeyError:
                    if not suffix:
                        raise
                    continue
                Path(str(path) + suffix).write_bytes(archive.extractfile(member).read())
        with sqlite3.connect(path) as db:
            return memory_source_from_db(db, owner, fact)


def actual_invalid_archives(snapshot, work, project, port):
    checks = []
    for index, failure in enumerate(("missing", "checksum", "mode", "duplicate", "link", "escape")):
        damaged = work / ("invalid-" + failure + ".tar.gz")
        with tarfile.open(snapshot, "r:gz") as source, tarfile.open(damaged, "w:gz") as target:
            for entry in source:
                member = copy.copy(entry)
                if failure == "missing" and member.name == "bundle/runtime.env":
                    continue
                content = source.extractfile(entry)
                selected = member.name == "home/data/deerflow.db"
                if selected:
                    if failure == "checksum":
                        blob = content.read()
                        content = io.BytesIO(bytes([blob[0] ^ 1]) + blob[1:])
                    elif failure == "mode":
                        member.mode ^= 0o001
                    elif failure == "link":
                        member.type, member.linkname, member.size = tarfile.SYMTYPE, "/outside", 0
                        content = None
                    elif failure == "escape":
                        member.name = "../outside"
                target.addfile(member, content)
                if selected and failure == "duplicate":
                    target.addfile(member, source.extractfile(entry))
        candidate = project + "-bad" + str(index)
        volume = candidate + "-restored-home"
        output = work / ("never-created-" + failure)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/single_host_backup.py"),
                "restore",
                "--snapshot",
                str(damaged),
                "--output",
                str(output),
                "--project",
                candidate,
                "--port",
                str(port),
            ],
            capture_output=True,
        )
        volumes = (
            single_host_backup.command(
                [
                    "docker",
                    "volume",
                    "ls",
                    "--format",
                    "{{.Name}}",
                    "--filter",
                    f"name=^{volume}$",
                ]
            )
            .decode()
            .splitlines()
        )
        passed = result.returncode == 1 and not output.exists() and not volumes
        checks.append(
            {
                "failure": failure,
                "exit_code": result.returncode,
                "target_bundle_exists": output.exists(),
                "target_volume_exists": bool(volumes),
                "passed": passed,
            }
        )
        if not passed:
            raise RuntimeError("Invalid archive reached target: " + failure)
    return checks


def verify(args):
    os.umask(0o077)
    work = args.work_dir.resolve()
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    source, target = work / "source", work / "restored"
    suffix = uuid.uuid4().hex[:8]
    source_project = "deermate-restore-" + suffix + "-fixture"
    target_project = "deermate-recovered-" + suffix + "-fixture"
    checks = []
    memory_deliveries = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise RuntimeError("Restore acceptance failed: " + name)

    single_host.prepare(args.images_config.resolve(), source, source_project, args.port)
    if args.gateway_test_image:
        env = source / ".env"
        lines = env.read_text().splitlines()
        assert sum(line.startswith("DEERMATE_GATEWAY_IMAGE=") for line in lines) == 1
        env.write_text(
            "\n".join(
                "DEERMATE_GATEWAY_IMAGE=" + args.gateway_test_image
                if line.startswith("DEERMATE_GATEWAY_IMAGE=")
                else line
                for line in lines
            )
            + "\n"
        )
    prepare_continuous_fixture.prepare(source)
    network_fixture(source, args.source_subnets)
    started = []
    try:
        started.append(source)
        subprocess.run([str(source / "start.sh")], check=True, stdout=subprocess.DEVNULL)
        base = f"http://localhost:{args.port}"
        owner_path = source / "owner.json"
        for script, extra in [
            ("verify_continuous.py", []),
            ("verify_continuous_native.py", ["--bundle", str(source)]),
        ]:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / script),
                    "--url",
                    base,
                    "--owner-file",
                    str(owner_path),
                    "--output",
                    str(work / (script + ".json")),
                    *extra,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        owner = json.loads(owner_path.read_text())
        original = source_project + "-gateway-1"
        native = json.loads((work / "verify_continuous_native.py.json").read_text())
        check(
            "actual_driver_native_two_rounds_same_root",
            native["passed"] and native["native_roots"] == 1,
        )
        with logged_in(base, owner) as client:
            uid = client.get("/api/v1/auth/me").json()["id"]
            profile = client.get("/api/me/personal-profile").json()
            response = client.patch(
                "/api/me/personal-profile",
                json={
                    "auto_capture_enabled": True,
                    "expected_revision": profile["revision"],
                },
            )
            check("synthetic_capture_enabled_for_actual_source", response.status_code == 200)

            def api(method, path, body=None, status=200):
                r = client.request(method, "/api/" + path, json=body)
                if r.status_code != status:
                    raise RuntimeError(f"Synthetic fixture API {method} {path}: {r.status_code}")
                return r.json()

            def delivery(method, path, body):
                started_delivery = time.monotonic()
                operation = api(method, path, body, 202)
                initial_status = operation["status"]
                deadline = time.monotonic() + 30
                while (
                    operation["status"] in {"pending", "processing"} and time.monotonic() < deadline
                ):
                    time.sleep(0.2)
                    operation = api("GET", "me/memory-operations/" + operation["id"])
                memory_deliveries.append(
                    {
                        "id": operation["id"],
                        "kind": method,
                        "initial_status": initial_status,
                        "final_status": operation["status"],
                        "seconds": round(time.monotonic() - started_delivery, 3),
                    }
                )
                (work / "memory-deliveries.json").write_text(
                    json.dumps(memory_deliveries, indent=2) + "\n"
                )
                check("memory_delivery_completed", operation["status"] == "completed")
                return operation

            capture_started = time.monotonic()
            source_text = "请记住：我偏好青竹色界面"
            source_inbox = api(
                "POST",
                "me/router/messages",
                {"operation_id": "restore-source-" + suffix, "text": source_text},
            )
            valid = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                view = api("POST", "me/memories/search", {"query": "青竹", "offset": 0})
                references = [v for v in view["references"] if v["status"] == "active"]
                if len(view["items"]) == 1 and len(references) == 1:
                    valid = api("GET", "me/memory-operations/" + references[0]["source_id"])
                    if valid["status"] == "completed":
                        break
                time.sleep(0.2)
            check(
                "actual_inbox_memory_delivery_completed", valid and valid["status"] == "completed"
            )
            memory_deliveries.append(
                {
                    "id": valid["id"],
                    "kind": "INBOX",
                    "initial_status": "accepted_inbox",
                    "final_status": valid["status"],
                    "seconds": round(time.monotonic() - capture_started, 3),
                }
            )
            early_source = api("GET", "me/memories/" + valid["fact_id"] + "/source")
            (work / "early-source-api.json").write_text(json.dumps(early_source, indent=2) + "\n")
            check(
                "actual_source_full_text_and_inbox_binding",
                early_source.get("kind") == "inbox"
                and early_source.get("text") == source_text
                and early_source.get("message_id") == source_inbox["id"],
            )
            profile = api("GET", "me/personal-profile")
            api(
                "PATCH",
                "me/personal-profile",
                {"auto_capture_enabled": False, "expected_revision": profile["revision"]},
            )
            forgotten = delivery(
                "POST",
                "me/memories",
                {
                    "operation_id": "restore-forgotten-" + suffix,
                    "category": "context",
                    "content": "合成恢复反例：旧临时暗号雪松",
                    "expected_revision": 0,
                },
            )
            delivery(
                "DELETE",
                "me/memories/" + forgotten["fact_id"],
                {
                    "operation_id": "restore-forget-" + suffix,
                    "expected_revision": 1,
                },
            )
            check(
                "forgotten_before_snapshot_not_recalled",
                api(
                    "POST",
                    "me/memories/search",
                    {"query": "雪松", "offset": 0},
                )["items"]
                == [],
            )
            baseline_memory = api("POST", "me/memories/search", {"query": "青竹", "offset": 0})[
                "items"
            ]
            check("valid_source_readable_before_snapshot", len(baseline_memory) == 1)
            original_worker = docker_python(original, PROBE)["worker_tasks"]
            native_roots = {v["session_id"] for v in original_worker if v["session_id"]}
            native_work = None
            for work_order in api("GET", "me/work-orders")["items"]:
                if not work_order["data"].get("head"):
                    continue
                timeline = api("GET", "me/work-orders/" + work_order["id"] + "/timeline")
                roots = {
                    v["data"].get("native_session")
                    for v in timeline["items"]
                    if v["kind"] == "operation" and v["data"].get("native_session")
                }
                if roots == native_roots:
                    native_work = work_order
                    break
            check("actual_worker_root_matches_public_api", native_work is not None)
            check("native_root_readable_before_snapshot", len(native_roots) == 1)
            # A separate read-status-only synthetic authorization is active at
            # the snapshot, then revoked after it. No native work is admitted.
            devices = api("GET", "agent-authorizations")["devices"]
            policy = {
                "projects": ["demo"],
                "operations": ["status"],
                "duration": "fixed",
                "expires_at": int(time.time()) + 900,
                "expiry_policy": "stop",
            }
            review_grant = api(
                "POST",
                "agent-authorizations",
                {
                    "device_id": devices[0]["id"],
                    "name": "SYNTHETIC post-point revocation",
                    "policy": policy,
                },
                201,
            )
            confirmation = docker_python(
                original,
                r"""
import json,httpx,sys
from pathlib import Path
p=json.load(sys.stdin)
device=json.loads(Path('/app/backend/.deer-flow/continuous-native-fixture/device.json').read_text())
reply=httpx.post('http://control:8080/api/agent-devices/confirm',
    headers={'Authorization':'Bearer '+device['token']},json=p,trust_env=False,timeout=20)
reply.raise_for_status();print(json.dumps({'confirmed':True}))
""",
                {
                    "grant_id": review_grant["id"],
                    "version": review_grant["pending_version"],
                    "policy": policy,
                },
            )
            check("synthetic_status_grant_confirmed_before_point", confirmation["confirmed"])
            grant_version = review_grant["pending_version"]

        # Exercise automatic ingress closure, common cold point and resumption once.
        warm = work / "normal.tar.gz"
        # Scripted notification runs can still be finalizing; they are explicitly
        # inventoried, retained and acknowledged rather than discarded or retried.
        single_host_backup.backup(source, warm, acknowledge_inflight=True)
        check(
            "cold_backup_automatically_resumed_original",
            bool(
                single_host_backup.compose(
                    source, "ps", "--status", "running", "--quiet", "control"
                )
            ),
        )
        # Inject one explicitly synthetic uncertain operation after stopping all writers.
        single_host_backup.compose(
            source, "stop", "--timeout", "60", "nginx", "frontend", "control"
        )
        unknown = str(uuid.uuid4())
        injected = docker_python(
            original,
            r"""
import json,sqlite3,sys
p=json.load(sys.stdin)
d=sqlite3.connect('/app/backend/.deer-flow/data/deerflow.db');d.row_factory=sqlite3.Row
query=("SELECT * FROM deermate_work_records WHERE owner=? AND parent=? AND kind='operation' "
       "AND json_extract(data,'$.native_session') IS NOT NULL LIMIT 1")
row=dict(d.execute(query,(p['owner'],p['work'])).fetchone())
row['id']=p['id'];row['state']='uncertain'
query=('INSERT INTO deermate_work_records('+','.join(row)+') VALUES('
       +','.join('?' for _ in row)+')')
d.execute(query,tuple(row.values()))
d.commit();print(json.dumps({'inserted':True}))
""",
            {"owner": uid, "id": unknown, "work": native_work["id"]},
        )
        check("synthetic_unknown_record_created", injected["inserted"])
        before = docker_python(original, PROBE)
        single_host_backup.compose(source, "stop", "--timeout", "60", "gateway")
        refused = work / "must-not-publish.tar.gz"
        try:
            single_host_backup.backup(source, refused)
        except single_host_backup.SnapshotError:
            pass
        else:
            raise RuntimeError("Unknown operation was not acknowledged")
        check("unacknowledged_unknown_does_not_publish_snapshot", not refused.exists())
        snapshot = work / "state.tar.gz"
        exported = single_host_backup.backup(source, snapshot, acknowledge_inflight=True)
        verified = single_host_backup.verify_snapshot(snapshot)
        baseline_source = snapshot_memory_source(snapshot, uid, valid["fact_id"])
        (work / "cold-point-source.json").write_text(json.dumps(baseline_source, indent=2) + "\n")
        check(
            "cold_point_preserves_actual_source_text_and_binding",
            baseline_source["text"] == source_text
            and baseline_source["message_id"] == source_inbox["id"]
            and baseline_source["thread_id"] == early_source["thread_id"],
        )
        check(
            "snapshot_retains_original_unknown_id",
            {"id": unknown, "state": "uncertain"} in verified["inflight_inventory"]["operations"],
        )
        forget_after_point = {
            "operation_id": "restore-postpoint-forget-" + suffix,
            "expected_revision": 1,
        }
        source_services = yaml.safe_load((source / "compose.yaml").read_text())
        source_services = single_host_backup.configure_quarantine(source, source_services)
        (source / "compose.yaml").write_text(yaml.safe_dump(source_services, sort_keys=False))
        subprocess.run([str(source / "start.sh")], check=True, stdout=subprocess.DEVNULL)
        with logged_in(base, owner) as review:
            check(
                "source_post_point_changes_keep_quarantine",
                review.get("/health/ready").headers.get("X-DeerMate-Restore-Quarantine") == "true",
            )
            frozen_source = review.get("/api/me/memories/" + valid["fact_id"] + "/source")
            (work / "frozen-source-api.json").write_text(
                json.dumps(
                    {"status": frozen_source.status_code, "source": frozen_source.json()}, indent=2
                )
                + "\n"
            )
            check(
                "source_api_matches_archived_cold_point",
                frozen_source.status_code == 200 and frozen_source.json() == baseline_source,
            )
            deletion = review.request(
                "DELETE", "/api/me/memories/" + valid["fact_id"], json=forget_after_point
            )
            check(
                "actual_source_forgetting_after_snapshot",
                deletion.status_code == 202 and deletion.json()["status"] == "completed",
            )
            revoked = review.post(
                "/api/agent-authorizations/" + review_grant["id"] + "/revocations",
                json={"expected_version": grant_version},
            )
            check(
                "actual_source_revocation_after_snapshot",
                revoked.status_code == 202 and revoked.json()["revoked"],
            )
            post_point_changes_at = time.time_ns()
        source_after_safety = docker_python(original, PROBE)
        check("source_safety_maintenance_did_not_dispatch", source_after_safety == before)
        invalid_archives = actual_invalid_archives(
            snapshot, work, target_project, args.restore_port
        )
        check("actual_bad_archives_leave_no_target", all(v["passed"] for v in invalid_archives))
        # Only this newly created fixture project is removed; its named home
        # remains intact and frees the temporary test network resources.
        single_host_backup.compose(source, "down")
        restore_started = time.monotonic()
        receipt = single_host_backup.restore(snapshot, target, target_project, args.restore_port)
        network_fixture(target, args.restore_subnets)
        started.append(target)
        subprocess.run([str(target / "start.sh")], check=True, stdout=subprocess.DEVNULL)
        ready_seconds = time.monotonic() - restore_started
        restored = target_project + "-gateway-1"
        after = docker_python(restored, PROBE)
        check("owner_thread_task_operation_and_native_identity_preserved", before == after)
        check(
            "counters_were_active_before_restore",
            before["model_calls"] > 0 and before["native_requests"] > 0,
        )
        with logged_in(f"http://localhost:{args.restore_port}", owner) as client:
            check("same_owner_logs_in", client.get("/api/v1/auth/me").json()["id"] == uid)
            headers = client.get("/health/ready").headers
            check("quarantine_is_active", headers.get("X-DeerMate-Restore-Quarantine") == "true")
            memories = client.post("/api/me/memories/search", json={"query": "青竹", "offset": 0})
            check(
                "valid_memory_fts5_restored",
                memories.status_code == 200 and len(memories.json()["items"]) == 1,
            )
            lost = client.post("/api/me/memories/search", json={"query": "雪松", "offset": 0})
            check(
                "pre_snapshot_forgotten_fact_stays_unrecallable",
                lost.status_code == 200 and lost.json()["items"] == [],
            )
            source_reply = client.get("/api/me/memories/" + valid["fact_id"] + "/source")
            (work / "restored-source-api.json").write_text(
                json.dumps(
                    {"status": source_reply.status_code, "source": source_reply.json()}, indent=2
                )
                + "\n"
            )
            check(
                "same_memory_source_restored",
                source_reply.status_code == 200 and source_reply.json() == baseline_source,
            )
            work_orders = client.get("/api/me/work-orders").json()["items"]
            check(
                "actual_work_and_task_links_readable",
                any(w["data"].get("head") for w in work_orders),
            )
            timeline = client.get("/api/me/work-orders/" + native_work["id"] + "/timeline")
            timeline.raise_for_status()
            operations = [v for v in timeline.json()["items"] if v["kind"] == "operation"]
            check(
                "same_native_root_readable_through_actual_api",
                {
                    v["data"].get("native_session")
                    for v in operations
                    if v["data"].get("native_session")
                }
                == native_roots,
            )
            check(
                "unknown_operation_readable_through_actual_api",
                any(v["id"] == unknown and v["state"] == "uncertain" for v in operations),
            )
            csrf = client.headers["X-CSRF-Token"]
            client.headers["X-CSRF-Token"] = "invalid-fixture-csrf"
            denied = client.post("/api/me/memories/search", json={"query": "青竹"})
            check("quarantine_search_preserves_csrf", denied.status_code == 403)
            client.headers["X-CSRF-Token"] = csrf
            grants = client.get("/api/agent-authorizations").json()["grants"]
            restored_grant = next(
                v["grant"] for v in grants if v["grant"]["id"] == review_grant["id"]
            )
            check("snapshot_precedes_actual_later_revocation", not restored_grant["revoked"])
            forgotten_again = client.request(
                "DELETE", "/api/me/memories/" + valid["fact_id"], json=forget_after_point
            )
            check(
                "post_point_forgetting_reapplied_while_frozen",
                forgotten_again.status_code == 202
                and forgotten_again.json()["status"] == "completed",
            )
            recall = client.post("/api/me/memories/search", json={"query": "青竹", "offset": 0})
            check(
                "post_point_fact_unrecallable_before_reopening",
                recall.status_code == 200 and recall.json()["items"] == [],
            )
            revoked_again = client.post(
                "/api/agent-authorizations/" + review_grant["id"] + "/revocations",
                json={"expected_version": grant_version},
            )
            check(
                "post_point_revocation_reapplied_while_frozen",
                revoked_again.status_code == 202 and revoked_again.json()["revoked"],
            )
            for route in ("/api/me/router/messages", "/api/agent-devices/poll", "/api/threads"):
                r = client.post(
                    route,
                    json={"operation_id": str(uuid.uuid4()), "text": "blocked synthetic request"},
                )
                check("dispatch_blocked_" + route.rsplit("/", 1)[-1], r.status_code == 503)
        time.sleep(4)  # More than the ordinary queue tick; no provider/native operation may appear.
        final = docker_python(restored, PROBE)
        check("zero_restored_native_or_provider_dispatches", final == after)
        source_volume = verified["source_home_volume"]
        check(
            "original_home_volume_still_exists",
            bool(single_host_backup.command(["docker", "volume", "inspect", source_volume])),
        )
        result = {
            "schema_version": 1,
            "passed": True,
            "profile": "synthetic Docker cold restore; real Go/Gateway/Worker APIs",
            "snapshot_id": verified["snapshot_id"],
            "recovery_point": verified["recovery_point"],
            "archive_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "restore_preparation_seconds": receipt["restored_seconds"],
            "archive_export_seconds": exported["archive_export_seconds"],
            "archive_validation_seconds": receipt["archive_validation_seconds"],
            "archive_copy_seconds": receipt["archive_copy_seconds"],
            "restore_to_ready_seconds": round(ready_seconds, 3),
            "invalid_archive_probes": invalid_archives,
            "post_snapshot_safety_changes": {
                "applied_at_ns": post_point_changes_at,
                "fact_id": valid["fact_id"],
                "deletion_operation": forget_after_point,
                "grant_id": review_grant["id"],
                "grant_version": grant_version,
                "reapplied_while_dispatch_frozen": True,
            },
            "memory_delivery_records": memory_deliveries,
            "memory_source": {
                "kind": "actual_captured_inbox",
                "expectation": "verified archive at common cold point",
                "full_object_matches": True,
                "text_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
                "message_id": source_inbox["id"],
                "thread_id": baseline_source["thread_id"],
                "uses_at_cold_point": len(baseline_source["uses"]),
            },
            "dispatch_counters_before_restore": before,
            "dispatch_counters_after_restore": final,
            "checks": checks,
            "real_provider_calls": 0,
            "real_native_calls": 0,
            "restored_dispatches": 0,
            "protocol_native_roots_before_restore": 1,
            "limits": (
                "Local synthetic data/keys and scripted native protocol; "
                "no cloud loss or real device reconciliation; private backup is not published."
            ),
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "passed": True,
                    "checks": len(checks),
                    "restore_to_ready_seconds": round(ready_seconds, 3),
                }
            )
        )
    finally:
        for bundle in reversed(started):
            single_host_backup.compose(bundle, "stop", "--timeout", "60")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-config", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--port", type=int, default=22043)
    parser.add_argument("--restore-port", type=int, default=22044)
    parser.add_argument("--gateway-test-image", help="Test-only Gateway with Git for toy Worker")
    parser.add_argument(
        "--source-subnets",
        nargs=2,
        metavar=("APP", "INGRESS"),
        help="Optional fixture-only unused Docker subnets",
    )
    parser.add_argument(
        "--restore-subnets",
        nargs=2,
        metavar=("APP", "INGRESS"),
        help="Optional fixture-only unused Docker subnets",
    )
    verify(parser.parse_args())
