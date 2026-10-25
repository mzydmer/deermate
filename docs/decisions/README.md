# Architecture decisions

Record significant choices and their consequences here. Current implementation and delivery status belong in [STATUS.md](../STATUS.md); requirements belong in [SPEC.md](../SPEC.md).

| ADR | Status | Decision | Implementation scope |
| --- | --- | --- | --- |
| [0001](0001-python-first.md) | Accepted | Python-owned backend; optional Hermesh bridge | Local Python M1 implemented; SSH and bridge remain planned |
| [0002](0002-durable-local-tasks.md) | Accepted | Durable local task identity, explicit recovery, and independent validation receipts | Implemented in M1 |
| [0003](0003-independent-mcp-bridge.md) | Accepted | Independent Worker behind a local Python MCP bridge | Implemented M2.1; Gateway/SQL deployment verification pending |

For a new decision, use the next number and include date, status, context, decision, alternatives, consequences, and relevant spec/code links. Statuses are `Proposed`, `Accepted`, `Superseded`, or `Rejected`; acceptance describes the design decision, not release status.

When replacing a decision, add a new ADR and mark the earlier one `Superseded by ADR NNNN`. Keep its original rationale. Routine implementation details and typo fixes do not need ADRs.
