# Feature/change spec template

Copy this file to a descriptive filename for a substantial feature, such as `m2-deerflow-task-bridge.md`. Routine fixes do not need a separate feature spec. Replace the prompts below with concrete decisions before treating the document as an accepted design.

- **Status:** Proposed / Accepted / Implemented / Superseded
- **Milestone:** M2, etc.
- **Requirement IDs:** Relevant `FR-*` / `NFR-*` in [SPEC.md](../SPEC.md)
- **Tracking:** Issue/PR links when they actually exist
- **Updated:** YYYY-MM-DD

## Problem and outcome

Describe a concrete trigger, the current behavior, the intended behavior, and who benefits. State what counts as completion.

## Scope

Define included behavior, excluded behavior, and upstream dependencies/versions that need verification. Distinguish product decisions from implementation options.

## Contract and lifecycle

Describe requests, responses, stable IDs, state transitions, idempotency, errors, cancellation, restart/reconnect behavior, compatibility, and migration requirements. Include examples that are clearly labeled if not implemented.

## Authority and data boundaries

Specify who can invoke the feature, what authority is granted, where credentials and plaintext exist, which input is untrusted, and how grants expire or are revoked. Reuse current authorization; do not assume new permissions merely because an adapter is available.

## Acceptance criteria

List observable results with stable criteria IDs. Map each criterion to a test, reproducible command, or retained evidence. Identify which claims require native/live verification rather than a fixture.

## Failure cases and limits

Define uncertain outcomes, duplicate delivery, offline devices, partial artifacts, oversized inputs, deadlines, and unsupported upstream capabilities. State what the user sees.

## Implementation and rollout

Break the change into small steps; document compatibility, deployment, upgrade, and rollback where relevant. Link an ADR for a significant tradeoff instead of duplicating its full rationale.

## Verification and handoff

Record actual commands/results and evidence links after implementation. Update [STATUS.md](../STATUS.md), [roadmap.md](../roadmap.md), and [EVOLUTION.md](../EVOLUTION.md) as appropriate. Never mark a planned acceptance check as passed in advance.
