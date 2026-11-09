# Roadmap and acceptance criteria

Status: M1–M2.5, M4.1 workspace, Go control plane and shared design language implemented; single-host public IP HTTPS verified. Worker preflight and a real three-round cloud-model/home-Codex conversation verified over an approved temporary reverse SSH link; general enrollment and actual expiry observation remain pending. Updated: 2026-11-04. This is a sequence of acceptance targets, not a delivery schedule.

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

- [x] Enforce one registered coding session per chat incarnation, automatic first-message naming and rename preservation; offline graph, Gateway local/SSH, real cloud Codex continuation and browser naming/inspection verified. Claude remains a future adapter; see [spec](specs/m2-chat-session-binding.md).

- [x] Enable public research tools and inspect saved MCP connections without executing tools; pinned runtime, public-provider smoke, real cloud model calls and browser connection test passed. Private data accounts remain unconfigured; see [tooling spec](specs/m2-tools-and-connections.md).

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

- [x] Add child tasks for follow-up questions in the same Codex session/workspace, preserving parent evidence; scoped provider and actual Gateway/SSH fixture verified ([guide](codex-conversation.md)).
- [x] Verify real cloud model-selected three-round context and delivered notifications on the existing temporary deployment ([receipt](verification/codex-conversation-live-2026-10-29.json)); original lease remains unchanged.

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

## M4.4 — Memory-backed personal secretary home（In progress）

用户已同意开始实施 [spec](specs/m4-personal-memory-briefing.md)。[个人记忆基础](personal-memory.md)与[个人范围的确定性首页闭环](personal-home.md)已本地验收，并于 2026-11-03 UTC 升级既有新加坡单机；[云端收据](verification/personal-home-cloud-2026-11-03.json)包含 25 项 HTTPS/API 与 8 项页面检查。完整语义采集/模型作业仍待实施。

[技术原型与六张关键流程/状态图](specs/m4-memory-technical-design.md)保留完整目标；本阶段的 Go 持久投递、个人事实屏障与召回不代表自动提取队列已经接入。

- [x] M4.4a: personal display name/timezone, explicit personal facts, correction/forgetting, FTS5 recall and a locally verified DeerMem adapter. Personal scope only; deployed to the existing cloud host with memory features still opt-in.
- [x] M4.4b: opt-in explicit personal memory requests from newly admitted chats, source identity/recency, daily limits and source invalidation. No extraction-model calls.
- [ ] Semantic automatic extraction/merging, project scopes and reliable model-job budgets.
- [x] Explicit personal attention topics with source/incarnation versions, pause/read/snooze controls and no recent-20 cutoff.
- [ ] Bounded history import and cross-topic semantic merging.
- [x] Deterministic personal focus with actual task evidence/freshness, goal-based explained suggestions and empty/error states.
- [x] Admitted read-only follow-up and previewed new-topic creation over the real local API/UI; one-round existing Codex continuation and lost-ack fencing covered with a pinned Submitter fixture.
- [ ] Verify the new home continuation entry through a real Go→Gateway→Worker/native run.
- [x] Source/goal cache invalidation, persisted intent restart reconciliation, zero summarization calls on reads and synthetic owner/UI isolation acceptance.
- [ ] Budgeted model-job generation, real-provider quality and 2 GiB host load acceptance.

First release uses existing owned conversations/tasks. Authorized external-source tracking follows separately. Design rationale: [ADR 0013](decisions/0013-memory-backed-personal-briefing.md).

## M4.5 — Continuous work and event-driven secretary（Accepted，实施中）

[功能 spec](specs/m4-continuous-agent.md) · [实施 plan](specs/m4-continuous-agent-plan.md) · [ADR 0015](decisions/0015-continuous-agent-control-plane.md)。用户已批准开发，P0–P6 Alpha 已实现，以下复选框表示阶段验收而非代码是否存在；不替代 M4.4 尚未完成的语义提取等范围。[当前证据与限制](STATUS.md)。

- [x] 用户审核 spec / plan；2026-11-03 明确批准开始开发。
- [ ] P0–P2：固定 Router/Worker 工具边界、Go inbox/工作/事件账本、非阻塞派单与原会话回执核对。
- [ ] P3–P4：单仓库 GitHub observe、已关联 Thread 直通/交回、有界引用召回和本人关键词查询。
- [ ] P5：统一秘书入口、持续工作详情及待处理界面。
- [ ] P6：本人启用的有界 auto、预算、背压和程序监测。
- [ ] P7：有限实机、低内存/升级回退、实际交付与脱敏收据。

P5 已补真实 Chrome 390/1280/1440px、浅深色、键盘/减少动态、工作草稿隔离、普通账号隔离、局部读取失败/过时/恢复；[独立 UI 收据](verification/continuous-ui-2026-11-04.json)。来源候选等完整矩阵尚未通过，不据此勾选整个阶段。

P7 已完成既有单机应用发布、数据备份/保留和 27+17 项公网回归；[上线收据](verification/continuous-cloud-2026-11-04.json)。用户开关仍关闭、自动预算 0；实际第三方/Native、线上视觉与完整阶段验收仍待完成。

## M5 — Extend the ecosystem

- [ ] Add an optional Hermesh CLI bridge; keep its separate upstream implementation optional.
- [ ] Add a browser tool and a dedicated-session macOS desktop adapter.
- [ ] Validate third-party assistant interfaces before claiming inbound/outbound integration.
- [ ] Publish an adapter compatibility matrix with versions and reproducible evidence.
- [ ] Review release operations, backup/restore, upgrade compatibility, and security readiness.

