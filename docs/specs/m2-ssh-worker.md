# M2.2: Enrolled SSH Worker transport

- **Status:** Direct SSH transport implemented; real generated-key SSH/HTTP/MCP tests and pinned DeerFlow driver checks passed. Operator deployment/NAT remain unverified.
- **Requirements:** FR-003, FR-004, FR-009, FR-010, FR-013; NFR-001–NFR-006; AC-M2-02.
- **Updated:** 2026-10-25.

## Outcome and scope

A controller can use the existing CLI or three MCP tools against an independently running Worker on an explicitly registered SSH host. Keep the Worker HTTP listener on loopback. Use AsyncSSH TCP forwarding to that fixed remote loopback port; do not execute commands, fetch credentials through SFTP, expose a public HTTP API, or build another wire protocol.

This increment covers a directly reachable SSH server and one owner. NAT enrollment, reverse tunnels, relays, multi-controller routing, production account provisioning and real cross-machine/model/UI deployment remain separate work.

## Enrollment and authority

The administrator configures a worker ID, host/SSH port, username, explicit known_hosts file, dedicated client key file, copied Worker API token file, expected Worker instance ID, optional key-passphrase environment reference, access expiry, and bounded connection lifetime. Model tool arguments cannot select or change any of those values.

No trust-on-first-use or accept-all callback; no ambient SSH config, agent, password, keyboard-interactive fallback or agent forwarding. Validate credential/trust file types and permissions. Unknown or changed host keys, wrong client keys, credentials or application instance identities fail closed with safe errors.

Add an instance ID to the Worker's SQLite metadata, stable across service restart and part of backup identity. It prevents accidental target drift; SSH host-key verification provides host authentication. It is not another credential or a new encryption scheme.

Remote MCP handles bind `instance_id:task_id`, within DeerFlow's 255-character limit. A process restart or configuration update cannot silently query a different instance's task. Local MCP IDs stay unchanged. CLI accepts the native task ID with an explicit registered worker, or the bound handle.

## Lifecycle and revocation

- Re-read the registered grant before each HTTP operation. Disabled, removed or expired entries reject access and close the cached tunnel.
- Configuration changes require a new client/MCP process; credential/trust-file content changes force fresh SSH authentication. Recheck the expected Worker instance before each operation.
- Bound SSH connection age (default 60 seconds, maximum 300) so new authentication is periodically required. Removing a server authorized key alone does not close an already authenticated connection; immediate server-side revocation also requires disconnecting active SSH sessions. Document this window.
- A revoked/expired grant forbids new queries, mutations and cancellations. Previously admitted native work continues within its Worker deadline; the local administrator remains responsible for stopping it when needed. Do not claim revocation stopped execution.
- Connection failure is an unknown task outcome, not task failure or cancellation. Retry connections, never automatically replay HTTP mutations. Repeating submit requires the same explicit idempotency key; resume remains explicit.
- Keep remote commands, target ports and tokens outside prompts. SSH endpoints can read plaintext. A forwarding relay, if added later, must not terminate this SSH channel.

## Acceptance

| ID | Observable result |
| --- | --- |
| M22-01 | Real temporary SSH server authenticates only the dedicated key and permits only the configured Worker loopback destination; CLI and MCP can submit/query/cancel and retrieve evidence. |
| M22-02 | Host-key mismatch/missing trust, client-key rejection, wrong API token and instance mismatch fail before task submission; no ambient credentials or accept-all trust. |
| M22-03 | Disconnect/reconnect and controller/MCP restart preserve instance-bound handles, idempotency and native session identity. No automatic mutation retry or duplicate native turn. |
| M22-04 | Disabled/removed/expired grants, changed configuration, key rotation and bounded connection expiry behave as documented. Revocation does not falsely report stopped work. |
| M22-05 | Remote outage and unconfirmed cancellation are tool errors; successful/failed validation, review and recovery retain existing lifecycle semantics. |
| M22-06 | Stable Worker instance identity survives SQLite reopen and upgrades existing local stores without rewriting tasks. |

Use generated temporary keys, an in-process real SSH protocol server, real loopback HTTP Worker, temporary Git repositories and the existing offline Codex fixture. Never use the operator's real SSH daemon, keys or host configuration for automated tests. Retain a bounded fixture receipt and record local/CI evidence. Keep actual multi-machine, OpenSSH deployment policy, NAT and hard-crash claims separate.

## Verification · 2026-10-25

- `python -m pytest -q`: 74 passed, 3 explicitly opt-in upstream checks skipped; one existing Starlette TestClient deprecation warning.
- `python -m pytest -q tests/test_ssh.py --ssh-receipt <file>`: 22 passed; [retained receipt](../verification/ssh-transport-2026-10-25.json) matches the source, reporter, fixture hashes and dependency versions.
- `DEERMATE_DEERFLOW_CHECKOUT=<pinned checkout> python -m pytest -q tests/test_deerflow_compat.py`: 2 passed, local and SSH with the actual upstream ordinary driver.
- Focused SSH/store checks passed; Ruff, dependency consistency and wheel build passed. Test runtime: macOS/Python 3.12, AsyncSSH 2.24.1, bcrypt 5.0.0, cryptography 48.0.1, MCP 1.30.0.
- No real credentials, operator SSH server, system configuration, model invocation, two-machine deployment, NAT or UI was used. A server-side OpenSSH restriction template is provided for deployment validation; it is not automatically installed or certified by these tests.
- Remote [CI 40206131865](https://github.com/mzydmer/deermate/actions/runs/40206131865) passed all four jobs at `96ca52b`, including both ordinary-driver variants and the existing local Gateway regression. Both platform SSH receipts and the Gateway receipt were verified present.
