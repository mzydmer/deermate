import argparse
import asyncio
import json
from pathlib import Path

import httpx

from .bridge import BridgeError, read_token, task_path
from .config import load_settings


async def client_command(args, token_path, *, transport=None, instance_id=None):
    if hasattr(args, "task_id"):
        if ":" in args.task_id:
            instance, _, native = args.task_id.partition(":")
            if instance != instance_id:
                raise BridgeError("Task handle belongs to a different Worker instance.")
            args.task_id = native
        task_path(args.task_id)
    token = await asyncio.to_thread(read_token, token_path)
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{args.port}",
        trust_env=False,
        follow_redirects=False,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
        transport=transport,
    ) as client:
        match args.command:
            case "submit":
                result = await client.post(
                    "/tasks",
                    json={
                        "project_id": args.project,
                        "prompt": args.prompt,
                        "idempotency_key": args.key,
                    },
                )
            case "capabilities":
                result = await client.get("/capabilities")
            case "list":
                result = await client.get("/tasks")
            case "status":
                result = await client.get(f"/tasks/{args.task_id}")
            case "events":
                result = await client.get(
                    f"/tasks/{args.task_id}/events", params={"after": args.after}
                )
            case "diff":
                result = await client.get(f"/tasks/{args.task_id}/diff")
            case "cancel":
                result = await client.post(f"/tasks/{args.task_id}/cancel")
            case "resume":
                result = await client.post(
                    f"/tasks/{args.task_id}/resume",
                    json={
                        "message": args.message,
                        "idempotency_key": args.key,
                        "confirm_recovery": args.confirm_recovery,
                    },
                )
            case "continue":
                result = await client.post(
                    f"/tasks/{args.task_id}/continue",
                    json={"message": args.message, "idempotency_key": args.key},
                )
            case "answer":
                answers = json.loads(await asyncio.to_thread(args.file.read_text))
                result = await client.post(
                    f"/tasks/{args.task_id}/input", json={"answers": answers}
                )
        result.raise_for_status()
        if args.command == "diff":
            print(result.text)
        else:
            payload = result.json()
            if args.command == "capabilities" and args.worker:
                payload["connection"] = {"type": "ssh", "worker_id": args.worker}
            print(json.dumps(payload, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(prog="deermate")
    parser.add_argument("--config", type=Path, default=Path("deermate.toml"))
    parser.add_argument("--port", type=int, default=18777, help="local API port")
    parser.add_argument("--worker", help="enrolled SSH worker ID in a controller config")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run one local-only worker; creates a private API token")
    sub.add_parser("mcp", help="serve stdio MCP tools backed by an independent worker")
    sub.add_parser("capabilities")
    sub.add_parser("doctor", help="check configured Worker connection without executing a task")
    sub.add_parser("list")
    create = sub.add_parser("submit")
    create.add_argument("--project", required=True)
    create.add_argument("--prompt", required=True)
    create.add_argument("--key", required=True, help="stable idempotency key")
    for name in ["status", "events", "diff", "cancel", "resume", "continue", "answer"]:
        command = sub.add_parser(name)
        command.add_argument("task_id")
        if name == "events":
            command.add_argument("--after", type=int, default=0)
        if name in {"resume", "continue"}:
            command.add_argument("--message", required=True)
            command.add_argument("--key", required=True)
        if name == "resume":
            command.add_argument("--confirm-recovery", action="store_true")
        if name == "answer":
            command.add_argument(
                "--file", type=Path, required=True, help='JSON object: {"question-id": ["answer"]}'
            )
    args = parser.parse_args()
    if args.worker and (args.command == "serve" or args.port != 18777):
        parser.error("--worker selects an enrolled client target; serve/--port are local-only")
    try:
        if args.command == "doctor":
            from .preflight import check_worker

            report = asyncio.run(check_worker(args.config, args.port, args.worker))
            print(json.dumps(report, indent=2, ensure_ascii=False))
            parser.exit(0 if report["status"] == "reachable" else 1)
        remote = None
        if args.worker:
            try:
                from .ssh import SSHTransport
            except ImportError as error:
                raise ValueError(
                    "SSH support requires installation with the 'ssh' extra."
                ) from error
            remote = SSHTransport(args.config, args.worker)
            token_path = remote.settings.token_file
        else:
            settings = load_settings(args.config)
            token_path = settings.state_dir / "api.token"
        if args.command == "mcp":
            try:
                from .mcp_server import run_server
            except ImportError as error:
                raise ValueError(
                    "MCP support requires installation with the 'mcp' extra."
                ) from error
            if remote:
                from .ssh import RemoteTaskBridge

                bridge = RemoteTaskBridge(args.config, args.worker, transport=remote)
            else:
                bridge = None
            asyncio.run(run_server(token_path, args.port, bridge=bridge))
            return
        if args.command == "serve":
            import uvicorn

            from .api import create_app

            app = create_app(settings)
            print(f"Local token file: {token_path}", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=args.port)
            return
        asyncio.run(
            client_command(
                args,
                token_path,
                transport=remote,
                instance_id=remote.settings.expected_instance_id if remote else None,
            )
        )
    except (OSError, ValueError, BridgeError, httpx.HTTPError) as error:
        parser.exit(1, f"deermate: {error}\n")


if __name__ == "__main__":
    main()