## Contribution priorities

Prioritize bounded SSH enrollment, worker contract review, and configured-model notification verification before expanding adapters. Do not mark a feature supported solely because the upstream project advertises the capability.

## 产品文档中心

- [x] 登录页与工作台提供「产品文档」入口，独立 `/docs` 分流使用指南、技术方案与变更日志。
- [x] 版本化 Markdown 生成网页内容；检查目录、来源、链接及生成一致性。
- [x] AGENTS 文档影响规则、PR 模板与本地/CI 文档门禁。
- [x] 本地 TypeScript/生产构建、17 项文档/overlay 测试与静态文章/锚点检查。
- [ ] 恢复浏览器后补响应式、主题、键盘、搜索、复制与错误路径验收。
- [x] 发布到既有实例：文档前端及代理路由，最终 45 项公网与原账号检查通过，41 项固定部署/文档回归通过。
- [ ] 完成远端 CI 验收，并将 product-docs 设为合并必需检查。

详见[规格](specs/product-documentation.md)与[更新约束](DOCUMENTATION_POLICY.md)。


## Agent 授权产品化

- [x] 用户选择期限、范围与到期任务策略；Go 管理页面与状态详情。
- [x] 本机逐版本确认、取消申请、续期与撤销；Go/Worker 双向接纳。
- [x] 主动 HTTPS 连接与持久单次投递；本地跨运行时及过期/幂等测试。
- [x] 固定提交线上部署与 17 项 HTTPS API/页面交付检查；线上浏览器访问未获授权，视觉验收不标记通过。
- [ ] 开机守护、身份凭据定期轮换、后台提醒与共享设备授权。

## M4.5 — Persistent secretary Alpha

- [x] Implement default-off Go work/event/inbox/decision ledger and guarded runtime adapters.
- [x] Isolate persistent Router, no-tool Assessor and original native task sessions; preserve one chat/native root and operation reconciliation.
- [x] Add fixed-repository read-only observe, explicit acceptance, bounded opt-in auto, source invalidation and owner-scoped FTS/reference reads.
- [x] Add the protected secretary/work/source/rule interface and setup guide.
- [ ] Complete all CONT-01–23 end-to-end acceptance, including full mobile/accessibility/failure states and compatible rollback.
- [ ] Verify one separately configured live GitHub/model/Codex loop, then deploy with valid access.
- [ ] Publish R-EVAL-01–05 comparisons and ablations; local functional tests do not establish research gains.

[Implementation plan](specs/m4-continuous-agent-plan.md) · [Usage](continuous-secretary.md) · [Current evidence](verification/continuous-secretary-2026-11-04.json).

2026-11-04 用户要求取消秘书单独启用：交互与手动工作默认可用，沿用对话模型；设置集中管理本人记忆。见 [专项规格](specs/default-secretary-memory-settings.md)，实现/验收/发布在 STATUS 单独追踪，不改变既有后台/设备授权或整个 P7 验收状态。

- [x] 默认秘书/手动工作沿用对话模型，设置复用本人记忆管理；独立本地 API 与浏览器通过，[专项收据](verification/default-secretary-memory-2026-11-04.json)。云端交付独立记录。

默认交互与记忆设置已上线 `161fd29`，28+46+17 项公网回归通过；[上线收据](verification/default-secretary-memory-cloud-2026-11-04.json)。不据此标记真实闭环或 R-EVAL 完成。

### 设计系统门禁 · 2026-11-05

- [x] design.md 机器可读 tokens、产品/营销配方与共享生成资产。
- [x] 第一方产品页面与公共组件视觉迁移，前端构建前与 CI 静态门禁。
- [x] 真实Go登录后的主要页面/交互状态矩阵，六宽度与浅深色；运行时使用合成数据，范围见2026-11-06验收。
- [ ] 全面人工可访问性评审、真实运行时/供应方验收、远端必需检查及线上发布。

## Workspace v2 · 已批准并实施

- [x] 编写助手首页、默认自然记忆和原话题延续的 [PRD](prd/workspace-assistant-v2.md)，配八张静态样式图。
- [x] 根据用户反馈完成文案审稿；当前 PRD v0.3 已对齐最新设计规范。
- [x] 用户于 2026-11-09 确认连续开发、本地验收后推送并部署。
- [x] 定稿技术 spec / ADR 0016 / plan，映射 WS2-01–21。
- [x] 工作台 v2 的本地交付与既有云端验收；真实接入范围见下列专项收据。

### 工作台 v2 实现与验收（2026-11-09）

- [x] 按最新 design.md 对齐八张设计稿，记录用户连续开发授权。
- [x] 版本化默认、旧暂停保留、临时话题与范围、来源和遗忘屏障。
- [x] 普通表达快路径、有界持久整理、完整 Inbox 证明与最终 Router 注入。
- [x] 单输入助手首页、我的工作、关于你、来源抽屉与有依据的最多三项快照。
- [x] 真实供应方记忆闭环 16 项，独立真实 Codex 同根两轮；范围见专项收据。
- [x] 最终浏览器矩阵 33 项、旧镜像升级保留与本地全部门禁。
- [x] 应用 595f654 推送与既有云端升级，22 项 API、13 项浏览器及原账号/数据保留通过；见上线收据。
