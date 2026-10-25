# M2.1: Gateway and SQL restart verification

- **Status:** Implemented; actual Gateway/SQLite process-restart and reconnect checks passed locally.
- **Requirements:** FR-003, FR-004, FR-010, FR-012; NFR-004, NFR-005, NFR-006; AC-M2-01.
- **Compatibility target:** DeerFlow `a1b89d0432de4e45adc59f512cb25bb386ea1e51`, using its frozen backend environment.
- **Updated:** 2026-10-25.

## Outcome

Start the actual upstream Gateway application and lifespan, SQL repository/service, tool discovery and submit wrapper, and background poller against a separate DeerMate Worker. Stop and restart the Gateway process while work is still active. The same SQL tracking row, remote Worker ID and native session must remain usable without replaying the submission.

The existing pure-driver probe does not exercise this path. The new verification must not replace the upstream task service, SQL repository, HTTP task routes or lifecycle with mocks.

## Deterministic test boundary

Use a temporary Git repository and the existing explicitly labeled offline Codex protocol fixture. A verifier-only, per-run-key protected submission shim invokes the actual discovered DeerFlow tool with server-owned thread/user context. This substitutes for the model choosing a tool; it is not a production API or a chat/UI test. Existing Gateway task query and cancel routes remain unchanged.

Use isolated configuration, dotenv, application home and SQLite paths, loopback listeners, and a filtered child environment with no model credentials. Configure no cloud models and reject non-loopback socket connections inside the verification Gateway. These are test controls, not claimed production sandbox properties. Do not change the user's normal DeerFlow configuration or global credentials.

## Acceptance

| ID | Required evidence |
| --- | --- |
| M21G-01 | Actual Gateway startup, migrations, SQL-backed thread/task rows, real MCP discovery; only the submit tool is visible to the secretary. |
| M21G-02 | Gateway process replacement preserves the SQL row and remote/native IDs; one native session, no duplicate turn from restart. |
| M21G-03 | The original HTTP task routes query the recovered task and request cancellation; the background service confirms it in SQL and Worker state. |
| M21G-04 | Completed and failed validation propagate through the background poller to the original query API with evidence. |
| M21G-05 | Worker outage records retry/degraded tracking rather than inventing terminal failure; reconnect can query existing work. |
| M21G-06 | Persist a bounded JSON receipt containing pinned source/runtime identifiers, scenario outcomes and IDs, without tokens, private paths, prompts, databases or raw traces. |

No browser, real-model interaction, notification-model completion, SSH, remote partition, or hard-crash claim follows from this check. Process replacement in this milestone is an orderly stop/start. Keep remote and hard-crash acceptance separate.

## Delivery

Provide an opt-in reproducible script and CI job with the pinned upstream checkout and frozen environment. Ordinary development tests remain independent of the large Gateway dependency set. Retain a non-private fixture receipt as evidence and document the exact command, output, environment limits and next task after the check succeeds.

## Verification · 2026-10-25

- The standalone verifier passed 14 recorded checks on macOS/Python 3.12.14 with the frozen upstream environment. [Retained JSON receipt](../verification/deerflow-gateway-2026-10-25.json) includes the upstream lock hash, verifier hash, package versions, fixture IDs and exact verification limits.
- `DEERMATE_DEERFLOW_CHECKOUT=<checkout> DEERMATE_GATEWAY_PYTHON=<backend venv python> python -m pytest -q tests/test_deerflow_gateway.py`: 1 passed in 37.72 seconds.
- Normal suite: 51 passed, 2 skipped (both explicitly opt-in upstream probes); Ruff and wheel build passed. No real model was invoked.
- Actual Gateway startup created the SQL schema and stamped Alembic revision `0048_extension_execution_leases`. This is fresh-database verification, not a historical-schema upgrade test.
- With no configured chat model, upstream notification runs fail model assembly as expected. Task results and cancellation are validated through original HTTP routes and SQL; model-generated notification completion and browser UX remain unverified.
