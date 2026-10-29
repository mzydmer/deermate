# One chat, one coding session

- Status: Deployed; offline graph/Gateway/local/SSH, real cloud/Codex and browser checks passed
- Updated: 2026-10-29
- Requirements: FR-001, FR-003, FR-012, FR-018, FR-022; NFR-001, NFR-003, NFR-005

A chat incarnation may acquire one registered coding executor session. The first
coding request reserves its executor, enrolled server and project before remote
admission. Later coding requests continue its latest task; they cannot start a
second root, change executor/project, branch from an old round, or replace a
missing/uncertain native session. A new coding session requires a new chat.
Research tools remain usable in the same chat.

Enforce this with an operator-configured, fail-closed DeerFlow middleware and a
durable SQLite admission journal in the existing application home. Use the
supported `extensions.middlewares` contract, not fail-open observation plugins.
The middleware covers both registered MCP submit/continue tools and DeerMate's
continuation tool, using host-stamped user/thread/incarnation/tool-call identity.
Models cannot choose the journal identity, enrolled server authority or native ID.
Reuse the ordinary durable task driver and Worker child-task continuation contract.
No new scheduler, native grant, public listener or public Python API is introduced;
Go remains the public auth/API boundary.

Journal a deterministic tracking ID and attempted intent before submission. A
duplicate call reconciles that tracking row; an unconfirmed attempt never replays
the remote operation. Concurrent calls cannot reserve two roots. Preserve native
identity and project/workspace policies across restarts. Legacy chats may adopt
one demonstrably unambiguous finished native session from bounded complete
history. Multiple/active/missing-session histories fail closed. A legacy project
that was not recorded cannot be inferred from a new request; use the explicit
continuation tool. Forked/recreated chats do not inherit journal authority.

Names are generated from the first human message without an additional model
request, then stored in the ordinary thread title. Existing rename UI remains the
editor; later messages never overwrite a nonempty title. A product display name
does not claim to rename a native session in another client.

Codex is the currently supported executor. The journal's executor discriminator
also accepts Claude for a future explicitly registered compatible adapter; this
change does not implement or advertise a working Claude execution adapter.

Acceptance covers restart/concurrency, same-call reconciliation, active/unknown
outcome refusal, project/executor/cross-chat isolation, legacy ambiguity, native
identity changes, automatic title/rename preservation, actual pinned middleware
assembly and normal Gateway/Worker continuation. Live and browser checks must be
reported separately from fixtures.

Verification: 31 policy/name tests; full suite **244 passed / 7 skipped**; pinned
deployment contracts **32 passed**. Actual configured middleware/LangChain graph
**10 checks passed**, including title generation, rename preservation, registered
tool interception, host-bound inspection and no fallback after journal failure.
Actual pinned Gateway/local and Gateway/SSH **22/30 checks passed**, including
restart persistence, repeated raw submit routed to continuation, one native root
and no extra native turn after reconciliation/project-switch refusal. These use
an offline native fixture and do not establish real cloud/model/Claude acceptance.

Real rollout: implementation `4e5c05d` deployed to the existing Gateway, preserving
model/account/Codex configuration, home storage and the original temporary SSH
expiry. Two normal user runs both selected `deermate_submit_task`; the guard
created one root and one child, with one binding/native session/workspace and
independent validation/notifications. The first message generated the visible
name; the browser rename was saved and remained after round two. Browser
**Session binding → View executor session** showed the canonical Codex round-two
identity. See [live receipt](../verification/chat-session-binding-live-2026-10-29.json).
Claude execution remains unimplemented.
