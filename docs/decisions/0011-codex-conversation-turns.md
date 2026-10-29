# ADR 0011: Preserve each Codex conversation round as a child task

Date: 2026-10-29. Status: Accepted; implemented; offline/pinned Gateway and an approved temporary cloud-to-home three-round conversation verified.

## Context

Worker resume retains the native session/workspace but updates one task's prompt/result. DeerFlow owns each remote handle in one durable tracking row; reopening that row would lose prior evidence and misrepresent background notifications. Web users need follow-up questions in the same native conversation.

## Decision

Create a new Worker child task for each follow-up. Inherit the existing native session/workspace and policy, retaining immutable prior terminal records. Advance one persistent conversation head transactionally; reject stale/concurrent parents and unsafe recovery. Keep existing instance-bound handle format and ordinary submit/status/cancel driver semantics.

A supported optional DeerFlow tool provider resolves a public tracking ID within the authenticated runtime's user/chat/incarnation and privately submits the raw MCP continuation. Raw MCP remains a trusted enrolled single-owner integration. Reuse the existing chat/task UI and Go public API/auth; add no new scheduler or browser-facing Python route.

## Alternatives and consequences

Reopening the existing tracking row would require changing pinned upstream persistence/notification semantics. Returning a new native session would lose context. Per-attempt virtual handles would require immutable attempt snapshots plus new status/cancel parsing. Child tasks fit existing tracking and keep one independently inspectable record per question.

The shared workspace must have one latest head; old rounds cannot resume after a child is admitted. SQLite adds a small head table and child metadata, while old root rows remain readable. A worktree remains a trusted execution boundary, not an OS sandbox. Explicit CLI recovery and native form answers remain separate.

See the [feature spec](../specs/m2-codex-conversation.md).
