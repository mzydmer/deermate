# Roadmap and acceptance criteria

Status: M1–M2.5, M4.1 workspace, Go control plane and shared design language implemented; single-host public IP HTTPS verified. Worker preflight and one real cloud-model-to-home-Codex task verified over an approved temporary reverse SSH link; general enrollment and actual expiry observation remain pending. Updated: 2026-10-28. This is a sequence of acceptance targets, not a delivery schedule.

See [SPEC.md](SPEC.md) for stable requirements, [STATUS.md](STATUS.md) for current implementation and verification, and [EVOLUTION.md](EVOLUTION.md) for project history. Agents start at [AGENTS.md](../AGENTS.md).

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

- [x] Pin and validate DeerFlow's ordinary-task driver contract (`a1b89d0`).
- [x] Expose narrow Python MCP tools matching its durable background-task contract.
- [x] Exercise the actual DeerFlow Gateway with SQLite-backed tracking across orderly process restart (AC-M2-01; offline native fixture and model-free tool entry).
- [x] Add enrolled AsyncSSH forwarding with host-key verification, dedicated key/token references and instance-bound handles.
- [x] Demonstrate actual Gateway → MCP → SSH → Worker in one run, including SSH outage/reconnect, revoked cancellation and Worker recovery, with a receipt and captured-event replay.
- [x] Prepare a single-instance ACK control-plane package with ACR builds, the pinned upstream Helm chart, persistent block storage, authentication and optional Worker enrollment; image/cluster verification states are tracked separately in STATUS.
- [x] Run a loopback-only local Docker profile, log in through a real browser, and complete a real Codex repair through Gateway/MCP/SSH with retained validation, idempotency and restart evidence; secretary model remains unconfigured.
- [x] Prepare an optional [single-host budget bundle](single-host.md), preserving Go authentication and private access; validate fresh startup, bounded reads and restart persistence under container memory ceilings.
- [x] Purchase and validate the selected minimum cloud host: actual headroom, bounded HTTP/browser access and controlled full-host reboot ([receipt](verification/single-host-cloud-2026-10-27.json)).
- [x] Deploy the separately approved public IPv4 HTTPS profile, migrate the cloud owner, and verify trusted TLS, access boundaries and reboot persistence ([receipt](verification/single-host-public-ip-2026-10-27.json)); real certificate renewal/model/home Worker acceptance remain separate.
- [x] Add read-only CLI/MCP Worker preflight with authenticated bounded capabilities, SSH grant/identity checks, protocol admission and sanitized failure reports ([spec](specs/m2-worker-preflight.md)); connectivity does not imply native execution readiness.
- [x] Verify encrypted managed model configuration and one real cloud chat through Go and the normal Gateway run API; higher-load capacity remains separate.
- [x] Verify local real model-selected MCP preflight/submission, native Codex evidence and delivered model notification through the normal run API ([receipt](verification/secretary-live-2026-10-28.json)).
- [x] Validate separately authorized cloud-to-home connectivity: real model-selected home Codex task, independent test and delivered notification over a temporary reverse SSH link ([scope](specs/m2-home-reverse-link.md), [receipt](verification/home-link-2026-10-28.json)).
- [x] Validate the two restricted cloud OpenSSH accounts and Mac outbound connection: nine actual permission checks; Mac system sshd remains unchanged.
- [ ] Show offline, reconnecting, waiting-input, and cancellation states accurately.
- [ ] Recover after controller restart and network loss without replaying side effects.
- [x] Define and verify one explicitly approved temporary reverse-forwarding topology and threat boundary ([ADR 0010](decisions/0010-temporary-home-reverse-link.md)).
- [ ] Productize device enrollment, Mac restart supervision and expiry/device-loss recovery; observe the installed lease actually expire.
- [x] Document direct-SSH authentication, rotation, expiry and revocation windows.
- [ ] Validate device-loss recovery and NAT enrollment operationally.

Exit criterion: start work from DeerFlow, finish remotely, return evidence, then demonstrate restart/reconnect recovery and revoked-access rejection.

