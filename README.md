<p align="center">
  <img src="docs/assets/hero.png" alt="DeerMate — one private assistant, your agents, your machines" width="100%" />
</p>

<h1 align="center">DeerMate</h1>
<p align="center"><strong>One private assistant. A team of agents. Your machines.</strong></p>
<p align="center">Talk to your secretary. Let the right agent take the job. Follow the work from one place.</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-6ee7b7" /></a>
  <img alt="Stage: systems research alpha" src="https://img.shields.io/badge/Stage-systems_research_alpha-fbbf24" />
  <img alt="Backend: Go" src="https://img.shields.io/badge/Backend-Go-00ADD8" />
  <img alt="Deployment goal: self hosted" src="https://img.shields.io/badge/Deployment_goal-self_hosted-c4b5fd" />
</p>
<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>
<p align="center"><a href="#research">Research</a> · <a href="#see-the-idea">Preview</a> · <a href="#how-it-fits-together">Architecture</a> · <a href="#connect-your-agents">Integrations</a> · <a href="#development-status">Progress</a> · <a href="CONTRIBUTING.md">Contribute</a></p>

> **Personal-agent systems research alpha · 2026-11-04.** Go control, real Codex session continuity and the personal-memory home have retained implementation evidence. User-managed device authorization and outbound HTTPS have separate local acceptance. The persistent Router/Worker architecture now has an opt-in Alpha implementation and isolated offline acceptance; live integrations and comparative research experiments remain separate. The video is a concept film. [Current status](docs/STATUS.md) · [Research spec](docs/specs/m4-continuous-agent.md).

## Meet your personal agent secretary

[Product guide (Chinese)](docs/product/guide/overview.md) · [Technical design](docs/product/technical/architecture.md) · [Changelog](docs/product/changelog.md). The in-app Product docs entry opens `/docs`; this documentation center is a local change awaiting deployment. Future changes follow the [documentation policy](docs/DOCUMENTATION_POLICY.md).

You should be able to say:

> “Watch this repository. When a reproducible bug arrives, ask Claude to propose a fix, let Codex implement it on my home machine, and have a separate agent review the patch. Bring me the result.”

Or:

> “Track these competitors on GitHub and Product Hunt. Explain what changed, keep the sources, and tell me only when something matters.”

DeerMate is an open-source project for making that workflow practical: a private assistant that remembers your preferences, delegates to specialist agents, follows long-running work, and returns evidence you can inspect.

It builds around **DeerFlow**, with a **Go main/management backend**, Go user/login and frontend APIs, and a Python execution worker, provider-specific session adapters, and optional browser or desktop tools. **Hermesh is an optional bridge**, rather than a required Go service. This repository is an independent project; the upstream projects are not affiliated with it.

<a id="research"></a>

## Research focus: a persistent secretary across agent sessions and machines

DeerMate studies how a private assistant can maintain ongoing work across isolated agent sessions, changing event streams and user-owned machines. The research target is a system that preserves the identity and authority of each task, recovers evidence after failures, and uses human attention deliberately.

Our contribution target is an executable systems design, explicit invariants and reproducible evaluation. The design builds on the [DSH Super-agent Router/Worker model](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/8c32a9dc5d72c033816c6a8110b37f40cf94fba4/docs/004-prompts.md) and [context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents). DeerMate applies these ideas to a Go-controlled, self-hosted assistant that preserves native coding sessions and independently collected execution evidence.

**M4.5 Alpha architecture — implementation available; no comparative Router benchmark yet:**

```mermaid
flowchart TD
    U[User requests] --> G[Go: durable inbox, policy, budget and admission]
    S[GitHub and task events] --> G
    G -->|New or unassigned work| R[Router: persistent DeerFlow secretary]
    R -->|Dispatch or follow-up proposal| G
    G -->|Admitted work and bound-thread input| W[Independent task Worker sessions: Codex first]
    W -->|Evidence, result or handoff| G
    G -->|Decision needed or final result| R
    G --> H[Workspace and work history]
```

The **Router** coordinates work and communicates with the user. It dispatches asynchronously and can handle another request while a Worker runs. Known thread events pass through Go's checks to their existing Worker; a Worker hands an out-of-scope request back for routing. **Go** owns durable state and enforces admission, while each **task Worker** retains its own execution conversation and native session. The Alpha limits Native concurrency to one for a small deployment; coordination remains asynchronous.

