#!/usr/bin/env python3
"""Read-only deployed authorization acceptance using an existing owner account.

Creates a normal login session, never pairs a device or activates a grant.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--owner-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parsed = urlsplit(args.origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.path:
        raise ValueError("Use the configured HTTPS origin")
    owner = json.loads(args.owner_file.read_text())
    checks = []

    def check(name, passed):
        if not passed:
            raise RuntimeError("Authorization deployment check failed: " + name)
        checks.append(name)

    with httpx.Client(base_url=args.origin, trust_env=False, timeout=20) as client:
        check("public_health", client.get("/health/ready").status_code == 200)
        check(
            "anonymous_inventory_rejected",
            client.get("/api/agent-authorizations").status_code == 401,
        )
        response = client.post(
            "/api/v1/auth/login/local",
            data={"username": owner["email"], "password": owner["password"]},
        )
        check("existing_owner_login", response.status_code == 200)
        before = client.get("/api/agent-authorizations")
        check("owner_inventory", before.status_code == 200)
        inventory = before.json()
        check(
            "expired_history_imported", any(g["status"] == "expired" for g in inventory["grants"])
        )
        check(
            "no_new_active_grants",
            not any(g["status"] in {"active", "expiring"} for g in inventory["grants"]),
        )
        check(
            "native_readiness_not_invented",
            all(g["execution_readiness"] == "not_checked" for g in inventory["grants"]),
        )
        check(
            "no_private_credentials_in_projection",
            "PRIVATE KEY" not in before.text
            and '"token"' not in before.text
            and '"secret"' not in before.text,
        )
        page = client.get("/admin/agents")
        check(
            "management_page_served",
            page.status_code == 200
            and "Agent 授权" in page.text
            and "DEERMATE_DESIGN_TOKENS" not in page.text,
        )
        check(
            "page_security_headers",
            "frame-ancestors 'none'" in page.headers.get("content-security-policy", ""),
        )
        check("admin_navigation", "/admin/agents" in client.get("/admin").text)
        denied = client.post("/api/device-pairings", json={})
        check("session_bound_csrf_required", denied.status_code == 403)
        csrf = client.cookies.get("csrf_token")
        for view in inventory["grants"]:
            grant = view["grant"]
            response = client.post(
                "/api/agent-authorizations/" + grant["id"] + "/checks",
                json={},
                headers={"X-CSRF-Token": csrf, "Origin": args.origin},
            )
            check("readonly_connection_check", response.status_code == 200)
            check("expired_reason_visible", response.json()["connection"] == "grant_expired")
            check("original_deadline_retained", grant["active"]["expires_at"] == 1793327396)
        after = client.get("/api/agent-authorizations").json()
        check("checks_preserve_authorization_state", before.json()["grants"] == after["grants"])
        history = client.post(
            "/api/threads/search",
            json={"limit": 1},
            headers={"X-CSRF-Token": csrf, "Origin": args.origin},
        )
        check("existing_conversation_api", history.status_code == 200)
    receipt = {
        "passed": True,
        "checks": checks,
        "grant_count": len(inventory["grants"]),
        "active_grants": 0,
        "native_provider_calls": 0,
        "device_pairings_created": 0,
        "permissions_activated": 0,
        "scope": "Normal HTTPS owner login, deployed Go authorization APIs and management HTML; "
        "no native execution",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"passed": True, "checks": len(checks), "active_grants": 0}))


if __name__ == "__main__":
    main()
