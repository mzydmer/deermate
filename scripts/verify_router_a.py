"""Non-comparative calibration: real Go -> one async coordinator -> MCP -> Worker."""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import yaml

if __package__:
    from . import prepare_continuous_fixture, single_host
else:
    import prepare_continuous_fixture
    import single_host

ROOT = Path(__file__).resolve().parents[1]
STATE = "/app/backend/.deer-flow"
FIXTURE = STATE + "/continuous-native-fixture"


def command(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def docker_python(gateway, code, data=None):
    return json.loads(
        command(
            ["docker", "exec", "-i", gateway, "/app/backend/.venv/bin/python", "-c", code],
            input=json.dumps(data) if data is not None else "",
        )
    )


def preflight_control(args):
    image = json.loads(command(["docker", "image", "inspect", args.control_image]))[0]
    if (
        image["Id"] != args.control_image_id
        or image["Os"] != "linux"
        or image["Architecture"] != "amd64"
    ):
        raise RuntimeError("Control image identity/platform differs from the prepared fixture")
    helper = command(["docker", "create", "--network=none", image["Id"], "capabilities"])
    try:
        with tempfile.TemporaryDirectory(prefix="deermate-evaluation-image-") as directory:
            binary = Path(directory) / "deermate"
            subprocess.run(["docker", "cp", helper + ":/deermate", str(binary)], check=True)
            build = command([args.go, "version", "-m", str(binary)])
            if not all(
                v in build for v in ["-tags=deermate_evaluation", "GOOS=linux", "GOARCH=amd64"]
            ):
                raise RuntimeError("Image binary does not contain the Linux evaluation build tag")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    finally:
        subprocess.run(["docker", "rm", helper], check=True, stdout=subprocess.DEVNULL)
    capabilities = json.loads(
        command(
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--read-only",
                "--user=1000:1000",
                "--cap-drop=ALL",
                image["Id"],
                "capabilities",
            ],
            timeout=12,
        )
    )
    if "restore-quarantine-v1" not in capabilities["capabilities"]:
        raise RuntimeError("Control image predates the merged capability command")
    return {
        "image_id": image["Id"],
        "binary_sha256": digest,
        "platform": "linux/amd64",
        "test_tag": "deermate_evaluation",
        "container_user": "1000:1000",
        "network": "none",
        "capabilities": capabilities,
    }


PROBE = r"""
import json,sqlite3,time,hashlib
from pathlib import Path
p=Path('/app/backend/.deer-flow')
d=sqlite3.connect('file:'+str(p/'data/deerflow.db')+'?mode=ro',uri=True);d.row_factory=sqlite3.Row
def lines(f):return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []
out={'clock_domain':'linux-monotonic:'+Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
 'clock_ns':time.monotonic_ns(),'native_events':lines(p/'continuous-native-fixture/native/evaluation-events.jsonl'),
 'model_events':lines(p/'evaluation-model.jsonl'),
 'mcp_tasks':[dict(r) for r in d.execute(
  'SELECT id,user_id,thread_id,status,remote_task_id FROM mcp_tasks ORDER BY id')],
 'runs':[dict(r) for r in d.execute('SELECT run_id,thread_id,status FROM runs ORDER BY run_id')]}
w=p/'continuous-native-fixture/state/tasks.sqlite3'
out['worker_tasks']=[]
if w.exists():
 db=sqlite3.connect('file:'+str(w)+'?mode=ro',uri=True)
 for row in db.execute('SELECT data FROM tasks ORDER BY id'):
  task=json.loads(row[0]); task.pop('prompt',None); task.pop('policy',None)
  if task.get('workspace'):
   workspace=Path(task['workspace'])
   task['actual_answer_sha256']=hashlib.sha256((workspace/'answer.py').read_bytes()).hexdigest()
  out['worker_tasks'].append(task)
print(json.dumps(out))
"""


