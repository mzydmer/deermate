# Integration contracts

Status: Codex, Python stdio MCP and enrolled direct SSH implemented; other adapters remain proposals. Updated: 2026-10-25. See [local HTTP/CLI](local-worker.md), [MCP](deerflow.md) and [SSH](ssh-worker.md) for setup and limits.

## Normalized adapter operations

| Operation | Required behavior |
| --- | --- |
| `capabilities` | Report supported lifecycle operations, artifact types, input handling, and version |
| `submit` | Accept a bounded task and idempotency key; quickly return a durable task handle |
| `status` | Return normalized state and distinguish offline, input required, failed, and completed |
| `events` | Return ordered events after a cursor, with stable event IDs |
| `send` | Append authorized input to an existing native session |
| `cancel` | Request interruption; report confirmation separately from the request |
| `artifacts` | List bounded, authorized output files and provenance |

Not every agent supports resume, questions, attachments, or persistent sessions. Unsupported operations must be explicit capabilities rather than silent fallbacks. Native session IDs are stored by the service; they must not depend on the secretary remembering them.

## DeerFlow tool integration

DeerFlow documents ordinary MCP background tools with `submit`, `status`, and `cancel`, plus SQL-backed tracking outside the agent turn. Its `task_toolsets` mechanism expects exact raw tool names and structured content. DeerMate exposes `submit_task`, `get_task_status`, and `cancel_task` through Python stdio MCP to an independent loopback Worker. At `a1b89d0432de4e45adc59f512cb25bb386ea1e51`, both the ordinary driver and actual Gateway/SQLite restart path have passed. The latter uses the unchanged application/service/routes, a verifier-only model-free submit entry and an offline native fixture; see the [scope and receipt](specs/m2-gateway-verification.md).

The implemented lifecycle returns these shapes in MCP `structuredContent`; IDs and summaries below are illustrative:

```json
{"task_id":"task-example","status":"running"}
```

```json
{"task_id":"task-example","status":"completed","result":{"summary":"Patch prepared","validation_status":"passed","diff_available":true}}
```

Source: pinned [DeerFlow MCP server guide](https://github.com/bytedance/deer-flow/blob/a1b89d0432de4e45adc59f512cb25bb386ea1e51/backend/docs/MCP_SERVER.md). Exact status/error mapping, bounded result fields, and acceptance evidence are in the [M2.1 spec](specs/m2-deerflow-task-bridge.md). Cancellation returns a confirmed terminal outcome or a tool error; no unconfirmed cancellation success is reported.

The same pinned driver now passes local and SSH variants. SSH mode binds a raw `instance_id:task_id` handle (65 characters) and accepts no host, port, credential or command fields in tool arguments. Grant/transport errors remain tool errors rather than invented task failures. Setup and per-instance constraints: [M2.2](specs/m2-ssh-worker.md).

## Native agent interfaces

| Adapter | Upstream entry point | Validation needed before claiming support |
| --- | --- | --- |
| Codex | `codex app-server` | Initialization, session IDs, stream events, input/approval handling, interrupt, resume, failure |
| Claude Code | `claude -p` / supported Agent SDK | Structured output, continuation semantics, exit status, tool restrictions, cancellation |
| DeepSeek Harness | `dsh --profile acp` | ACP handshake, authentication, session lifecycle, forms, interruption |
| Qoder | Its documented ACP mode | Version and capability negotiation, auth, session load, tool events |
| Generic ACP | A real ACP adapter or native ACP entry point | Confirm framing and capabilities; an arbitrary CLI is not automatically ACP |
| Hermesh bridge | `hermesh session ... -o json` | Map session IDs, states, events, questions, diff, offline devices, and interruption |

The Codex and Claude upstream CLIs do not become ACP servers merely by being installed. Use their native documented interfaces or an explicit ACP adapter. DeerMate's Codex plan uses its native app-server.

Sources: [Codex](https://developers.openai.com/codex/app-server), [Claude Code](https://code.claude.com/docs/en/headless), [DSH ACP profile](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/bundle/acp-app), [Qoder](https://docs.qoder.com/release-notes/qoder-cli), [Hermesh](https://github.com/hermeshai/hermesh).

## Events, connectors, and external assistants

GitHub events need signature verification and deduplication by delivery ID, repository, and commit where appropriate. An event creates a task proposal; it cannot authorize a broader action than the repository policy allows. Automatic PR creation, review comments, merge, and release are separate write capabilities.

Research connectors preserve source URLs, timestamps, and prior snapshots. Use supported APIs where available. Product Hunt's API has explicit commercial-use restrictions; a connector must not assume business research is permitted by default. See [Product Hunt API documentation](https://www.producthunt.com/v2/docs).

Mail starts as a separately scoped, read-only capability. Browser and desktop tools are opt-in and must use dedicated profiles or sessions. Do not grant a research agent access to a general-purpose host shell just to read a page.

Grok Bot or Muse calling a DeerMate MCP tool is inbound delegation. DeerMate invoking those products is outbound delegation, and requires a separately verified interface. No bidirectional support is claimed.
