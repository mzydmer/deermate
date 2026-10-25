# Roadmap and acceptance criteria

Status: M1 local worker alpha. Updated: 2026-10-25. This is a sequence of acceptance targets, not a delivery schedule.

## M0 — Publish the design

- [x] Define the personal-secretary use case and Python backend boundary.
- [x] Publish English and Chinese README pages.
- [x] Document architecture, upstream interfaces, threat boundaries, and open questions.
- [x] Add original concept media with a visible simulated-data label.
- [x] Add contribution and integration proposal templates.

## M1 — Prove one local task

Tracking issue: [Python worker and Codex session lifecycle · #1](https://github.com/mzydmer/deermate/issues/1).

- [x] Implement a versioned Python worker contract and local task store.
- [x] Implement the Codex native app-server adapter.
- [x] Submit a bounded task in a disposable repository and return native session ID, events, diff, and captured test output.
- [x] Distinguish execution failure, cancelled work, missing evidence, and accepted completion.
- [x] Interrupt and continue without a duplicate native session (offline tests and live Codex).
- [x] Prove duplicate submission returns the same task handle.

Verification: a real Codex repair passed independently executed validation and returned a patch. A live interruption and continuation preserved the native thread ID. Offline protocol tests cover restart recovery, pending input, denied capabilities, deadlines, and idempotency. See [local-worker.md](local-worker.md) for the precise scope. The video remains a concept storyboard until a recorded live walkthrough is added.

Exit criterion: a reproducible local walkthrough that runs on a clean machine with documented prerequisites. Replace the concept film with a labeled live demo when ready.

## M2 — Connect DeerFlow to a remote worker

- [ ] Pin and validate a compatible DeerFlow version.
- [ ] Expose narrow Python MCP tools matching its durable background-task contract.
- [ ] Add an AsyncSSH connector with host-key verification and a limited worker account.
- [ ] Show offline, reconnecting, waiting-input, and cancellation states accurately.
- [ ] Recover after controller restart and network loss without replaying side effects.
- [ ] Decide NAT traversal and reverse-forwarding enrollment, threat model, and operational requirements.
- [ ] Document authentication, key rotation, revocation, and device-loss recovery.

Exit criterion: start work from DeerFlow, finish remotely, return evidence, then demonstrate restart/reconnect recovery and revoked-access rejection.

## M3 — Add specialists and repository maintenance

- [ ] Add Claude Code design runs with structured results.
- [ ] Add a capability-negotiated ACP adapter; validate DSH and Qoder independently.
- [ ] Add a fresh-context review stage with no implicit merge rights.
- [ ] Add GitHub event verification, deduplication, allowed-repository policies, and bounded PR creation.
- [ ] Keep credentials outside worktrees and test a malicious issue/agent-output scenario.

Exit criterion: a test issue produces an isolated patch, test evidence, and independent review; duplicate events do not create duplicate PRs.

## M4 — Build the daily workspace

- [ ] Add task cards to the DeerFlow experience, with timelines, artifacts, and stop/resume controls.
- [ ] Add source-preserving research watchlists and change detection.
- [ ] Add read-only mail integration with a separate permission scope.
- [ ] Expose usage estimates and unknown cost distinctly; enforce configured job/concurrency limits.
- [ ] Keep routine polling quiet and surface actionable changes.

Exit criterion: follow several different tasks from one interface without having to manually route every handoff.

## M5 — Extend the ecosystem

- [ ] Add an optional Hermesh CLI bridge; do not require Go for the default backend.
- [ ] Add a browser tool and a dedicated-session macOS desktop adapter.
- [ ] Validate third-party assistant interfaces before claiming inbound/outbound integration.
- [ ] Publish an adapter compatibility matrix with versions and reproducible evidence.
- [ ] Review release operations, backup/restore, upgrade compatibility, and security readiness.

## Contribution priorities

Prefer a narrow Codex lifecycle proof, a worker contract review, or a DeerFlow background-task integration spike over a large framework rewrite. Do not mark a feature supported solely because the upstream project advertises the capability.