def prepare(args, work, project, key):
    bundle = work / "bundle"
    single_host.prepare(args.images_config.absolute(), bundle, project, args.port)
    prepare_continuous_fixture.prepare(bundle)
    runtime = bundle / "runtime"
    for name in ["continuous_native_fixture.py", "fake_codex.py", "router_evaluation_model.py"]:
        shutil.copyfile(ROOT / "tests" / name, runtime / name)
    cfg = {
        "profile": "router-offline-v1",
        "mode": "A",
        "logical_operation_id": "calibration-a-1101",
        "native_delay_seconds": 12,
        "formal_batch": False,
    }
    (runtime / "evaluation.json").write_text(json.dumps(cfg) + "\n")
    config = yaml.safe_load((runtime / "config.yaml").read_text())
    config["extensions"]["middlewares"] = [
        "router_evaluation_model:FixtureMiddleware"
        if v == "continuous_fixture_model:FixtureMiddleware"
        else v
        for v in config["extensions"]["middlewares"]
    ]
    config["plugins"][0]["use"] = "router_evaluation_model:install"
    config["models"][0]["use"] = "router_evaluation_model:FixtureModel"
    profile = {
        "enabled": True,
        "command": "/app/backend/.venv/bin/python",
        "args": [
            "-m",
            "deermate.cli",
            "--relay-config",
            STATE + "/agent-authorizations/bridge.json",
            "mcp",
        ],
        "task_toolsets": [
            {
                "name": "coding",
                "submit_tool": "submit_task",
                "status_tool": "get_task_status",
                "cancel_tool": "cancel_task",
            },
            {
                "name": "followup",
                "submit_tool": "continue_task",
                "status_tool": "get_continuation_status",
                "cancel_tool": "cancel_continuation_task",
            },
        ],
    }
    config["extensions"]["mcpServers"] = {"deermate": profile}
    (runtime / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    (runtime / "extensions_config.json").write_text(
        json.dumps({"mcpServers": {"deermate": profile}, "skills": {}})
    )
    for path in runtime.iterdir():
        if path.is_file():
            path.chmod(0o644)
    compose = yaml.safe_load((bundle / "compose.yaml").read_text())
    for name in ["frontend", "nginx"]:
        del compose["services"][name]
    compose["networks"] = {
        "default": {"internal": True, "ipam": {"config": [{"subnet": args.subnet}]}}
    }
    control = compose["services"]["control"]
    control["ports"] = [f"127.0.0.1:{args.port}:8080"]
    control["environment"].update(
        {
            "DEERMATE_EVALUATION_MODE": "A",
            "DEERMATE_EVALUATION_KEY": key,
            "DEERMATE_GITHUB_REPOSITORY": "fixture/project",
        }
    )
    compose["services"]["gateway"]["environment"]["DEERMATE_EVALUATION_CONFIG"] = (
        "/etc/deermate/evaluation.json"
    )
    (bundle / "compose.yaml").write_text(yaml.safe_dump(compose, sort_keys=False))
    env = bundle / ".env"
    lines = env.read_text().splitlines()
    env.write_text(
        "\n".join(
            "DEERMATE_CONTROL_IMAGE=" + args.control_image
            if v.startswith("DEERMATE_CONTROL_IMAGE=")
            else v
            for v in lines
        )
        + "\n"
    )
    return bundle, cfg


def native_device(client, gateway, api):
    docker_python(
        gateway,
        r"""
import subprocess,json
from pathlib import Path
p=Path('/app/backend/.deer-flow/continuous-native-fixture.log')
with p.open('w') as out:
 subprocess.Popen(['/app/backend/.venv/bin/python','/etc/deermate/continuous_native_fixture.py'],stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'started':True}))
""",
    )
    deadline = time.monotonic() + 20
    while True:
        descriptor = docker_python(
            gateway,
            "from pathlib import Path;import json;p=Path('"
            + FIXTURE
            + "/descriptor.json');print(p.read_text() if p.exists() else 'null')",
        )
        if descriptor:
            break
        if time.monotonic() > deadline:
            raise RuntimeError("Toy Worker did not become ready")
        time.sleep(0.1)
    pairing = api("POST", "device-pairings", {})
    token = secrets.token_urlsafe(32)
    device = str(uuid.uuid4())
    api(
        "POST",
        "agent-devices/pair",
        {
            "pairing_id": pairing["pairing_id"],
            "code": pairing["code"],
            "device_token": token,
            "device": {
                "id": device,
                "name": "OFFLINE ROUTER CALIBRATION",
                "instance_id": descriptor["instance_id"],
                "projects": ["demo"],
            },
        },
    )
    policy = {
        "projects": ["demo"],
        "operations": ["submit", "status", "continue", "cancel"],
        "duration": "fixed",
        "expires_at": int(time.time()) + 900,
        "expiry_policy": "stop",
    }
    grant = api(
        "POST",
        "agent-authorizations",
        {"device_id": device, "name": "Synthetic toy repository", "policy": policy},
    )
    client.post(
        "/api/agent-devices/confirm",
        headers={"Authorization": "Bearer " + token},
        json={"grant_id": grant["id"], "version": grant["pending_version"], "policy": policy},
    ).raise_for_status()
    docker_python(
        gateway,
        "from pathlib import Path;import json,sys;p=Path('"
        + FIXTURE
        + "/device.json');p.write_text(json.dumps(json.load(sys.stdin)));"
        "p.chmod(0o600);print('true')",
        {
            "token": token,
            "instance_id": descriptor["instance_id"],
            "approvals": {grant["id"]: {"version": grant["pending_version"], "policy": policy}},
        },
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        devices = api("GET", "agent-authorizations")["devices"]
        if any(v["id"] == device and v.get("worker_status") == "reachable" for v in devices):
            return grant
        time.sleep(0.1)
    raise RuntimeError("Synthetic connector did not become ready")


def verify(args):
    os.umask(0o077)
    if args.port == 2026 or not 1024 <= args.port <= 65535:
        raise ValueError("Use a separate unprivileged fixture port")
    preflight = preflight_control(args)
    args.control_image = preflight["image_id"]
    work = args.work_dir.absolute()
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    (work / "image-preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")
    project = "deermate-router-a-" + uuid.uuid4().hex[:8] + "-fixture"
    key = secrets.token_urlsafe(32)
    bundle, cfg = prepare(args, work, project, key)
    gateway = project + "-gateway-1"
    result = {
        "profile": "non-comparative A async calibration",
        "formal_batch": False,
        "passed": False,
    }
    try:
        subprocess.run([str(bundle / "start.sh")], check=True, stdout=subprocess.DEVNULL)
        owner = json.loads((bundle / "owner.json").read_text())
        with httpx.Client(
            base_url=f"http://localhost:{args.port}", trust_env=False, timeout=20
        ) as client:
            client.post("/api/v1/auth/initialize", json=owner).raise_for_status()
            client.post(
                "/api/v1/auth/login/local",
                data={"username": owner["email"], "password": owner["password"]},
            ).raise_for_status()
            uid = client.get("/api/v1/auth/me").json()["id"]
            client.headers.update(
                {
                    "X-CSRF-Token": client.cookies["csrf_token"],
                    "X-Expected-User-Id": uid,
                    "X-DeerMate-Evaluation": key,
                }
            )

            def api(method, path, body=None):
                response = client.request(method, "/api/" + path, json=body)
                if response.is_error:
                    raise RuntimeError(f"Fixture API {method} {path}: {response.status_code}")
                return response.json()

            native_device(client, gateway, api)
            start = api(
                "POST",
                "me/router/messages",
                {
                    "operation_id": "a-start-1101",
                    "text": "EVAL_START " + cfg["logical_operation_id"],
                },
            )
            deadline = time.monotonic() + 30
            observed = []
            while time.monotonic() < deadline:
                probe = docker_python(gateway, PROBE)
                observed.append(
                    {"runner_ns": time.monotonic_ns(), "native_events": len(probe["native_events"])}
                )
                if any(v["kind"] == "native_turn_started" for v in probe["native_events"]):
                    break
                time.sleep(0.02)
            else:
                raise RuntimeError("The actual original native turn did not start")
            runner_send = time.monotonic_ns()
            front = api(
                "POST",
                "me/router/messages",
                {
                    "operation_id": "a-front-1101",
                    "text": "EVAL_FRONT " + cfg["logical_operation_id"],
                },
            )
            first = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                view = api("GET", "me/router")
                item = next(v for v in view["items"] if v["id"] == front["id"])
                if "EVAL_VISIBLE " + cfg["logical_operation_id"] in item["data"].get("reply", ""):
                    first = time.monotonic_ns()
                    break
                time.sleep(0.02)
            if first is None:
                raise RuntimeError("No actual foreground response within its deadline")
            view = api("GET", "me/router")
            if next(v for v in view["items"] if v["id"] == start["id"])["state"] != "settled":
                raise RuntimeError("Original coordinator turn is not released")
            evidence = client.get("/__deermate_evaluation/evidence").json()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                probe = docker_python(gateway, PROBE)
                if probe["worker_tasks"] and all(
                    v["status"] == "completed" for v in probe["worker_tasks"]
                ):
                    break
                time.sleep(0.1)
            timing = next(v for v in evidence["items"] if v["inbox"] == front["id"])
            native = probe["native_events"]
            begun = next(v for v in native if v["kind"] == "native_turn_started")
            finished = next(v for v in native if v["kind"] == "native_turn_finished")
            released = next(v for v in probe["model_events"] if v["kind"] == "coordinator_released")
            assert (
                evidence["clock_domain"]
                == probe["clock_domain"]
                == begun["clock_domain"]
                == finished["clock_domain"]
            )
            assert begun["ns"] < timing["first_visible_ns"] < finished["ns"]
            assert released["ns"] < timing["first_visible_ns"] < finished["ns"]
            assert len(probe["worker_tasks"]) == len(probe["mcp_tasks"]) == 1
            task = probe["worker_tasks"][0]
            assert task["status"] == "completed" and task["result"]["validation"]["exit_code"] == 0
            assert len([v for v in native if v["kind"] == "effect"]) == 1
            assert {v["thread_id"] for v in probe["mcp_tasks"]} == {
                view["session"]["data"]["thread_id"]
            }
            result.update(
                passed=True,
                probe=probe,
                service_evidence=evidence,
                foreground_inbox=front["id"],
                start_inbox=start["id"],
                coordinator_thread=view["session"]["data"]["thread_id"],
                foreground_admission_to_first_ms=(
                    timing["first_visible_ns"] - timing["admitted_ns"]
                )
                / 1e6,
                client_send_to_first_ms=(first - runner_send) / 1e6,
                runner_clock_domain="runner-monotonic",
                native_observation_samples=observed,
                real_provider_calls=0,
                real_native_calls=0,
            )
    except Exception as error:
        result["failure_kind"] = type(error).__name__
        try:
            result["retained_failure_probe"] = docker_python(gateway, PROBE)
        except Exception as probe_error:
            result["failure_probe_error_kind"] = type(probe_error).__name__
        raise
    finally:
        (work / "calibration.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
        subprocess.run(
            ["docker", "compose", "--project-directory", str(bundle), "stop", "--timeout", "60"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "formal_batch": False,
                "foreground_admission_to_first_ms": result.get("foreground_admission_to_first_ms"),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-config", type=Path, required=True)
    parser.add_argument("--control-image", required=True)
    parser.add_argument("--control-image-id", required=True)
    parser.add_argument("--go", default="go")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=22045)
    parser.add_argument("--subnet", default="192.168.240.0/24")
    verify(parser.parse_args())
