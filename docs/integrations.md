# Integration contracts

Status: local Codex adapter implemented; MCP, SSH, and the other adapter contracts remain proposals. Updated: 2026-10-25. The local HTTP/CLI API is documented in [local-worker.md](local-worker.md).

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

DeerFlow documents ordinary MCP background tools with `submit`, `status`, and `cancel`, plus SQL-backed tracking outside the agent turn. Its `task_toolsets` mechanism expects exact raw tool names and structured content. DeerMate should expose a narrow Python MCP server mapping to that lifecycle, subject to a compatibility spike.

Example response shapes below are a design sketch aligned to that upstream contract, not endpoints available from this repository:

```json
{"task_id":"task-example","status":"running"}
```

```json
{"task_id":"task-example","status":"completed","result":{"summary":"Patch prepared","evidence":["diff","test-receipt"]}}
```

Source: [DeerFlow MCP server guide](https://github.com/bytedance/deer-flow/blob/main/backend/docs/MCP_SERVER.md). Configuration and authentication requirements must be validated against a pinned upstream version before implementation.

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
