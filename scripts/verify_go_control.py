#!/usr/bin/env python3
"""Verify the local Go cutover using existing evidence; never submit model work."""

import argparse
import json
import secrets
import sys
from datetime import UTC, datetime

import httpx

if __package__:
    from . import local_docker as local
else:
    import local_docker as local


def verify(restart=False):
    account = json.loads((local.STATE / "admin.json").read_text())
    historical = json.loads((local.STATE / "verification.json").read_text())
    checks = []

    def check(name, condition):
        if not condition:
            raise RuntimeError("Go cutover failed: " + name)
        checks.append(name)

    def login(client, email, password):
        return client.post(
            "/api/v1/auth/login/local", data={"username": email, "password": password}
        )

    def mutate(client, method, path, body=None):
        return client.request(
            method, path, json=body, headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")}
        )

    with (
        httpx.Client(base_url=local.URL, trust_env=False, timeout=15) as owner,
        httpx.Client(base_url=local.URL, trust_env=False, timeout=15) as reader,
    ):
        response = login(owner, account["email"], account["password"])
        check(
            "existing_owner_password_accepted_by_go",
            response.status_code == 200 and response.headers.get("X-DeerMate-Backend") == "go",
        )
        me = owner.get("/api/v1/auth/me").json()
        check("opaque_browser_session", len(owner.cookies["access_token"]) == 43)
        thread = "/api/threads/" + historical["thread_id"]
        detail = thread + "/mcp-tasks/" + historical["gateway_task_id"]
        original = owner.get(detail)
        original.raise_for_status()
        check("original_native_task_retained", original.json()["status"] == "completed")
        check(
            "workspace_api_owned_by_go", owner.get("/api/deermate/v1/workspace").status_code == 200
        )
        check("admin_console", owner.get("/admin").status_code == 200)
        preferences = {"X-Expected-User-Id": me["id"]}
        current = owner.get("/api/v1/auth/preferences", headers=preferences)
        current.raise_for_status()
        result = owner.patch(
            "/api/v1/auth/preferences",
            json=current.json(),
            headers={**preferences, "X-CSRF-Token": owner.cookies["csrf_token"]},
        )
        check("existing_preferences_preserved", result.status_code == 204)
        email = "cutover-" + secrets.token_hex(6) + "@example.com"
        password = secrets.token_urlsafe(30)
        created = mutate(
            owner, "POST", "/api/v1/admin/users", {"email": email, "password": password}
        )
        check("admin_creates_user", created.status_code == 201)
        user = created.json()
        path = "/api/v1/admin/users/" + user["id"]
        try:
            check("new_user_login", login(reader, email, password).status_code == 200)
            check("regular_user_admin_denied", reader.get("/api/v1/admin/users").status_code == 403)
            check(
                "regular_user_execution_denied",
                mutate(reader, "POST", "/api/threads", {}).status_code == 403,
            )
            check("cross_owner_thread_hidden", reader.get(thread).status_code in {403, 404})
            check(
                "forged_internal_identity_rejected",
                reader.get(
                    detail, headers={"X-DeerFlow-Internal-Token": "forged", "X-User-Id": me["id"]}
                ).status_code
                in {403, 404},
            )
            check(
                "csrf_rejected",
                owner.patch(
                    path, json={"disabled": True}, headers={"X-CSRF-Token": "wrong"}
                ).status_code
                == 403,
            )
            check(
                "last_admin_retained",
                mutate(
                    owner, "PATCH", "/api/v1/admin/users/" + me["id"], {"disabled": True}
                ).status_code
                == 409,
            )
            check(
                "role_change",
                mutate(owner, "PATCH", path, {"system_role": "admin"}).status_code == 200,
            )
            check("role_change_revokes_session", reader.get("/api/v1/auth/me").status_code == 401)
            check(
                "promoted_user_relogin",
                login(reader, email, password).status_code == 200
                and reader.get("/api/v1/admin/users").status_code == 200,
            )
            mutate(owner, "PATCH", path, {"system_role": "user"}).raise_for_status()
            login(reader, email, password).raise_for_status()
            replacement = secrets.token_urlsafe(30)
            check(
                "admin_password_reset",
                mutate(owner, "POST", path + "/password", {"password": replacement}).status_code
                == 200,
            )
            check(
                "password_reset_revokes_session", reader.get("/api/v1/auth/me").status_code == 401
            )
            check("old_password_invalid", login(reader, email, password).status_code == 401)
            check("new_password_accepted", login(reader, email, replacement).status_code == 200)
            mutate(owner, "PATCH", path, {"disabled": True}).raise_for_status()
            check("suspension_revokes_session", reader.get("/api/v1/auth/me").status_code == 401)
        finally:
            # Keep the audit trail and never leave a verifier-created active principal.
            mutate(
                owner, "PATCH", path, {"disabled": True, "system_role": "user"}
            ).raise_for_status()
        if restart:
            local.compose("restart", "control")
            local.ready()
            check(
                "go_restart_preserves_session",
                owner.get("/api/v1/auth/me").json()["id"] == me["id"],
            )
            check(
                "go_restart_preserves_native_task",
                owner.get(detail).json()["status"] == "completed",
            )
        check("audit_available", owner.get("/api/v1/admin/audit").status_code == 200)
        check("logout", mutate(owner, "POST", "/api/v1/auth/logout", {}).status_code == 200)
        check("logout_revokes_session", owner.get("/api/v1/auth/me").status_code == 401)
    receipt = {
        "passed": True,
        "verified_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "model_tasks_submitted": 0,
        "legacy_task_id": historical["gateway_task_id"],
        "limits": "Local Docker only; ACK deployment and external OAuth/PAT not verified.",
    }
    output = local.STATE / "go-verification.json"
    local.ack.private_write(output, json.dumps(receipt, indent=2) + "\n")
    print(f"Go cutover: {len(checks)} checks passed; no model work submitted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.restart)
    except (httpx.HTTPError, RuntimeError, KeyError) as error:
        print(
            f"Verification failed ({type(error).__name__}); inspect the local profile.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
