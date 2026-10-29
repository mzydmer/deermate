# M2 continuous remote Codex conversation

- **Status:** Implemented; offline and actual pinned Gateway/SSH verified, live upgrade pending
- **Updated:** 2026-10-29
- **Requirements:** FR-001, FR-003, FR-004, FR-006, FR-010, FR-012, FR-013; NFR-001, NFR-003, NFR-005
- **Decision:** [ADR 0011](../decisions/0011-codex-conversation-turns.md)

## Outcome

From one secretary chat, ask Codex to fix a problem, explain the change, then make a further change using the same native session and workspace. Each round has its own durable task, status, cancellation and independent validation result. Prior results remain readable.

## Contract

Add authenticated Worker `POST /tasks/{parent}/continue` with message and a per-round idempotency key. Create a new child task inheriting project, policy, native session, workspace and base commit; keep the parent unchanged. Only the latest terminal round may continue. Active, waiting-input, review/recovery, missing-session/workspace and changed-policy requests are rejected. Under one transaction, advance a persistent conversation head so concurrent follow-ups cannot fork the shared workspace. Existing CLI resume remains available only for the current head. A network failure never triggers automatic application replay.

Expose raw `continue_task` through local/instance-bound SSH MCP and the ordinary durable task contract. New rounds have distinct remote handles, preserving upstream ownership and notification semantics. Advertise additive `continuation: child-tasks-v1` capability while retaining the old operations list; old Workers fail before mutation. Do not change the existing handle format.

Add an opt-in DeerFlow tool provider `continue_codex` using supported `tools[].use`. It resolves a public DeerFlow task ID only among the actual runtime user's current chat/incarnation records, privately translates its enrolled remote handle and submits through the existing ordinary driver/task service. The model cannot specify another user, thread, server, native ID, path, policy or recovery approval. Default selection is allowed only for one unambiguous conversation with bounded complete history; otherwise require an explicit current task ID. Native/MCP clients remain trusted single-owner lower-level interfaces, not a new multi-tenant boundary.

Go remains the public login/API boundary. Reuse the existing chat and background-task UI; no new browser-facing Python endpoint or competing scheduler. Result summaries include round number and opaque conversation/parent references, without paths, prompts or credentials.

## Acceptance

- Three questions through one chat create three tracked tasks, one native session and one workspace; earlier results remain unchanged.
- Same-key retries return the same child even after restart; different content conflicts. Concurrent/stale continuations and legacy resume of an old parent are rejected.
- SSH trust, expiry, revocation and protocol checks apply before continuing; no grant extension or fallback session.
- Scoped provider rejects cross-user/chat/incarnation task IDs, ambiguous history, active/recovery states and unsupported records before native execution.
- Real pinned ordinary driver/Gateway handles child polling, independent validation and notification without reusing an existing tracking row.
- Reconnect/read-only reconciliation creates no extra native round. UI/protocol/model/native evidence is reported separately.

## Rollout and limits

Back up Worker SQLite and Gateway configuration before upgrade; retain existing root tasks and enrollments. Add the optional provider and raw continuation task binding only to configured Worker profiles. Reuse the existing access lease; do not silently renew expired cloud SSH grants. Each question is a bounded native turn and may consume model quota. Native form input, approval, uncertain recovery, automatic queueing and arbitrary permanent device enrollment are separate work.

## Verification so far

Full suite: **199 passed / 7 skipped**, 70.73 seconds, one existing Starlette warning. Focused conversation/deployment checks: **53 passed**, including 32 actual pinned deployment contracts. Actual pinned ordinary driver local/SSH: 2 passed. Actual Gateway/SQL/SSH verifier: **28 checks passed**, including three rounds, parent evidence preservation, scoped rejection and same-call reconciliation. Ruff/wheel and live deployment are recorded in STATUS; generated fixtures do not establish real-model/UI/native acceptance.