Run the [combined demo](demo.md) to exercise 21 checks over actual Gateway/MCP/SSH/Worker processes. Its [receipt](verification/gateway-ssh-2026-10-25.json) and [replay](assets/gateway-ssh-demo.html) include Gateway restart, SSH-only outage/reconnect, revocation and confirmed cancellation. This uses generated credentials and an offline native fixture on one host; real devices, product UI/model notifications and hard crashes remain separate acceptance targets.

User-requested ACK deployment uses the [quick deployment guide](ack-deployment.md). Its single Gateway/PVC topology supersedes the earlier recommendation to defer Kubernetes; see [ADR 0005](decisions/0005-ack-control-plane.md). A deployment script and successful image probe do not establish an actual user-cluster or cloud-to-home deployment.

The separate [SSH receipt](verification/ssh-transport-2026-10-25.json) covers 22 real generated-key SSH/HTTP/MCP tests, including lost acknowledgements, key rotation and revocation. Both local/SSH pinned-driver variants pass. This remains a same-host network fixture, not two-machine or NAT deployment evidence.

## M3 — Add specialists and repository maintenance

- [ ] Add Claude Code design runs with structured results.
- [ ] Add a capability-negotiated ACP adapter; validate DSH and Qoder independently.
- [ ] Add a fresh-context review stage with no implicit merge rights.
- [ ] Add GitHub event verification, deduplication, allowed-repository policies, and bounded PR creation.
- [ ] Keep credentials outside worktrees and test a malicious issue/agent-output scenario.

Exit criterion: a test issue produces an isolated patch, test evidence, and independent review; duplicate events do not create duplicate PRs.

## M4 — Build the daily workspace

User-requested M4.1 UI work starts on the M2 runtime while specialist routing remains pending. See [workspace source](../frontend/README.md) and [M4.1 spec](specs/m4-workspace-refresh.md).

- [x] Add a DeerMate secretary home, bounded read-only real task list, evidence drawer, draft handoff and accessible motion on the reused frontend.

- [ ] Add task cards to the DeerFlow experience, with timelines, artifacts, and stop/resume controls.
- [ ] Add source-preserving research watchlists and change detection.
- [ ] Add read-only mail integration with a separate permission scope.
- [ ] Expose usage estimates and unknown cost distinctly; enforce configured job/concurrency limits.
- [ ] Keep routine polling quiet and surface actionable changes.

Exit criterion: follow several different tasks from one interface without having to manually route every handoff.

## M4.2 — Go main, management and frontend APIs

Owner-requested language change; [ADR 0007](decisions/0007-go-control-plane.md) supersedes the original Python-only control plane.

- [x] Implement Go login/sessions, account/admin APIs, CSRF, roles and audit.
- [x] Keep original account IDs/passwords/preferences and historical task ownership.
- [x] Route frontend browser/SSR APIs through Go; retain Python Agent/Worker integration.
- [x] Provide `/admin` and verify actual create/suspend interactions.
- [x] Add local Compose and ACK sidecar/image packaging with private runtime access.
- [x] Verify local API restart/revocation/isolation and existing browser workspace without new model work.
- [ ] Design project-scoped execution grants before enabling normal-user execution.
- [ ] Add external identity/OAuth, MFA and recovery as separately specified features.

## M4.3 — Shared Vercel-inspired design language

- [x] Establish root `design.md` as the required guide for all future frontend work.
- [x] Share neutral light/dark tokens across React and embedded Go management UI.
- [x] Enforce token consistency in builds and CI; link guidance from AGENTS and contribution docs.
- [x] Verify the refreshed login/workspace/admin pages on desktop, mobile, dark and reduced-motion modes.

## M5 — Extend the ecosystem

- [ ] Add an optional Hermesh CLI bridge; keep its separate upstream implementation optional.
- [ ] Add a browser tool and a dedicated-session macOS desktop adapter.
- [ ] Validate third-party assistant interfaces before claiming inbound/outbound integration.
- [ ] Publish an adapter compatibility matrix with versions and reproducible evidence.
- [ ] Review release operations, backup/restore, upgrade compatibility, and security readiness.

## Contribution priorities

Prioritize bounded SSH enrollment, worker contract review, and configured-model notification verification before expanding adapters. Do not mark a feature supported solely because the upstream project advertises the capability.
