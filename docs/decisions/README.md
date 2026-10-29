# Architecture decisions

Record significant choices and their consequences here. Current implementation and delivery status belong in [STATUS.md](../STATUS.md); requirements belong in [SPEC.md](../SPEC.md).

| ADR | Status | Decision | Implementation scope |
| --- | --- | --- | --- |
| [0001](0001-python-first.md) | Superseded for control plane by 0007 | Original Python-owned backend | Python Worker/MCP/SSH retained; Hermesh optional |
| [0002](0002-durable-local-tasks.md) | Accepted | Durable local task identity, explicit recovery, and independent validation receipts | Implemented in M1 |
| [0003](0003-independent-mcp-bridge.md) | Accepted | Independent Worker behind a local Python MCP bridge | M2.1 implemented; actual Gateway/SQLite fixture restart verified |
| [0004](0004-ssh-loopback-transport.md) | Accepted | Enrolled forwarding, bounded SSH connections and instance-bound remote handles | M2.2 implemented; generated-key protocol/driver evidence; actual temporary cloud/Mac topology separately verified under 0010 |
| [0005](0005-ack-control-plane.md) | Accepted | Single-instance ACK control plane using the pinned upstream chart and Python post-renderer | Deployment package; actual ACK installation remains operator-specific |
| [0006](0006-frontend-overlay.md) | Accepted | Hash-checked source overlay, bounded task desk and accessible motion | First DeerMate workspace; secretary routing/device liveness remain separate |
| [0007](0007-go-control-plane.md) | Accepted | Go main/management/login/frontend APIs; pinned Python runtime integration | Shared compatible identity tables, revocable sessions, admin console, local/ACK integration |
| [0008](0008-single-host-budget.md) | Accepted as optional target | Single-host Compose bundle for a personal budget trial | Prebuilt images, memory ceilings, loopback access; actual cloud purchase/deployment separate |
| [0009](0009-public-ip-https.md) | Accepted as optional public target | Exact public IPv4 HTTPS via a persistent Caddy edge | Private default retained; cloud account migration and external acceptance tracked separately |
| [0010](0010-temporary-home-reverse-link.md) | Accepted | Two restricted SSH legs for a temporary outbound home Worker link | Approved cloud-to-Mac deployment, nine OpenSSH policy checks and real model/Codex result verified; actual expiry observation pending |
| [0011](0011-codex-conversation-turns.md) | Accepted | One child task per follow-up, sharing the native session/workspace | Worker head admission, scoped DeerFlow provider and ordinary tracking; live deployment tracked in STATUS |

For a new decision, use the next number and include date, status, context, decision, alternatives, consequences, and relevant spec/code links. Statuses are `Proposed`, `Accepted`, `Superseded`, or `Rejected`; acceptance describes the design decision, not release status.

When replacing a decision, add a new ADR and mark the earlier one `Superseded by ADR NNNN`. Keep its original rationale. Routine implementation details and typo fixes do not need ADRs.
