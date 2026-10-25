# ADR 0003: Independent Worker behind a local MCP bridge

Date: 2026-10-25. Status: accepted and implemented for M2.1. Requirement: FR-012; acceptance: AC-M2-01 (deployment validation remains partial).

## Context

DeerFlow can persist ordinary submit/status/cancel tasks, but it may close or recreate a stdio server for discovery, connection pooling, or restart. A stdio child which owns execution could stop a task when a client disconnects. Opening another Worker on the same state directory would conflict with M1's process ownership and recovery rules.

## Decision

- Run the existing Worker independently. The optional Python stdio MCP process only calls its authenticated loopback HTTP API and never opens its database.
- Expose three exact raw names with strict JSON schemas and `structuredContent`: `submit_task`, `get_task_status`, `cancel_task`. Keep project roots, command templates, credentials and endpoint selection out of tool arguments.
- Reuse persisted Worker IDs and idempotency. Match the pinned ordinary-task driver's contract rather than implementing a second scheduler or MCP task protocol extension.
- Submit acknowledges tracking with `running`; status preserves actual worker phase. Review, form input and uncertain recovery remain visible as `input_required` rather than successful completion.
- Honor the upstream terminal-only cancel schema. Wait within a bounded confirmation budget, or return a tool error that leaves the outcome unknown. Network/auth failures do not become fabricated remote task failures.
- Return bounded summaries and receipt excerpts. Keep full patches, prompts and policy snapshots in the Worker. Do not invent remotely accessible artifact links.
- Bound the optional SDK to `mcp>=1.30,<2`, tested at 1.30.0. Adopt another major API only with explicit compatibility validation; DeerFlow's client runs independently.

## Alternatives considered

| Alternative | Reason not chosen |
| --- | --- |
| Embed Worker execution in every stdio process | Client lifecycle would own execution and multiple processes would contend for state |
| Read SQLite directly from the bridge | Bypasses the authenticated boundary and couples to store internals |
| Add an externally reachable HTTP MCP service now | Introduces remote identity and multi-user exposure before SSH/admission design |
| Mark cancelling as cancelled | Violates the actual execution outcome and upstream terminal contract |
| Report review/recovery as completed | Discards missing evidence and uncertain side effects |

## Consequences and limits

Operators start one Worker and give the trusted local MCP process access to its existing private token. The current bridge is for one host/network namespace and one owner, not a cloud-to-home connection. Full DeerFlow Gateway/SQL restart validation remains required, even though SDK/subprocess tests and the actual pinned upstream driver pass. Native form answers and explicit recovery use existing local CLI controls. No database migration is needed to enable or remove this bridge.

References: [feature spec](../specs/m2-deerflow-task-bridge.md), [setup](../deerflow.md), [bridge](../../src/deermate/bridge.py), [MCP server](../../src/deermate/mcp_server.py), and [compatibility probe](../../tests/test_deerflow_compat.py).
