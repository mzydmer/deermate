# M2 Worker connection preflight

- **Status:** Implemented
- **Milestone:** M2
- **Requirement IDs:** FR-009, FR-011, FR-013; NFR-002, NFR-003, NFR-004, NFR-005, NFR-006 in [SPEC.md](../SPEC.md)
- **Updated:** 2026-10-28

## Problem and outcome

An enabled MCP configuration does not establish that a home Worker is reachable. Before dispatching work, an operator or secretary needs a bounded read-only check of the configured connection, credentials, Worker identity and protocol. The result must distinguish connectivity from native-agent execution readiness.

## Scope

Add `deermate ... doctor` and the no-argument MCP tool `check_worker_connection` to the existing Python Worker integration. Reuse the loopback HTTP or explicitly enrolled AsyncSSH connection. Go continues to own main/admin/auth/frontend APIs. No new public listener, device registration, project grant, task, native agent, model request, NAT traversal or desktop access is introduced.

## Contract and lifecycle

`doctor` prints a bounded JSON report and exits 0 for `status: reachable`, 1 for `status: blocked`. Reports contain a UTC `checked_at`, connection type (and enrolled Worker ID for SSH), `execution_readiness: not_checked` and `task_outcome: not_checked`. Success includes authenticated protocol-v1 capabilities and whether the application identity was observed locally or pinned by SSH enrollment. Failure includes a stable error code and a fixed sanitized message. A blocked check is a normal MCP result; malformed tool arguments remain tool errors.

Only authenticated `GET /capabilities` is allowed. The response is limited to 32 KiB, parsed strictly, and projected to known bounded fields. Unknown additional fields are ignored, never echoed. Version 1, the Codex app-server adapter, a loopback-only Worker and submit/status/cancel operations are required; unknown versions or adapters are blocked. SSH checks the same contract before forwarding **any** operation, preventing mutation against an incompatible Worker. Existing task handles, task tools and idempotency keys are unchanged.

The check has a 15-second request deadline in addition to existing HTTP/SSH deadlines, followed by at most two seconds for existing SSH transport cleanup. It performs no hidden retry and respects cancellation. SSH identity failures, disabled/expired/removed grants and changed enrollment close cached tunnels. Later recovery is a fresh explicit read; a successful report is a timestamped observation, not a lease or dispatch authorization.

## Authority and data boundaries

The operator supplies the local config or an administrator-registered Worker ID. MCP accepts no target, host, path, credentials or commands. Existing token privacy checks, pinned SSH host key, dedicated client key, expected Worker instance, grant expiry/revocation and no-agent/no-password rules remain in effect. Reports omit hosts, usernames, file paths, credential content, project policy and raw upstream errors. Endpoints still see plaintext; SSH is reused, with no new cryptography.

## Acceptance criteria

| ID | Observable result | Verification |
| --- | --- | --- |
| AC-PF-01 | Local doctor returns authenticated bounded capabilities, with no task or native execution | HTTP fixture and CLI subprocess tests |
| AC-PF-02 | Valid enrolled SSH reports pinned identities and forwards only to the registered loopback port | Generated-key SSH fixture |
| AC-PF-03 | Invalid credentials, host/application identity, grant lifecycle, unavailable connection and incompatible/oversized responses produce sanitized blocked reports | Local and SSH failure tests |
| AC-PF-04 | MCP exposes a read-only, no-argument check; task tool schemas and durable tracking remain compatible | Real stdio MCP, pinned driver and actual Gateway discovery checks |
| AC-PF-05 | A failed check never claims tasks stopped or native readiness; explicit recheck can recover without replaying tasks | SSH live-task/reconnect tests and bounded deadline test |
| AC-PF-06 | Incompatible SSH capability responses are rejected before mutation | SSH protocol failure tests |

## Failure cases and limits

Connectivity/authentication/protocol success does not prove Codex login, capacity, a project-specific grant, model availability, OS isolation or future reachability. Existing work may continue after a blocked check. Actual cloud-to-home/OpenSSH/NAT and configured-model verification remain separate acceptance targets. No long-running monitor or persisted online-state registry is added.

## Implementation and rollout

Add a shared capability validator, structured bridge check, CLI entry and additive MCP tool. Extend the Gateway verifier to select task tools by name and verify that the new check remains a normal read-only tool. No database or Go API migration is required. Upgrade the trusted controller/MCP package and restart MCP discovery; old controllers keep their original three tools. Revert the package change to roll back; Worker tasks are unaffected.

## Verification and handoff

- `.venv/bin/python -m pytest -q tests/test_preflight.py`: **45 passed**, including real stdio MCP, loopback HTTP, generated-key SSH, operator CLI and failure cases. Protocol-corruption cases alter the application response after the actual SSH/HTTP exchange; they do not claim a separate-host server test.
- `.venv/bin/python -m pytest -q`: **148 passed / 7 skipped**, 63.03 seconds. Optional upstream/deployment checks need explicit environment settings; one existing Starlette deprecation warning remains.
- With the fixed upstream checkout and frozen Gateway Python, `tests/test_deerflow_compat.py tests/test_deerflow_gateway.py`: **4 passed**, 104.17 seconds, local/SSH driver and actual Gateway paths.
- Final SSH Gateway verifier: **26 checks passed**. The [retained receipt](../verification/worker-preflight-gateway-2026-10-28.json) binds source/verifier hashes, records normal MCP preflight conversion, SQL tracking/restart, revocation/cancellation and no native replay. Model selection is replaced by the existing protected verifier entry; native execution uses the offline fixture.
- Ruff, wheel and whitespace checks passed. The new local `doctor` also returned `reachable` against the already running host Worker without submitting native work. No cloud deployment, real home SSH grant, model request or Go/frontend change was made for this feature.

See [STATUS.md](../STATUS.md), [roadmap.md](../roadmap.md) and [EVOLUTION.md](../EVOLUTION.md) for handoff and remaining work.
