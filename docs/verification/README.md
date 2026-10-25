# Retained verification evidence

These receipts describe known test fixtures, not private user work or a production audit. Never commit credentials, prompts, raw traces, databases, host paths or screenshots here.

| Receipt | Scope |
| --- | --- |
| [deerflow-gateway-2026-10-25.json](deerflow-gateway-2026-10-25.json) | Actual pinned Gateway/SQLite startup, MCP tool wrapper/caller, orderly process restart, original HTTP cancellation/query, validation outcomes and Worker outage/reconnect; offline Codex fixture, no configured model |
| [ssh-transport-2026-10-25.json](ssh-transport-2026-10-25.json) | 22 generated-key SSH/HTTP/MCP protocol tests: identity, credentials, grant/connection expiry, revocation, rotation, reconnect and lost submit acknowledgement; same-host loopback endpoints, offline native fixture |

Each receipt records the upstream commit/lock hash, verifier hash, DeerMate source/fixture hashes, relevant runtime versions, fixture task IDs, checks and limits. `deermate_source_sha256` hashes sorted `src/deermate/*.py` entries as filename, NUL, then file bytes. Compare hashes with the referenced versions before treating changed code as the same evidence. A later source change does not retroactively verify itself.

Reproduction and interpretation: [DeerFlow setup](../deerflow.md), [verification spec](../specs/m2-gateway-verification.md), and [current status](../STATUS.md). The CI `deerflow-gateway` job also publishes its own fixture receipt as an artifact; a configured workflow is not evidence of a successful run until its actual result is checked.
