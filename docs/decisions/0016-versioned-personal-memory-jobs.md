# ADR 0016: Versioned personal memory and bounded extraction

Date: 2026-11-09. Status: Accepted. Implementation and release evidence remain in STATUS.

## Context

The approved workspace PRD makes memory a default part of a personal assistant. Existing booleans cannot establish whether an old disabled value was an intentional pause. Ordinary Gateway messages and the Go Router Inbox have distinct provenance. A lost provider acknowledgement must not cause repeated paid extraction or revive a forgotten fact.

## Decision

Go owns versioned defaults, explicit owner migration, topic mode, owner-local scopes, durable extraction jobs, call ceilings and deletion fences. New users receive product defaults. Legacy unknown-off and explicit pauses stay unchanged. Whole temporary topics reserve their negative policy before runtime creation.

Reuse pinned DeerMem files and owner FTS5 through the internal Python adapter. A deterministic fast path handles clear ordinary expressions; otherwise reserve one bounded, no-tool, no-retry model call using the existing conversation model. Freeze model and policy before provider I/O, persist invocation state, cache the result and only reconcile that result after uncertainty. Never hold SQLite's write reservation while waiting for the provider.

Ordinary runs require canonical interactive user input. Inbox capture requires a Go-owned admission proof over the complete untruncated owner text; events cannot acquire it. The final Router prompt explicitly includes allowed personal references after role isolation. Assessor prompts do not inherit them. Project labels organize private memory and do not grant Worker or shared-project access.

## Alternatives

A shared summary or global automatic upstream memory path loses per-fact source, scope and deletion control. Adding a vector database would not solve those authority problems. Blindly retrying an extraction is operationally simpler but spends quota again and can race a correction. Automatically enabling all legacy users overwrites an unverifiable old choice.

## Consequences

SQLite remains a single local-disk Go/Gateway contract. Unknown extraction can remain uncompleted rather than call again. Recent history is deliberately bounded and interruptible; it does not promise complete recall. Byte ceilings are conservative and some long input is skipped. Usage records mean inclusion in context, not proof that a model used a fact in its answer. Sensitive-content rejection is not universal redaction or forensic erasure.

See [feature spec](../specs/workspace-assistant-v2.md), [plan](../specs/workspace-assistant-v2-plan.md), memory_jobs.go, memory_extraction.py and memory.py.
