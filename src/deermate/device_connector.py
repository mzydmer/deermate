"""Outbound authenticated HTTPS connector; never retries a delivered Worker mutation."""

import argparse
import asyncio
import fcntl
import json
import secrets
import socket
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .authorization import private_json, private_save
from .bridge import read_token
from .config import load_settings

DEFAULT_STATE = Path.home() / ".deermate-device"


def approved_policy(state, grant_id, version):
    candidate = state["approvals"].get(f"{grant_id}:{version}") or state["approvals"].get(grant_id)
    return candidate if candidate and candidate["version"] == version else None


def server_origin(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use an exact trusted HTTPS origin")
    return value.rstrip("/")


def connection(state):
    return httpx.AsyncClient(
        base_url=server_origin(state["server"]),
        headers={"Authorization": "Bearer " + state["token"]},
        timeout=20,
        trust_env=False,
        follow_redirects=False,
    )


async def pair(args):
    settings = load_settings(args.config)
    state_path = args.state / "device.json"
    if state_path.exists():
        state = private_json(state_path)
        if state["server"] != server_origin(args.server):
            raise ValueError("Existing pairing belongs to another server")
    else:
        async with httpx.AsyncClient(trust_env=False, timeout=6) as client:
            response = await client.get(
                "http://127.0.0.1:18777/capabilities",
                headers={"Authorization": "Bearer " + read_token(settings.state_dir / "api.token")},
            )
            response.raise_for_status()
            if response.json().get("authorization_protocol") != "local-grants-v1":
                raise ValueError("Upgrade the local Worker before pairing remote authorizations")
            instance = response.json()["instance_id"]
        state = {
            "server": server_origin(args.server),
            "token": secrets.token_urlsafe(32),
            "device_id": str(uuid.uuid4()),
            "instance_id": instance,
            "config": str(args.config.resolve()),
            "approvals": {},
        }
        private_save(state_path, state)
    body = {
        "pairing_id": args.pairing,
        "code": args.code,
        "device_token": state["token"],
        "device": {
            "id": state["device_id"],
            "name": args.name or socket.gethostname(),
            "instance_id": state["instance_id"],
            "projects": sorted(settings.projects),
        },
    }
    async with connection(state) as client:
        response = await client.post("/api/agent-devices/pair", json=body)
        response.raise_for_status()
    print("Device paired. Select projects and expiry on the page, then confirm locally.")


async def approve(args):
    state = private_json(args.state / "device.json")
    pending = private_json(args.state / "pending.json")
    grant = next(
        (
            g
            for g in pending["grants"]
            if g["id"] == args.grant and g.get("pending") and not g["revoked"]
        ),
        None,
    )
    if not grant:
        raise ValueError("No matching pending grant; run deermate-device connect first")
    policy = grant["pending"]
    print(
        json.dumps(
            {
                "server": state["server"],
                "device": state["device_id"],
                "grant_id": grant["id"],
                "version": grant["pending_version"],
                "policy": policy,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if (
        await asyncio.to_thread(input, "Confirm this exact authorization? Type AUTHORIZE: ")
        != "AUTHORIZE"
    ):
        raise ValueError("Authorization was not confirmed")
    # Persist before acknowledgement: an uncertain reply cannot lose local scope.
    state["approvals"][f"{grant['id']}:{grant['pending_version']}"] = {
        "version": grant["pending_version"],
        "policy": policy,
    }
    private_save(args.state / "device.json", state)
    async with connection(state) as client:
        response = await client.post(
            "/api/agent-devices/confirm",
            json={"grant_id": grant["id"], "version": grant["pending_version"], "policy": policy},
        )
        response.raise_for_status()
    print("Authorization confirmed. The connector will install the active local policy.")


async def process_request(client, local, state, settings, packet):
    job = packet.get("request")
    if not job:
        return
    approved = approved_policy(state, job["grant_id"], job["version"])
    grant = next((g for g in packet["grants"] if g["id"] == job["grant_id"]), None)
    allowed = (
        approved
        and grant
        and not grant["revoked"]
        and approved["version"] == job["version"] == grant["version"]
        and approved["policy"] == grant["active"]
    )
    status, body = 403, {"detail": "Locally confirmed authorization required"}
    if allowed and job["deadline"] > packet["server_time"]:
        capabilities = await local.get(
            "/capabilities",
            headers={"Authorization": "Bearer " + read_token(settings.state_dir / "api.token")},
        )
        identity = capabilities.json() if capabilities.status_code == 200 else {}
        if (
            identity.get("instance_id") != state["instance_id"]
            or identity.get("authorization_protocol") != "local-grants-v1"
        ):
            allowed = False
            status, body = (
                409,
                {
                    "detail": "Worker identity or local authorization protocol unavailable; "
                    "upgrade and recheck"
                },
            )
        operation = (
            "check"
            if job["path"] == "/capabilities"
            else "submit"
            if job["path"] == "/tasks"
            else "continue"
            if job["path"].endswith("/continue")
            else "cancel"
            if job["path"].endswith("/cancel")
            else "status"
        )
        if operation != "check" and operation not in approved["policy"]["operations"]:
            allowed = False
        if (
            operation == "submit"
            and (job.get("body") or {}).get("project_id") not in approved["policy"]["projects"]
        ):
            allowed = False
    if allowed and job["deadline"] > packet["server_time"]:
        # Defense in depth: no arbitrary URL/port/header/command from the server.
        from .relay import operation_path

        if operation_path(job["method"], job["path"]):
            try:
                async with local.stream(
                    job["method"],
                    job["path"],
                    json=job.get("body"),
                    headers={
                        "Authorization": "Bearer " + read_token(settings.state_dir / "api.token"),
                        "X-Deermate-Authorization": grant["id"],
                    },
                ) as response:
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000:
                            raise ValueError("Worker result exceeded limit")
                    status, body = response.status_code, json.loads(raw)
            except (httpx.HTTPError, ValueError):
                status, body = (
                    504,
                    {
                        "detail": "Worker response unavailable; original task outcome unknown. "
                        "No mutation was replayed."
                    },
                )
    # Results may be retried by request ID, Worker operations may not.
    result = await client.post(
        "/api/agent-devices/results", json={"request_id": job["id"], "status": status, "body": body}
    )
    result.raise_for_status()


def install_snapshot(packet, state, settings):
    local_state = {
        "observed_at": time.time(),
        "observed_monotonic": time.monotonic(),
        "server_time": packet["server_time"],
        "grants": {},
    }
    for grant in packet["grants"]:
        approved = approved_policy(state, grant["id"], grant["version"])
        if (
            approved
            and grant["instance_id"] == state["instance_id"]
            and approved["version"] == grant["version"]
            and approved["policy"] == grant["active"]
        ):
            local_state["grants"][grant["id"]] = {
                "policy": approved["policy"],
                "version": approved["version"],
                "revoked": grant["revoked"],
            }
    private_save(settings.state_dir / "remote-authorizations.json", local_state)


async def connect(args):
    path = args.state / "device.json"
    state = private_json(path)
    settings = load_settings(Path(state["config"]))
    lock = (args.state / "connector.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    async with (
        connection(state) as client,
        httpx.AsyncClient(
            base_url="http://127.0.0.1:18777", trust_env=False, timeout=8, follow_redirects=False
        ) as local,
    ):
        continuous_server = False
        while True:
            try:
                state = private_json(path)  # An explicit local approval can arrive while polling.
                worker_status = "unavailable"
                continuous_protocol = ""
                try:
                    response = await local.get(
                        "/capabilities",
                        headers={
                            "Authorization": "Bearer "
                            + read_token(settings.state_dir / "api.token")
                        },
                    )
                    if (
                        response.status_code == 200
                        and response.json()["instance_id"] == state["instance_id"]
                        and response.json().get("authorization_protocol") == "local-grants-v1"
                    ):
                        worker_status = "reachable"
                        if response.json().get("continuous_protocol") == "work-orders-v1":
                            continuous_protocol = "work-orders-v1"
                except (httpx.HTTPError, ValueError, KeyError):
                    pass
                observation = {"worker_status": worker_status}
                if continuous_server:
                    observation["continuous_protocol"] = continuous_protocol
                response = await client.post("/api/agent-devices/poll", json=observation)
                response.raise_for_status()
                packet = response.json()
                continuous_server = packet.get("continuous_protocol") == "work-orders-v1"
                if len(response.content) > 256_000:
                    raise ValueError("Cloud policy exceeded limit")
                install_snapshot(packet, state, settings)
                private_save(args.state / "pending.json", {"grants": packet["grants"]})
                for grant in packet["grants"]:
                    if grant["revoked"] and not grant["device_confirmed"]:
                        ack = await client.post(
                            "/api/agent-devices/confirm",
                            json={
                                "grant_id": grant["id"],
                                "version": grant["version"],
                                "revoked": True,
                            },
                        )
                        ack.raise_for_status()
                await process_request(client, local, state, settings, packet)
            except (httpx.HTTPError, OSError, ValueError, KeyError) as error:
                print(
                    "Connector unavailable: "
                    + type(error).__name__
                    + "; no Worker mutation replayed.",
                    flush=True,
                )
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser(prog="deermate-device")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pair")
    p.add_argument("--server", required=True)
    p.add_argument("--pairing", required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--name")
    p = sub.add_parser("approve")
    p.add_argument("--grant", required=True)
    sub.add_parser("connect")
    args = parser.parse_args()
    try:
        asyncio.run({"pair": pair, "approve": approve, "connect": connect}[args.command](args))
    except (OSError, ValueError, httpx.HTTPError) as error:
        parser.exit(
            1,
            "deermate-device: "
            + type(error).__name__
            + "; inspect local state; no operation automatically replayed.\n",
        )


if __name__ == "__main__":
    main()
