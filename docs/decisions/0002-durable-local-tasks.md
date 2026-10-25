# ADR 0002: Durable local task identity and explicit recovery

Date: 2026-10-25. Status: accepted; implemented in M1. This records choices already present in runtime baseline `7dfe34a`, rather than adding new behavior.

## Context

Agent work can outlive one chat turn. A timeout or interrupted service does not prove that a native agent never acted. Repeating an action or replacing the session can duplicate side effects or lose context. A model can also report success without providing execution evidence.

## Decision

- Use SQLite with one worker process owning each local state directory. This is a local single-owner milestone, not a distributed database/lease design.
- Persist task identity, idempotency fingerprints, policy snapshots, native session IDs, and ordered events. Save the native session identity before starting a turn.
- Return an existing task for an identical idempotent request and reject conflicting reuse of the key. Give continuation operations their own keys.
- Keep a detached worktree per task; preserve it for inspection and continuation. A worktree does not provide OS isolation.
- After restart, preserve queued work and mark previously active work `recovery_required`. Do not automatically replay it. Continue a saved native session only after explicit recovery confirmation where required.
- Treat interruption requested and interruption confirmed as different states.
- Execute the administrator-configured validation command independently after native completion. Save its output and exit code. Missing validation or denied capability requires review; a passing command is a receipt rather than a correctness guarantee.

## Alternatives considered

| Alternative | Reason not chosen for M1 |
| --- | --- |
| Chat history as the task store | Cannot reliably deduplicate or resume work across service restart |
| Replay all unfinished prompts on startup | May repeat side effects whose outcome is uncertain |
| Always start a fresh native session | Discards continuity and can launch duplicate work |
| Accept the model's final success statement | Does not establish that tests or file changes occurred |
| Introduce a distributed orchestration platform immediately | Adds deployment and state complexity before a local task is proven |

## Consequences and limits

Recovery requires operator judgment when the prior outcome is uncertain. A hard crash, orphaned process, or remote partition needs further reconciliation design. Local recovery tests are not proof of multi-machine fault tolerance. Persistent records may contain private content; database encryption, comprehensive redaction, retention, and total quotas remain separate work.

References: [FR-003–FR-010](../SPEC.md), [store](../../src/deermate/store.py), [worker](../../src/deermate/worker.py), [Codex adapter](../../src/deermate/codex.py), and [local worker limits](../local-worker.md).
