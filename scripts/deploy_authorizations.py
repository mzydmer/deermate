#!/usr/bin/env python3
"""Upgrade the existing single-host control/Gateway with pinned local artifacts.

Run on the already-authenticated deployment host. No SSH/key expiry changes.
"""

# Embedded remote programs and Dockerfile lines retain literal protocol formatting.
# ruff: noqa: E501

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def output(argv, **kwargs):
    return subprocess.check_output(argv, text=True, **kwargs).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--legacy-instance", default="")
    args = parser.parse_args()
    assert os.geteuid() == 0, "Use the existing deployment administrator"
    lock = Path("/opt/deermate/deploy.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    manifest_file = args.artifacts / "manifest.json"
    assert hashlib.sha256(manifest_file.read_bytes()).hexdigest() == args.manifest_sha256
    manifest = json.loads(manifest_file.read_text())
    commit = manifest["source_commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    for name in ("deermate-linux", "deermate-0.1.0a1-py3-none-any.whl"):
        assert (
            hashlib.sha256((args.artifacts / name).read_bytes()).hexdigest()
            == manifest["sha256"][name]
        )
    work = Path("/opt/deermate/authorization-" + commit[:12])
    assert not work.exists(), "Reconcile the retained checkpoint before retrying"
    work.mkdir(mode=0o700)
    names = {key: "deermate-single-" + key + "-1" for key in ("gateway", "control", "nginx")}
    original = {
        key: json.loads(output(["docker", "inspect", name]))[0] for key, name in names.items()
    }
    (work / "original-state.json").write_text(
        json.dumps({"images": {k: v["Image"] for k, v in original.items()}})
    )
    assert all(v["State"]["Running"] and not v["State"]["OOMKilled"] for v in original.values())
    labels = original["gateway"]["Config"]["Labels"]
    cwd = Path(labels["com.docker.compose.project.working_dir"])
    project = labels["com.docker.compose.project"]
    assert project == "deermate-single" and cwd.is_relative_to("/opt/deermate")
    files = [Path(x) for x in labels["com.docker.compose.project.config_files"].split(",")]
    assert files and all(p.is_file() and p.is_relative_to("/opt/deermate") for p in files)
    home = Path(
        next(
            m["Source"]
            for m in original["gateway"]["Mounts"]
            if m["Destination"] == "/app/backend/.deer-flow"
        )
    )
    assert home.is_relative_to("/var/lib/docker/volumes")
    nginx_mount = next(
        m for m in original["nginx"]["Mounts"] if m["Destination"] == "/etc/deermate"
    )
    nginx = Path(nginx_mount["Source"]) / "nginx.conf"
    assert nginx.is_file()
    nginx_source = cwd / "runtime" / "nginx.conf"
    assert nginx_source.is_file(), "Preserve the source config used by the next start.sh"
    (work / "original-state.json").write_text(
        json.dumps(
            {
                "images": {k: v["Image"] for k, v in original.items()},
                "compose_files": [str(p) for p in files],
                "cwd": str(cwd),
                "nginx": str(nginx),
                "extensions": str(home / "extensions_config.json"),
            }
        )
    )

    def gateway(code):
        return output(
            ["docker", "exec", names["gateway"], "/app/backend/.venv/bin/python", "-c", code]
        )

    active = """import json,re,sqlite3
d=sqlite3.connect('file:/app/backend/.deer-flow/data/deerflow.db?mode=ro',uri=True)
counts={}
for (n,) in d.execute("SELECT name FROM sqlite_master WHERE type='table'"):
 if re.fullmatch('[a-z_]+',n) and ('run' in n or n=='mcp_tasks'):
  if 'status' in {r[1] for r in d.execute('PRAGMA table_info('+n+')')}:
   counts[n]=d.execute('SELECT count(*) FROM '+n+" WHERE status IN ('pending','running','submitted','working','input_required')").fetchone()[0]
assert counts and sum(counts.values())==0,'Active work: wait before replacing services'
print(json.dumps(counts))"""
    active_counts = json.loads(gateway(active))
    gateway(
        "import sqlite3;a=sqlite3.connect('/app/backend/.deer-flow/data/deerflow.db');b=sqlite3.connect('/tmp/authorization-before.db');a.backup(b);assert b.execute('PRAGMA quick_check').fetchone()[0]=='ok';b.close();a.close()"
    )
    run(
        [
            "docker",
            "cp",
            names["gateway"] + ":/tmp/authorization-before.db",
            str(work / "before.db"),
        ],
        stdout=subprocess.DEVNULL,
    )
    (work / "before.db").chmod(0o600)
    for i, path in enumerate(files):
        shutil.copyfile(path, work / f"compose-{i}-before.yaml")
    shutil.copyfile(nginx, work / "nginx-before.conf")
    shutil.copyfile(nginx_source, work / "nginx-source-before.conf")
    shutil.copyfile(home / "extensions_config.json", work / "extensions-before.json")
    for path in work.iterdir():
        path.chmod(0o600)
    (work / "checkpoint.json").write_text(
        json.dumps(
            {
                "stage": "backed_up",
                "commit": commit,
                "images": {k: v["Image"] for k, v in original.items()},
            }
        )
    )
    images = {}
    for component in ("control", "gateway"):
        context = work / (component + "-image")
        context.mkdir(mode=0o700)
        tag = "deermate.local/" + component + ":authorization-" + commit[:12]
        base_tag = "deermate.local/" + component + ":authorization-base-" + commit[:12]
        run(["docker", "tag", original[component]["Image"], base_tag])
        if component == "control":
            shutil.copyfile(args.artifacts / "deermate-linux", context / "deermate")
            (context / "deermate").chmod(0o755)
            commands = "COPY deermate /deermate\n"
        else:
            shutil.copyfile(
                args.artifacts / "deermate-0.1.0a1-py3-none-any.whl",
                context / "deermate-0.1.0a1-py3-none-any.whl",
            )
            commands = "USER root\nCOPY deermate-0.1.0a1-py3-none-any.whl /tmp/\nRUN uv pip install --python /app/backend/.venv/bin/python --offline --no-deps --reinstall /tmp/deermate-0.1.0a1-py3-none-any.whl\nUSER 1000:1000\n"
        (context / "Dockerfile").write_text(
            "FROM "
            + base_tag
            + "\n"
            + commands
            + "LABEL org.opencontainers.image.revision="
            + commit
            + "\n"
        )
        run(["docker", "build", "--network=none", "--tag", tag, str(context)])
        images[component] = tag
    # Prefetch the exact MCP environment while the old service is still healthy.
    release = home / "agent-authorizations" / "releases" / commit[:12]
    release.mkdir(mode=0o700, parents=True)
    shutil.copyfile(
        args.artifacts / "deermate-0.1.0a1-py3-none-any.whl",
        release / "deermate-0.1.0a1-py3-none-any.whl",
    )
    for path in (home / "agent-authorizations").rglob("*"):
        os.chown(path, 1000, 1000)
    os.chown(home / "agent-authorizations", 1000, 1000)
    package = (
        "deermate[mcp,ssh] @ file:///app/backend/.deer-flow/agent-authorizations/releases/"
        + commit[:12]
        + "/deermate-0.1.0a1-py3-none-any.whl"
    )
    cache = "/app/backend/.deer-flow/deermate-worker/uv-cache"
    mcp_args = [
        "--offline",
        "--from",
        package,
        "--constraints",
        "/app/backend/.deer-flow/deermate-worker/constraints.txt",
        "--with",
        "mcp==1.30.0",
        "--with",
        "asyncssh==2.24.1",
        "deermate",
        "--relay-config",
        "/app/backend/.deer-flow/agent-authorizations/bridge.json",
        "mcp",
    ]
    run(
        [
            "docker",
            "exec",
            "-e",
            "UV_CACHE_DIR=" + cache,
            "-e",
            "UV_PYTHON_DOWNLOADS=never",
            names["gateway"],
            "uvx",
            *mcp_args[:-3],
            "--help",
        ],
        stdout=subprocess.DEVNULL,
    )
    active_counts = json.loads(gateway(active))
    for key, name in names.items():
        assert (
            json.loads(output(["docker", "inspect", name]))[0]["Image"] == original[key]["Image"]
        ), "Concurrent deployment detected"
    edit = (
        "import sys,yaml;v=yaml.safe_load(sys.stdin.read());images="
        + repr(images)
        + ";changed=False\nfor k,t in images.items():\n if 'image' in v.get('services',{}).get(k,{}):v['services'][k]['image']=t;changed=True\nprint(yaml.safe_dump(v,sort_keys=False) if changed else '')"
    )
    changed = []
    for path in files:
        updated = output(
            ["docker", "exec", "-i", names["gateway"], "/app/backend/.venv/bin/python", "-c", edit],
            input=path.read_text(),
        )
        if updated:
            changed.append((path, updated))
    assert changed
    activation = """import copy,json,sys
from pathlib import Path
from deerflow.config.extensions_config import atomic_write_extensions_config,extensions_config_file_lock,extensions_config_write_lock,validate_raw_extensions_config
from deerflow.mcp.lifecycle import LIFECYCLE_KEY,plan_mcp_lifecycle
p=Path('/app/backend/.deer-flow/extensions_config.json')
with extensions_config_write_lock,extensions_config_file_lock(p):
 raw=json.loads(p.read_text());old=copy.deepcopy(raw);entry=raw['mcpServers']['deermate'];entry['command']='uvx';entry['args']=json.loads(sys.argv[1]);entry['env']={'UV_CACHE_DIR':sys.argv[2],'UV_PYTHON_DOWNLOADS':'never'}
 assert entry['enabled'] and len(entry['task_toolsets'])==2
 candidate=validate_raw_extensions_config(raw);raw[LIFECYCLE_KEY]=plan_mcp_lifecycle(old,raw,candidate_config=candidate)
 validate_raw_extensions_config(raw);atomic_write_extensions_config(p,raw)
"""
    seed = home / "agent-authorizations" / "bridge.json"
    if not seed.exists():
        seed.write_text(json.dumps({"grants": [], "owner_id": args.owner_id}))
        seed.chmod(0o600)
        os.chown(seed, 1000, 1000)
    run(
        [
            "docker",
            "exec",
            names["gateway"],
            "/app/backend/.venv/bin/python",
            "-c",
            activation,
            json.dumps(mcp_args),
            cache,
        ]
    )
    before = nginx.read_text()
    if "location = /admin/agents" not in before:
        marker = "        location = /nginx-health {"
        assert before.count(marker) == 1
        nginx.write_text(
            before.replace(
                marker,
                "        location = /admin/agents {\n            proxy_pass http://gateway_upstream;\n            proxy_set_header Host $http_host;\n            proxy_http_version 1.1;\n        }\n\n"
                + marker,
            )
        )
    nginx_source.write_text(nginx.read_text())
    for path, updated in changed:
        path.write_text(updated)
    compose = ["docker", "compose"]
    for path in files:
        compose.extend(["-f", str(path)])
    compose.extend(["-p", project])
    rollback = ["#!/bin/sh", "set -eu"]
    for i, path in enumerate(files):
        rollback.append(
            "cp "
            + shlex.quote(str(work / f"compose-{i}-before.yaml"))
            + " "
            + shlex.quote(str(path))
        )
    rollback.extend(
        [
            "cp "
            + shlex.quote(str(work / "nginx-source-before.conf"))
            + " "
            + shlex.quote(str(nginx_source)),
            "cp "
            + shlex.quote(str(work / "extensions-before.json"))
            + " "
            + shlex.quote(str(home / "extensions_config.json")),
            "cp " + shlex.quote(str(work / "nginx-before.conf")) + " " + shlex.quote(str(nginx)),
            "cd " + shlex.quote(str(cwd)),
            shlex.join(compose + ["up", "-d", "--no-deps", "gateway", "control"]),
            shlex.join(
                [
                    "docker",
                    "exec",
                    names["nginx"],
                    "nginx",
                    "-s",
                    "reload",
                    "-c",
                    "/etc/deermate/nginx.conf",
                ]
            ),
        ]
    )
    (work / "rollback.sh").write_text("\n".join(rollback) + "\n")
    (work / "rollback.sh").chmod(0o700)
    run(compose + ["config", "--quiet"], cwd=cwd)
    run(["docker", "exec", names["nginx"], "nginx", "-t", "-c", "/etc/deermate/nginx.conf"])
    (work / "checkpoint.json").write_text(json.dumps({"stage": "activating", "commit": commit}))
    run(compose + ["up", "-d", "--no-deps", "gateway", "control"], cwd=cwd)
    ready = False
    for _ in range(60):
        result = subprocess.run(
            ["docker", "exec", names["control"], "/deermate", "healthcheck"], capture_output=True
        )
        if result.returncode == 0:
            ready = True
            break
        time.sleep(2)
    assert ready, "Inspect checkpoint and restore recorded images/config if necessary"
    run(
        [
            "docker",
            "exec",
            names["nginx"],
            "nginx",
            "-s",
            "reload",
            "-c",
            "/etc/deermate/nginx.conf",
        ]
    )
    # Import the expired test grant as history, never as an active permission.
    migration = """import json,sqlite3,sys,time,uuid
d=sqlite3.connect('/app/backend/.deer-flow/data/deerflow.db');owner=sys.argv[1];instance=sys.argv[2]
assert d.execute("SELECT count(*) FROM users WHERE id=? AND disabled=0 AND system_role='admin'",(owner,)).fetchone()[0]==1
d.execute("INSERT OR IGNORE INTO deermate_control_meta VALUES('agent-owner',?)",(owner,));assert d.execute("SELECT value FROM deermate_control_meta WHERE key='agent-owner'").fetchone()[0]==owner
if instance:
 did=str(uuid.uuid5(uuid.NAMESPACE_URL,'deermate-legacy-home-device'));gid=str(uuid.uuid5(uuid.NAMESPACE_URL,'deermate-legacy-home-grant'));expiry=1793327396
 device={'id':did,'name':'家里的 Mac（原临时链路）','owner_id':owner,'instance_id':instance,'projects':['demo'],'last_seen_at':0,'worker_status':'unknown','legacy':True}
 policy={'projects':['demo'],'operations':['submit','status','continue','cancel'],'duration':'fixed','expires_at':expiry,'expiry_policy':'finish'}
 grant={'id':gid,'owner_id':owner,'device_id':did,'name':'Codex','instance_id':instance,'version':1,'active':policy,'pending':None,'pending_version':0,'revoked':False,'device_confirmed':False,'updated_at':expiry}
 d.execute('INSERT OR IGNORE INTO deermate_agent_devices VALUES(?,?,?,?)',(did,owner,'disabled-legacy-'+did,json.dumps(device)))
 d.execute('INSERT OR IGNORE INTO deermate_agent_grants VALUES(?,?,?,?)',(gid,owner,did,json.dumps(grant)))
d.commit();assert d.execute('PRAGMA quick_check').fetchone()[0]=='ok'
print(json.dumps({'owner_retained':True,'legacy_imported_as_expired':bool(instance),'grant_count':d.execute('SELECT count(*) FROM deermate_agent_grants').fetchone()[0]}))
"""
    migrated = json.loads(
        output(
            [
                "docker",
                "exec",
                names["gateway"],
                "/app/backend/.venv/bin/python",
                "-c",
                migration,
                args.owner_id,
                args.legacy_instance,
            ]
        )
    )
    current = {
        key: json.loads(output(["docker", "inspect", name]))[0] for key, name in names.items()
    }
    receipt = {
        "source_commit": commit,
        "control_revision": current["control"]["Config"]["Labels"].get(
            "org.opencontainers.image.revision"
        ),
        "gateway_revision": current["gateway"]["Config"]["Labels"].get(
            "org.opencontainers.image.revision"
        ),
        "database_backup_retained": True,
        "same_home_volume": next(
            m["Source"]
            for m in current["gateway"]["Mounts"]
            if m["Destination"] == "/app/backend/.deer-flow"
        )
        == str(home),
        "active_counts_before": active_counts,
        "services_running": all(
            v["State"]["Running"] and not v["State"]["OOMKilled"] for v in current.values()
        ),
        "new_authorizations_activated": 0,
        "migration": migrated,
    }
    assert receipt["control_revision"] == commit == receipt["gateway_revision"]
    assert receipt["same_home_volume"] and receipt["services_running"]
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2))
    (work / "checkpoint.json").write_text(json.dumps({"stage": "ready", "commit": commit}))
    print("AUTHORIZATION_DEPLOYMENT=" + json.dumps(receipt))


if __name__ == "__main__":
    main()
