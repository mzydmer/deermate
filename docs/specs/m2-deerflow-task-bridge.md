# M2.1: DeerFlow durable-task bridge

- **Status:** Implemented locally; SDK/Worker, pinned upstream driver and subsequent actual Gateway/SQLite fixture verification passed. Model/UI and remote checks remain separate.
- **Milestone:** M2.1, local integration before SSH.
- **Requirement IDs:** FR-003, FR-004, FR-008, FR-009, FR-010, FR-012; NFR-001–NFR-006; AC-M2-01.
- **Updated:** 2026-10-25.

## Outcome and compatibility target

DeerFlow can submit a bounded coding task and retain its ID outside an agent turn. A Python stdio MCP bridge forwards calls to an independently running local DeerMate Worker. Disconnecting/restarting the MCP client does not own or stop execution; a new connection can query the same persisted ID.

Target the ordinary-tools contract in DeerFlow commit `a1b89d0432de4e45adc59f512cb25bb386ea1e51` (backend version `2.2.0-dev`). Verify against the actual upstream driver, not only a copied payload schema. This does not promise compatibility with all DeerFlow releases or prove a deployed Gateway/UI flow.

Sources: pinned [MCP guide](https://github.com/bytedance/deer-flow/blob/a1b89d0432de4e45adc59f512cb25bb386ea1e51/backend/docs/MCP_SERVER.md) and [ordinary task driver](https://github.com/bytedance/deer-flow/blob/a1b89d0432de4e45adc59f512cb25bb386ea1e51/backend/packages/harness/deerflow/mcp/tasks/ordinary.py).

## Scope and authority

- Expose exactly `submit_task`, `get_task_status`, and `cancel_task` with MCP `structuredContent`.
- Accept registered project ID, prompt, and caller-supplied stable idempotency key. Do not accept root paths, commands, endpoint URLs, tokens, or expanded execution permissions from tool arguments.
- Use fixed loopback HTTP and the existing private token file; disable environment proxy discovery and redirects. Keep stdout exclusively for MCP frames.
- The stdio caller has the configured single owner's task authority. Do not publish the bridge as a multi-user or remote service. DeerFlow and the Worker must share the host network and token access for this milestone.
- Keep the Worker independent. Do not start a second Worker or access its database from the bridge. No SSH, general shell tool, auto-answer, auto-resume, remote enrollment, or new credential store in this change.

## Lifecycle contract

| Tool/state | Required behavior |
| --- | --- |
| Submit | Return stable `task_id` and contract status `running` promptly, even on a duplicate of an already finished task; the next status call reports the actual state. Never retry a failed submit with a different key. |
| queued/starting/running/cancelling | Map to `running`; preserve `worker_status`. A cancellation request is not a stopped task. |
| completed/failed/cancelled | Map to the matching terminal status with bounded result/evidence summaries. |
| input_required/needs_review/recovery_required | Map to `input_required` with the actual worker state, reason, and instructions for existing local CLI controls. Keep the task pollable; never silently resume or approve it. |
| Cancel | Request cancellation, then wait within a bounded budget for an actual completed/failed/cancelled response. On uncertainty or review/recovery state, return an MCP tool error; never invent cancellation or return a nonterminal success to a terminal-only upstream parser. Repeating cancellation is safe. |
| Missing task | Normal structured `failed` with `error_code: task_not_found`. |
| Transport/auth/malformed response | MCP `isError: true`, with a safe explanation. A status-call failure does not imply task failure; upstream can retry. |

Do not copy private prompts, project paths, policy snapshots, credentials, full diffs, or unlimited output into DeerFlow's tracker. Return bounded summaries and validation excerpts with truncation flags and a local CLI route to the complete evidence. A local CLI command is not a remotely downloadable artifact URI.

## Acceptance criteria

| ID | Observable outcome | Verification |
| --- | --- | --- |
| M21-01 | MCP discovery advertises the three exact raw tool names; real stdio calls return structured content. | SDK client/subprocess test. |
| M21-02 | Duplicate submission after a bridge/client restart keeps the same ID and creates one native session. | Real Worker with offline native fixture and temporary Git repo; reconnect MCP client. |
| M21-03 | Successful and failed validation, pending native input, review and recovery retain their meaning. | API/bridge integration and state mapping tests. |
| M21-04 | Cancellation is confirmed or explicitly uncertain; terminal races are preserved; repeated cancellation is safe. | Active Worker cancellation plus delayed/unconfirmed response tests. |
| M21-05 | Offline/auth errors do not fabricate task failure; missing task is a permanent structured failure. | HTTP boundary and MCP error tests. |
| M21-06 | Invalid IDs/extra authority fields are rejected, output is bounded, and private task configuration is absent from returned summaries. | Admission/output tests. |
| M21-07 | The pinned upstream ordinary driver accepts submit/status/cancel through a real MCP session. | Opt-in compatibility probe against a verified upstream checkout; no model call. |

The subsequent [Gateway verification](m2-gateway-verification.md) satisfies AC-M2-01 for the local backend/fixture scope by exercising the actual application and SQLite service across process restart. Neither a driver probe nor the Gateway fixture is a full model-driven product or UI test.

## Rollout and handoff

Install the optional Python MCP dependency, start the existing Worker, then add an example `extensions_config.json` entry with absolute executable/config paths, raw task tool bindings, and timeouts. Enable `mcp_tasks` and SQL persistence in DeerFlow. Restart DeerFlow after configuration changes. Removing the bridge configuration rolls back this integration without migrating or deleting Worker tasks.

Record actual checks and limitations here and in STATUS/EVOLUTION after implementation. Leave the broader SSH milestone unchecked until its own acceptance evidence exists.

## Verification record · 2026-10-25

- `python -m pytest -q`: 51 passed, one explicitly skipped opt-in upstream check. One upstream Starlette TestClient deprecation warning; no test failures.
- `DEERMATE_DEERFLOW_CHECKOUT=<pinned checkout> python -m pytest -q tests/test_deerflow_compat.py tests/test_bridge.py tests/test_mcp.py`: 34 passed, including the actual upstream driver and real MCP subprocesses.
- `ruff check src tests scripts/live_smoke.py` passed; `python -m build --wheel` built `deermate-0.1.0a1`.
- MCP SDK tested at `1.30.0`; bridge dependency is bounded to the 1.x API (`>=1.30,<2`). The independently running DeerFlow client need not use the same Python environment.
- At the original bridge commit `2a941b1`, no model invocation, production deployment, full Gateway restart test, SSH, or UI walkthrough was performed. The follow-up [Gateway verification and retained receipt](m2-gateway-verification.md) now cover the local backend restart path without a model or browser.
