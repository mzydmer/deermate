# M2.3: Complete Gateway → MCP → SSH → Worker demonstration

- **Status:** Implemented; local acceptance passed in both transport modes. Remote CI is tracked in STATUS.
- **Requirements:** FR-003, FR-004, FR-010, FR-012, FR-013; NFR-004–NFR-006; AC-M2-01/AC-M2-02.
- **Upstream:** DeerFlow `a1b89d0432de4e45adc59f512cb25bb386ea1e51`, frozen backend environment.
- **Updated:** 2026-10-25.

## Outcome

Extend the real Gateway verifier with an SSH mode. One command starts an unchanged upstream Gateway application/service, its real MCP discovery/submit wrapper, the enrolled SSH client, a generated-key SSH fixture process, and the independent HTTP Worker/native adapter. Retain one combined receipt and a replay of actual events so reviewers can see the entire path in one run.

## Boundaries

- Reuse the existing per-run-key protected, model-free submit shim. Only model tool selection is substituted; SQL service, original task HTTP routes, background polling, MCP, SSH and native adapter execute normally.
- Use generated keys, fresh known_hosts, a copied fixture API token and the actual Worker instance ID in a temporary enrollment. Do not touch real SSH configuration, operator keys, devices, credentials or the network outside loopback.
- The fixture server accepts the dedicated key and only the configured Worker loopback destination, rejecting session/exec/subsystem requests. It is an opt-in demo process, not a new production service.
- This is real protocol/process execution on one host with an offline native fixture and no configured chat model. It does not prove cloud-to-home connectivity, OpenSSH account policy, NAT, real-model notification completion, chat UI, or hard-crash recovery.

## Acceptance

| ID | Observable evidence |
| --- | --- |
| M23-01 | Actual Gateway submission creates a SQL tracking row whose remote handle binds the enrolled instance; SSH server records authenticated forwarding to the only allowed target. |
| M23-02 | Successful repair returns validation output through Gateway and exposes a diff captured by a read-only Worker observer; failed validation remains failed. The three existing MCP tools return bounded evidence/diff availability, not raw patches. |
| M23-03 | Gateway process replacement preserves SQL/Worker/native identity; original cancellation route confirms the outcome over SSH. |
| M23-04 | SSH-only outage degrades tracking while Worker continues; restarting the SSH fixture with the same identity restores tracking without another native turn. |
| M23-05 | Revoked enrollment rejects cancellation without claiming the task stopped; restoring the same grant allows the pending explicit cancellation to complete. |
| M23-06 | Worker stop/restart over the SSH path preserves identity and becomes explicit recovery, without replay. |
| M23-07 | One bounded receipt records source/runtime hashes, stage timestamps, fixture IDs, SSH counters, outcomes and limits, with no secrets, private paths or raw logs. |
| M23-08 | A standalone HTML replay uses only captured receipt events and fixture artifacts, labels its scope, and supports replay without external resources. CI exercises both local and SSH Gateway modes and retains their receipts/replays. |

Keep local mode compatible. Publish runnable commands, precise evidence, and current limitations in the same change. Update STATUS/SPEC/roadmap and append EVOLUTION after actual verification; do not upgrade older receipts into evidence for new source.

## Recorded result

The opt-in pytest entry ran both actual Gateway modes: 2 passed in 92.59 seconds. The retained SSH run has 21 passing checks; the last check occurred at +44.779 seconds. Its receipt contains the five submitted tasks and confirms five native session starts and five turn starts. See [receipt](../verification/gateway-ssh-2026-10-25.json), [replay](../assets/gateway-ssh-demo.html), and [reproduction](../demo.md). CI status and delivery state belong to [STATUS](../STATUS.md).