| Research question | Design under study | Planned measurements |
| --- | --- | --- |
| Can a secretary stay responsive while work continues? | Isolated Router/Worker roles, asynchronous reports and subscribed-thread pass-through | Foreground response p50/p95, routing-model calls, backlog and completed work |
| Can proactive work remain within granted authority? | Host-enforced scope, versioned rules and `off / observe / auto` modes | Unauthorized admissions, wrong-task attachments, decision provenance and model requests |
| Can task identity survive interruptions? | One native session per execution chat, durable operations and uncertain-outcome reconciliation | Duplicate native roots, replayed side effects, recovery outcomes and cases needing a person |
| Can memory recover the relevant evidence within a budget? | Bounded work→event→session→evidence references alongside personal memory | Correct source retrieval, context size, read latency and stale/unauthorized disclosure cases |
| Can the system reduce supervisory effort? | Structured attention, evidence-based completion and quiet routine updates | Human interventions per completed task, missed actionable issues and notification volume |

Planned evaluations compare a single-session coordinator with equivalent background tools, Router/Worker with all events routed, and Router/Worker with thread pass-through. Ablations examine reference recall and routing separately, using the same event traces, model versions, budgets and Worker limits. Results should report latency, completion evidence, model usage and failure outcomes together.

We plan to publish replayable synthetic event traces, fault-injection cases, pinned configurations and sanitized receipts. Existing [verification artifacts](docs/verification/README.md) establish scoped component/integration behavior; they are not comparative Router results. The new design has **23 pending acceptance criteria** and no claimed performance gain.

[Read the spec](docs/specs/m4-continuous-agent.md) · [Implementation and evaluation plan](docs/specs/m4-continuous-agent-plan.md) · [Accepted architecture decision](docs/decisions/0015-continuous-agent-control-plane.md)

## See the idea

