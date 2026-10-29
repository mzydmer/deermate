# Retained verification evidence

These receipts describe known test fixtures, not private user work or a production audit. Never commit credentials, prompts, raw traces, databases, host paths or screenshots here.

| Receipt | Scope |
| --- | --- |
| [codex-conversation-live-2026-10-29.json](codex-conversation-live-2026-10-29.json) | Real cloud model selects two scoped follow-ups to the earlier home Codex repair: one native session/workspace, marker recall, preserved parent/patch evidence, independent tests and delivered notifications; versioned Gateway image upgrade and unchanged lease. |
| [codex-conversation-gateway-2026-10-29.json](codex-conversation-gateway-2026-10-29.json) | Actual pinned Gateway/SQL/SSH with three child-task rounds, one offline native session/workspace, preserved parent evidence and scoped reconciliation. Real-model deployment evidence is separate. |
| [home-link-2026-10-28.json](home-link-2026-10-28.json) | Approved temporary cloud OpenSSH→Mac link: nine permission checks, real cloud model→home Codex→independent validation→delivered notification, transport reconnect and read-only task reconciliation. Expiry timer installed/active; actual expiry not yet observed. |
| [secretary-live-2026-10-28.json](secretary-live-2026-10-28.json) | Earlier cloud chat and local model-selected dispatch/notification; its prepared-only reverse-link status is historical and superseded by the separate home-link receipt. |
| [ack-package-2026-10-25.json](ack-package-2026-10-25.json) | Artifact-derived CI evidence for four linux/amd64 image builds and non-root Gateway readiness/auth/MCP/SSH/credential-copy probes; source/ZIP hashes and real image ID. No ACR push, ACK installation, model, frontend login or home SSH claim. |
| [gateway-ssh-2026-10-25.json](gateway-ssh-2026-10-25.json) | Combined actual Gateway → MCP → SSH → Worker run: 21 checks, generated credentials, Gateway restart, SSH-only outage/reconnect, revocation/cancel confirmation, validation outcomes and Worker recovery; [captured event replay](../assets/gateway-ssh-demo.html) |
| [deerflow-gateway-2026-10-25.json](deerflow-gateway-2026-10-25.json) | Actual pinned Gateway/SQLite startup, MCP tool wrapper/caller, orderly process restart, original HTTP cancellation/query, validation outcomes and Worker outage/reconnect; offline Codex fixture, no configured model |
| [ssh-transport-2026-10-25.json](ssh-transport-2026-10-25.json) | 22 generated-key SSH/HTTP/MCP protocol tests: identity, credentials, grant/connection expiry, revocation, rotation, reconnect and lost submit acknowledgement; same-host loopback endpoints, offline native fixture |

Each receipt records the upstream commit/lock hash, verifier hash, DeerMate source/fixture hashes, relevant runtime versions, fixture task IDs, checks and limits. `deermate_source_sha256` hashes sorted `src/deermate/*.py` entries as filename, NUL, then file bytes. Compare hashes with the referenced versions before treating changed code as the same evidence. A later source change does not retroactively verify itself.

Reproduction and interpretation: [combined demo](../demo.md), [DeerFlow setup](../deerflow.md), [verification spec](../specs/m2-gateway-verification.md), and [current status](../STATUS.md). The CI `deerflow-gateway` local/SSH matrix publishes its own receipts and HTML replays; a configured workflow is not evidence of a successful run until its actual result is checked. Older receipts retain their original source hashes and verification scope.
