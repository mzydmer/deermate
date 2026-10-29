# M2 real secretary model acceptance

- **Status:** Implemented; cloud-to-home acceptance remains pending
- **Milestone:** M2
- **Requirement IDs:** FR-001, FR-003, FR-006, FR-010, FR-012, FR-013; NFR-004, NFR-005, NFR-006 in [SPEC.md](../SPEC.md)
- **Updated:** 2026-10-28

## Problem and outcome

The existing native/Gateway evidence replaces model tool selection with a protected verification shim. Add an opt-in verifier that uses the normal authenticated DeerFlow run API: first real chat, then real model-selected MCP submission and independently checked Worker evidence. Preserve that distinction in receipts.

## Scope and authority

An operator explicitly supplies `--live`, an existing administrator account file, origin, model name and private state directory. Dispatch additionally requires the existing local Worker configuration and its registered disposable addition-test project. Credentials stay in private files/memory and existing encrypted model storage. Go remains the public authentication/API boundary. No new product endpoint or listener is added. No model calls run in ordinary tests.

## Contract and lifecycle

Hold an exclusive process lock for the private state directory; use atomic writes with unique temporary files. Save a private stable thread ID, HTTP run idempotency key and Worker task key before mutation. Use normal `/api/threads/{id}/runs`, not the development submit shim. Save that a run was attempted before sending it; after timeout/restart, reconcile through read-only run/task APIs rather than replaying model work. A new state directory is an explicit new paid attempt. Model input requests a fixed bounded task, but prompts are not authorization. Existing Worker project policy and native sandbox remain authoritative.

Chat acceptance checks an actual assistant response and zero MCP tasks. Dispatch requires model preflight followed by exactly one submit-tool call without extra tools, exactly one durable MCP row, matching Worker instance/request fingerprint, native session, attempt 1, independent validation and the expected addition patch in only `answer.py`. The public task projection intentionally omits remote handle/key; the operator's verifier cross-checks its local Worker SQLite mapping read-only and compares authenticated Worker evidence to the MCP result. This adds no database access to MCP or Go public APIs. Run/Worker errors, review/input and unknown outcomes fail acceptance without implying cancellation. Recursion/deadlines bound this acceptance run; they are not a hard provider-cost or per-project task quota. Do not retry a native/model request silently.

## Acceptance criteria

| ID | Observable result | Verification |
| --- | --- | --- |
| AC-LM-01 | Real model answers through Go and the normal Gateway run/checkpoint APIs | Opt-in chat verifier |
| AC-LM-02 | Model selects enrolled MCP submission; Worker completes with independent evidence | Opt-in dispatch verifier |
| AC-LM-03 | Lost acknowledgements/restart do not cause verifier replay; unsafe origin/state/account input is rejected | Offline verifier contract tests |
| AC-LM-04 | Local verification shim selects tools by name after additive preflight discovery | Offline contract plus actual local stack |
| AC-LM-05 | Retained receipts contain only bounded facts, no account, origin, key, prompt or raw model/native output | Receipt projection tests and manual review |

## Failure cases and limits

An enabled MCP entry does not prove reachable enrollment; use doctor first. Expired real host grants are not extended by this verifier. Actual cloud-to-home connectivity, reverse tunnels/NAT and restricted system accounts require their own design and explicit deployment authority. A local Docker SSH fixture is not evidence of those properties. Notification model runs are separate from initial submission and must be reported independently.

## Implementation, rollout and verification

Added `scripts/verify_secretary.py`, offline contract tests and the [acceptance guide](../secretary-acceptance.md); repaired additive discovery in the local-only submit shim. No schema or Go API migration is required.

- Full offline suite: **170 passed / 7 skipped**, 62.46 seconds; one existing Starlette deprecation warning. Fixed upstream Chart/local Compose/single-host/HTTPS contracts: **29 passed**, 1.78 seconds. Ruff and wheel passed.
- Actual cloud managed model: authenticated HTTPS save, private encrypted catalog/key, streaming tool probe and normal chat run success (1 LLM call, zero MCP tasks). No model key was written in plaintext to an export file.
- Actual local dispatch: normal run success (3 LLM calls), model preflight then one submit, real Codex attempt 1, independent unittest exit 0, expected single-file patch and delivered notification. The notification run separately completed successfully.
- Initial graph budgets of 12/32 were too low because middleware also consumes graph steps. Those attempts were retained, not replayed; one had admitted work that completed and notified despite its initial run error. Final 128-step acceptance used a new explicit bounded intent. Across all attempts: two native tasks, nine runtime-observed LLM calls and two provider probes. These are observed run counts, not billing or SDK-request counts.
- Read-only rechecks of saved intents passed without another model/native run. The [sanitized receipt](../verification/secretary-live-2026-10-28.json) binds verifier/Worker hashes and preserves successful scopes and initial failures.
- The updated local shim was separately called with an already tracked native key: HTTP 409 preserved its existing owner, with zero new native tasks. This checks additive tool discovery without replacing the real model acceptance or invoking native execution again.
- Local Gateway updated from its existing immutable image with the current wheel and no dependency/network update, after a DB backup. Cloud model configuration changed through the public API; its Gateway image and empty MCP registry remain unchanged. [Reverse link proposal](m2-home-reverse-link.md) is prepared and awaiting new SSH-grant approval, not active.