[![Play the DeerMate concept video — simulated workflow, not a live demo](docs/assets/concept-preview.gif)](https://github.com/mzydmer/deermate/blob/main/docs/assets/deermate-concept.mp4)

**[▶ Watch the 24-second concept video](https://github.com/mzydmer/deermate/blob/main/docs/assets/deermate-concept.mp4)** · [Download MP4](https://raw.githubusercontent.com/mzydmer/deermate/main/docs/assets/deermate-concept.mp4) · [Storyboard and reproduction](docs/media.md)

The film illustrates an intended handoff: one request → role-based routing → work on your own machine → an independent review → a result with a diff and test evidence. It remains a motion storyboard. Actual execution evidence is recorded separately in the verification receipts linked below.

## Run the local worker

Python 3.11+, Git, and macOS or Linux are required. Codex must be installed and authenticated separately.

```bash
git clone https://github.com/mzydmer/deermate.git
cd deermate
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp examples/local-worker.toml deermate.toml
```

Edit `deermate.toml` to register a trusted repository and its validation command, then run `deermate serve`. In another terminal:

```bash
deermate doctor
deermate submit --project demo --key first-task --prompt 'Investigate and fix the bug.'
deermate status TASK_ID
deermate events TASK_ID
deermate diff TASK_ID
```

Replace `TASK_ID` with the submission's returned ID. The service binds to `127.0.0.1` and creates a local bearer token. It is not a remotely exposed production service. [Full setup, cancellation, recovery, and verification →](docs/local-worker.md)

To connect a trusted DeerFlow process on the same host, install `.[mcp]` and configure its background task tools using the [DeerFlow guide](docs/deerflow.md) and [example configuration](examples/deerflow.extensions.json). The additional read-only `check_worker_connection` tool checks the configured connection without submitting work. The Worker runs independently of the MCP process. A real model has selected MCP tools through the normal run API, completed a real local Codex repair and delivered its notification. See [live acceptance](docs/secretary-acceptance.md). A historical, separately approved temporary cloud-to-home link also passed real model/Codex dispatch, independent validation, notification and nine OpenSSH policy checks ([receipt](docs/verification/home-link-2026-10-28.json)); that grant has expired. The newer [device authorization and outbound HTTPS path](docs/agent-authorizations.md) has separate local acceptance; deployment and live-device results are tracked in STATUS.

Run `deermate --config controller.toml --worker home doctor` before dispatching to an enrolled home Worker. It checks credentials, pinned identities and protocol, returns sanitized JSON and exits nonzero when blocked. A reachable API does not establish native-agent login, capacity or project authorization. See the [SSH setup and preflight guide](docs/ssh-worker.md).

**Follow up with the same Codex:** an optional chat tool and child-task API preserve the native session/workspace and each round’s evidence. Worker/MCP/SSH, pinned Gateway and a real cloud-to-home three-round conversation are verified, with independent validation and delivered notifications ([receipt](docs/verification/codex-conversation-live-2026-10-29.json)). [Setup and limits](docs/codex-conversation.md).

**Public research tools:** minimal deployments now include public search and page reading. The **Tools & connections** page inspects loaded tools and tests saved MCP connections by discovering tool names without executing them. GitHub, Notion and SQL still require a service and authorization; catalog entries are not connected accounts. [Usage and limits](docs/tools-and-connections.md).

**One chat, one coding session:** registered Codex requests bind once and follow up in the same native session/workspace. Concurrent or uncertain submissions cannot create a replacement session. Conversations are named from their first message and remain editable. Claude execution is a future adapter. [Usage and rollout](docs/chat-sessions.md).

## What we are building

For a directly reachable SSH Worker, install `.[mcp,ssh]`, fill in [enrollment](examples/ssh-controller.toml), and run `deermate --config controller.toml --worker home mcp` or existing CLI commands. The [SSH guide](docs/ssh-worker.md) covers host trust, credentials, expiry and bound handles; each additional device/account/network deployment needs its own enrollment and acceptance.

**Run the backend demo:** [one-command walkthrough](docs/demo.md) · [captured event replay](docs/assets/gateway-ssh-demo.html) · [21-check receipt](docs/verification/gateway-ssh-2026-10-25.json). It exercises the actual Gateway → MCP → SSH → Worker path, including repair, validation failure, restart, reconnect and revocation. Download the HTML to replay it locally. Generated keys, same-host processes and an offline native fixture keep its scope explicit; the concept video above remains simulated.

**Run the full local Docker profile:** [startup, login and real Codex verification](docs/local-docker.md) · [retained live receipt](docs/verification/local-docker-2026-10-26.json). On the tested Mac it serves `http://localhost:2026`; a generated private owner password and named volumes preserve account/task state. No cloud key is needed. Fresh profiles leave the model empty; existing managed models can be configured separately.

**DeerMate workspace:** the default address opens the protected secretary home, with real recent tasks, a validation-evidence drawer, account-scoped draft handoff, accessible motion and an original Lottie mark. See [frontend source and checks](frontend/README.md). Specialist routing and browser chat input/streaming acceptance remain separate.

**Deploy the control plane to Alibaba Cloud ACK:** [quick deployment guide](docs/ack-deployment.md). Python scripts build ACR images and install the pinned DeerFlow Helm chart with private access, persistent cloud-disk state and optional enrolled home Worker. Actual cluster installation and cloud-to-home acceptance remain operator-specific.

**Lowest-cost personal trial:** the optional [single-host Docker bundle](docs/single-host.md) uses four prebuilt images, one server and local disks, without managed Kubernetes or a load balancer. An actual 2 vCPU/2 GiB SWAS host passed bounded HTTP/browser checks and a controlled reboot; model and home Worker workloads remain separate ([receipt](docs/verification/single-host-cloud-2026-10-27.json)). Go authentication and management remain in place; initial access uses a localhost SSH tunnel. The optional [public IPv4 HTTPS profile](docs/specs/single-host-public-ip.md) passed account migration, trusted certificate, login and host reboot checks on a small Singapore node ([receipt](docs/verification/single-host-public-ip-2026-10-27.json)); the private default is retained.

| Capability | Intended experience | Status |
| --- | --- | --- |
| A persistent secretary | One conversation for goals, preferences, handoffs, and follow-ups | M4.5 Router/Worker spec and plan proposed; review pending |
| Specialist routing | Choose an eligible agent by role, project, device availability, and budget | Host-bounded Router design proposed; Codex first |
| Home and cloud workers | Run bounded work on machines you own; show offline devices explicitly | Historical temporary link verified; user-managed pairing/HTTPS locally verified |
| Durable sessions | Local start/status/events/interrupt/resume; idempotent submission and explicit restart recovery | Local implementation |
| Repository maintenance | Triage issues, prepare fixes, collect CI evidence, and request independent review | Planned |
| Research watchlists | Track changes, keep citations, compare snapshots, and surface meaningful updates | Planned |
| One work dashboard | Secretary home, bounded real task list, status filters and validation evidence | First read-only view implemented; device liveness and task controls pending |
| Browser and desktop tools | Use a browser or a dedicated desktop session when the job needs an interface | Optional; planned |

“Private” means you choose where DeerMate stores and runs its own services. Sending a prompt to a cloud model still discloses that prompt to the model provider. Open-source software also does not make model usage or hosting free.

## How it fits together

```mermaid
flowchart TD
    You[You] --> UI[DeerMate React workspace]
    UI --> Go[Go main API, login and management]
    Go --> Runtime[Private DeerFlow Agent runtime]
    Runtime --> Tasks[Python MCP and durable task tracking]
    Tasks --> Link[Registered transport: outbound HTTPS or SSH]
    Link --> Worker[Python Worker on your machine]
    Worker --> Codex[Codex app-server]
    Worker --> Results[Diff, tests and native session evidence]
    Results --> Runtime
    Go -. proposed M4.5 .-> Routing[Persistent Router and event-driven work]
    Routing -. planned .-> Other[Claude, DeepSeek, research and desktop adapters]
    Tasks -. optional, planned .-> Hermesh[Self-hosted Hermesh bridge]
```

The backend follows the owner’s updated **Go control plane + Python Agent runtime/Worker** direction:

| Component | Proposed implementation | Responsibility |
| --- | --- | --- |
| Secretary | DeerFlow integration | Conversation, planning, memory, and delegation |
| Main and management backend | Go `net/http` | Frontend API boundary, workspace summary, users/roles, sessions, CSRF and audit |
| Persistence | SQLite initially; PostgreSQL when needed | Task/session mapping, event cursors, and recovery records |
| Remote worker | Python asyncio | Bounded subprocess execution and local artifact collection |
| Private link | Outbound HTTPS connector or optional AsyncSSH | User-managed device grants or explicitly enrolled SSH; local HTTPS and historical SSH evidence have separate scopes |
| Agent adapters | Python wrappers for each supported interface | Normalize native agent lifecycle and output |
| UI | Reuse DeerFlow first; add task cards | A single place to follow the work |

External agents may require Node.js, Rust binaries, macOS tools, or paid subscriptions. Go owns the public API/auth boundary; DeerFlow and Worker/MCP/SSH retain Python. Docker builds Go automatically; native backend development uses Go 1.27.3.

See [Go backend / API guide](backend/README.md), [architecture](docs/architecture.md) and [ADR 0007](docs/decisions/0007-go-control-plane.md), which supersedes the original Python-only control-plane choice. The SSH path does not implement or claim wire compatibility with Hermesh.

## Connect your agents

The Codex native app-server adapter is implemented locally. The remaining adapters are planned and require their own compatibility validation.

| Agent or tool | Planned integration | Upstream interface |
| --- | --- | --- |
| Codex | Persistent sessions and streamed events | [Codex app-server](https://developers.openai.com/codex/app-server) |
| Claude Code | Structured design/development runs | [Programmatic CLI / Agent SDK](https://code.claude.com/docs/en/headless) |
| DeepSeek Harness | A persistent ACP session | [`dsh --profile acp`](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/bundle/acp-app) |
| Qoder | An ACP adapter after compatibility checks | [Qoder CLI](https://docs.qoder.com/release-notes/qoder-cli) |
| Other ACP agents | Capability-negotiated adapter | [Agent Client Protocol](https://agentclientprotocol.com/) |
| Hermesh | Optional CLI bridge for existing installations | [Hermesh](https://github.com/hermeshai/hermesh) |
| Web applications | An optional browser tool | [Playwright MCP](https://github.com/microsoft/playwright-mcp) |
| macOS applications | An optional desktop tool on a dedicated session | [Peekaboo](https://github.com/openclaw/Peekaboo) |

**A model is not an agent adapter.** Using a DeepSeek model inside DeerFlow is different from delegating to a running DeepSeek Harness. Likewise, a Claude API call is different from a Claude Code session.

Grok Bot and Muse are possible external clients or collaborators, subject to the interfaces their products expose. An assistant being able to call our MCP tools does **not** establish that DeerMate can wake, control, or cancel that assistant. They are not required for the initial system.

User-managed device enrollment is locally verified; follow the [authorization guide](docs/agent-authorizations.md) and check STATUS for deployment scope:

1. Start pairing from **Agent authorization** and run its short-lived pairing command on the device.
2. Run the local Worker and the outbound HTTPS connector; no public Worker port is needed.
3. Choose projects, operations, duration and the policy for work already running at expiry.
4. Confirm that exact authorization version locally. Keep native-agent authentication on the device.
5. Check connection and authorization separately before submitting work. A connection check runs no Native task.

Direct SSH implementation and provisioning are documented in [the SSH guide](docs/ssh-worker.md). Local setup uses the [worker guide](docs/local-worker.md) and [TOML example](examples/local-worker.toml). The [broader YAML example](examples/deermate.example.yaml) remains design-only. Install from this repository; a package named `deermate` on a registry is not claimed to be this project.

## Autonomy with explicit boundaries

The target is unattended work within permissions you set in advance. The proposed rules live at the tool and worker boundary, beyond the model prompt:

- **Separate capabilities:** research can read sources; a code worker can edit an allowed workspace; publishing or sending mail needs its own grant.
- **Separate execution:** different worktrees prevent overlapping edits; OS accounts, containers, or VMs provide isolation. A worktree alone is not a sandbox.
- **Recover deliberately:** reconcile an existing task before retrying; do not assume a timeout means the action never happened.
- **Preserve evidence:** keep session IDs, task state, event cursors, diffs, test receipts, and source links.
- **Bound the work:** task limits, concurrency limits, expiry, and cancellation are first-class design requirements.
- **Treat outside text as data:** an issue, email, web page, or another agent's result cannot grant additional authority.

**Encryption status:** SSH uses pinned host identity; the outbound HTTPS path uses the existing trusted service and locally confirmed grants. The cloud application and execution endpoints can read task plaintext. Historical live SSH evidence and local HTTPS authorization evidence have separate scopes; no independent audit is claimed. Hermesh has its own trust boundary. See [security](docs/security.md), [device authorization](docs/agent-authorizations.md) and [SSH revocation](docs/ssh-worker.md).

## Development status

We track delivered work separately from planned functionality. Delivered scope includes **M4.4c–e personal focus and home actions**, implemented on the Go backend and shared design system, locally verified and deployed to the existing Singapore single-host installation. See the [personal home guide](docs/personal-home.md) for followed conversations, evidence-based focus, read-only follow-ups and opt-in goal suggestions. Semantic extraction, automatic merging, shared projects and budgeted model jobs remain planned.

**M4.5 persistent Router/Worker coordination** is implemented as a default-off Alpha. See the [usage and setup guide](docs/continuous-secretary.md), [progress](docs/STATUS.md) and [local evidence](docs/verification/continuous-secretary-2026-11-04.json). User-managed Agent authorization has its own [local acceptance receipt](docs/verification/agent-authorization-local-2026-11-03.json). Local evidence does not establish a deployed M4.5 Router or a comparative benchmark result.

| Milestone | Deliverable | State |
| --- | --- | --- |
| M0 | English/Chinese README, architecture, security boundaries, contracts, concept film | In this repository |
| M1 | Local Python worker + Codex adapter + one verified task lifecycle | Implemented locally; see verification scope |
| M2 | DeerFlow tools + remote worker + restart/reconnect reconciliation | Historical MCP/SSH link verified; user-managed pairing/HTTPS locally verified; live expiry observation remains separate |
| M3 | Claude/ACP adapters + independent review + GitHub maintenance workflow | Planned |
| M4 | Secretary workspace, Go main/management APIs, shared design system | Workspace implemented; user-managed execution grants locally verified; watchlists/mail planned |
| M4.4a | Personal settings, explicit memory CRUD, scoped FTS5 recall and chat injection | Locally verified and cloud-deployed; memory defaults off |
| M4.4b | Opt-in explicit chat memory requests, canonical source links and revocation | Locally verified and cloud-deployed; no extra extraction-model calls |
| M4.4c–e | Persistent personal focus, task evidence, goal suggestions and admitted home actions | Cloud home/API verified; action tests use local synthetic models; new home Native entry still needs live acceptance |
| M4.5 | Persistent Router, isolated Worker sessions, event pass-through, bounded recall and admission | Opt-in Alpha; local fixtures verified, full live/UI criteria and comparative evaluations pending |
| M5 | Optional Hermesh bridge + desktop execution + broader ecosystem adapters | Planned |

**Verified so far:** a real Codex repair in a disposable repository returned a patch and an independently executed passing test. A live interruption and continuation preserved the same native session. Offline protocol tests cover idempotency, restart recovery, input handling, deadlines, and denied permissions. Native session IDs and policy snapshots persist in SQLite. In-flight work after restart requires explicit recovery; it is never automatically replayed. See [verification and current limits](docs/local-worker.md).

Historical M2.1 verification had 51 passing normal tests (two opt-in upstream checks skipped), a passing ordinary-driver probe and a separately passing actual Gateway/SQLite process-restart verifier with 14 recorded checks. That backend check used a model-free submit entry and offline native fixture. Current evidence, including local browser login and real Codex, is tracked in [STATUS](docs/STATUS.md).

No release dates or production-readiness claims are promised. [Detailed roadmap and acceptance criteria →](docs/roadmap.md)

The implementation acceptance at `701a309` recorded **244 passed, 9 opt-in cases skipped**, 41 pinned provider/graph/source/home checks, 43 actual Go/Gateway API checks, 14 browser checks and 27 deployment/overlay checks using synthetic data and an offline Fake conversation model. That suite was not rerun for the cloud rollout. The [cloud upgrade receipt](docs/verification/personal-home-cloud-2026-11-03.json) records **25 public HTTPS/API checks and 8 browser checks**, preserved existing accounts/history/model files, and healthy running services. Temporary deployment SSH was revoked and a new connection denied; the expired home-agent grant was not renewed. No real model/native tasks or load test were started during this upgrade. Historical cloud-to-home Codex evidence retains its original scope; see [STATUS](docs/STATUS.md) and the [local home receipt](docs/verification/personal-home-2026-11-02.json).

Track the first implementation milestone: [Python worker + Codex session lifecycle · #1](https://github.com/mzydmer/deermate/issues/1).

## Built with the open-source ecosystem

| Project | Intended relationship |
| --- | --- |
| [DeerFlow](https://github.com/bytedance/deer-flow) | Secretary foundation; reuse its conversations, skills, and existing task capabilities |
| [Hermesh](https://github.com/hermeshai/hermesh) | Design inspiration and optional bridge; its code remains independently maintained |
| [Codex](https://github.com/openai/codex) | A native coding-agent runtime connected through documented interfaces |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | An optional ACP worker runtime |
| [DSH Super-agent prototype](https://github.com/deepseek-ai/dsh-superagent-prototype) | Research reference for Router/Worker roles, subscriptions and observe mode; independently maintained |
| [AsyncSSH](https://github.com/ronf/asyncssh) | Implemented optional SSH transport; tested at 2.24.1; no custom cryptography |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | Implemented optional stdio bridge; tested with SDK 1.30.0 |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) / [Peekaboo](https://github.com/openclaw/Peekaboo) | Optional web and desktop capabilities |

This repository contains original design documents and media, not a vendored copy of these projects. Their licenses, support policies, model costs, and security boundaries remain their own. We do not claim endorsement, completed interoperability, or bundled third-party subscriptions.

**Frontend design:** All frontend changes follow [design.md](design.md), our Vercel/Geist-inspired neutral design system shared by React and Go management pages.

## Join the project

For agent-assisted development, start with [AGENTS.md](AGENTS.md). Follow the [product spec](docs/SPEC.md), [current development status](docs/STATUS.md), [evolution log](docs/EVOLUTION.md), and [architecture decisions](docs/decisions/README.md). The status page separates implemented, verified, merged, and released work.

Useful first contributions include SSH identity design, configured-model notification validation, native lifecycle coverage, and feedback on task recovery. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before starting a large change.

- [Open a design proposal](https://github.com/mzydmer/deermate/issues/new?template=design-proposal.yml)
- [Propose an integration](https://github.com/mzydmer/deermate/issues/new?template=integration-request.yml)
- [Read the roadmap](docs/roadmap.md)
- [Report a security concern](SECURITY.md)

## License

[MIT](LICENSE). Copyright © 2026 DeerMate contributors.
