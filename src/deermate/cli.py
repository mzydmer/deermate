import argparse
import json
from pathlib import Path

import httpx

from .config import load_settings


def main():
    parser = argparse.ArgumentParser(prog="deermate")
    parser.add_argument("--config", type=Path, default=Path("deermate.toml"))
    parser.add_argument("--port", type=int, default=18777)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run one local-only worker; creates a private API token")
    sub.add_parser("capabilities")
    sub.add_parser("list")
    create = sub.add_parser("submit")
    create.add_argument("--project", required=True)
    create.add_argument("--prompt", required=True)
    create.add_argument("--key", required=True, help="stable idempotency key")
    for name in ["status", "events", "diff", "cancel", "resume", "answer"]:
        command = sub.add_parser(name)
        command.add_argument("task_id")
        if name == "events":
            command.add_argument("--after", type=int, default=0)
        if name == "resume":
            command.add_argument("--message", required=True)
            command.add_argument("--key", required=True)
            command.add_argument("--confirm-recovery", action="store_true")
        if name == "answer":
            command.add_argument(
                "--file", type=Path, required=True, help='JSON object: {"question-id": ["answer"]}'
            )
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
        if args.command == "serve":
            import uvicorn

            from .api import create_app

            app = create_app(settings)
            print(f"Local token file: {settings.state_dir / 'api.token'}", flush=True)
            uvicorn.run(app, host="127.0.0.1", port=args.port)
            return
        token = (settings.state_dir / "api.token").read_text().strip()
        with httpx.Client(
            base_url=f"http://127.0.0.1:{args.port}",
            trust_env=False,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        ) as client:
            match args.command:
                case "submit":
                    result = client.post(
                        "/tasks",
                        json={
                            "project_id": args.project,
                            "prompt": args.prompt,
                            "idempotency_key": args.key,
                        },
                    )
                case "capabilities":
                    result = client.get("/capabilities")
                case "list":
                    result = client.get("/tasks")
                case "status":
                    result = client.get(f"/tasks/{args.task_id}")
                case "events":
                    result = client.get(
                        f"/tasks/{args.task_id}/events", params={"after": args.after}
                    )
                case "diff":
                    result = client.get(f"/tasks/{args.task_id}/diff")
                case "cancel":
                    result = client.post(f"/tasks/{args.task_id}/cancel")
                case "resume":
                    result = client.post(
                        f"/tasks/{args.task_id}/resume",
                        json={
                            "message": args.message,
                            "idempotency_key": args.key,
                            "confirm_recovery": args.confirm_recovery,
                        },
                    )
                case "answer":
                    result = client.post(
                        f"/tasks/{args.task_id}/input",
                        json={"answers": json.loads(args.file.read_text())},
                    )
            result.raise_for_status()
            print(
                result.text
                if args.command == "diff"
                else json.dumps(result.json(), indent=2, ensure_ascii=False)
            )
    except (OSError, ValueError, httpx.HTTPError) as error:
        parser.exit(1, f"deermate: {error}\n")


if __name__ == "__main__":
    main()
