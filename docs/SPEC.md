# DeerMate 基础规格

文档版本：0.1。更新：2026-10-25。本文记录产品行为与验收基线；当前交付状态以 [STATUS.md](STATUS.md) 为准，历史变化见 [EVOLUTION.md](EVOLUTION.md)。

需求编号在后续版本保持稳定。编号被替代时保留替代关系，不将旧编号重新分配给另一种功能。状态中的“已实现”只描述实现范围，不意味着已合并、发布或通过生产安全审计。

## 产品目标

用户通过一个私人秘书交代目标，由秘书选择获授权的专职 Agent，在用户自己的本地或云端机器完成工作，并通过统一工作台返回进展、产物与可检查的证据。

默认技术方向：Go 主服务、管理服务、用户登录及前端 API；DeerFlow 为内部 Agent 运行时，现有 Python Worker/MCP/SSH 及会话适配层继续复用。用户本轮要求取代原 Python 控制端限定，见 [ADR 0007](decisions/0007-go-control-plane.md)。Hermesh 保持可选生态桥接。

## 角色与边界

| 角色 | 职责 |
| --- | --- |
| 用户/管理员 | 注册项目和设备、配置权限和验证命令、检查异常或结果 |
| 私人秘书 | 理解目标、规划和路由、跟踪任务、整理结果；不能通过提示词自行扩权 |
| 控制服务 | 接纳任务、检查策略、保存任务身份与状态、暴露受限工具接口 |
| Worker | 在获授权项目中启动执行者，维护原生会话，收集事件与产物 |
| 专职 Agent | 在被授予的能力范围内完成设计、实现、审核或调研 |
| 外部服务/模型 | 按其接口处理数据，保留自己的费用、权限和隐私边界 |

当前不承诺：无条件无人值守、任意网页可自动登录、默认访问所有私人数据、生产级多租户隔离、云模型无法读取提示词，或所有外部助手都能被反向唤醒。

## 功能需求

| 编号 | 需求与关键行为 | 实现阶段 |
| --- | --- | --- |
| FR-001 | 单一私人秘书入口，保留偏好和任务上下文 | MCP 接入与 ACK 的 DeerFlow 入口部署包已实现；真实模型选工具、通知和完整秘书体验待验收 |
| FR-002 | 只接受管理员注册的项目；请求不能任意指定主机路径、执行命令或扩展权限 | M1 已实现本地接纳 |
| FR-003 | 相同幂等键与相同请求返回已有任务；不同内容复用键返回冲突；继续操作也有独立幂等键 | M1 已实现 |
| FR-004 | 保存任务、原生会话、轮次与事件游标；支持查询、中断和继续同一会话 | M1 Codex 已实现 |
| FR-005 | 从项目已提交 HEAD 创建独立 worktree；保留原工作区；收集 tracked 与普通 untracked 文件的补丁 | M1 已实现 |
| FR-006 | Agent 原生轮次完成后独立运行管理员配置的验证命令，保存退出码与输出；缺少验证时不能宣称验证通过 | M1 已实现 |
| FR-007 | 服务重启保留任务与会话身份；先前运行中的任务进入显式恢复状态，不能自动重放副作用 | M1 已实现本地恢复 |
| FR-008 | 支持可识别的原生表单问题与回答；不支持的能力明确拒绝，不自动代替用户授权 | M1 已实现处理路径；表单路径仅离线验证 |
| FR-009 | 本地 API 具有 bearer 鉴权、Host/Origin 检查、请求体大小限制和受限查询分页 | M1 已实现 |
| FR-010 | 任务时限、并发限制、取消确认与异常输出处理；结果不确定时不能误报成功或停止 | M1 已实现本地范围 |
| FR-011 | 根据职责、项目权限、设备能力和在线状态筛选执行者，再进行专职路由 | M2–M3 规划 |
| FR-012 | 通过 Python MCP 工具接入 DeerFlow 后台任务跟踪，映射 submit/status/cancel 与结构化结果 | M2.1 已实现；M2.3 fixture 与 M2.5 容器/真实 Codex 链路通过；本地页面/登录通过，模型选工具和通知未验证 |
| FR-013 | 使用校验主机身份的 SSH 连接远程 Python Worker；定义密钥生命周期与断线恢复 | M2.2 已实现；M2.3 组合链路已验证 SSH 断线重连、撤权与取消；真实双机/OpenSSH 部署与 NAT 未验收 |
| FR-014 | GitHub 事件验签、去重、issue 修复和独立 PR 审核；创建 PR、评论、合并、发布分别授权 | M3 规划 |
| FR-015 | 竞品/资料 watchlist、历史快照对比、引用来源和有实质变化才通知 | M4 规划 |
| FR-016 | 按需浏览器和独立桌面会话；同一桌面会话不能被多个任务同时操作 | M4–M5 规划 |
| FR-017 | 邮件从单独授权的只读能力开始，发送权限独立控制 | M4 规划 |
| FR-018 | 工作台展示任务、执行者、设备、阶段、事件、产物与异常决策，并提供停止/继续入口 | M4.1 首个只读工作台：近期真实任务、状态筛选、摘要/独立验证与原记录；完整事件/设备探测和停止/继续入口待完成，见 [规格](specs/m4-workspace-refresh.md) |
| FR-019 | 外部助手作为客户端调用工具，与系统反向唤醒外部助手分别验证；不能由一种接入推断另一种已支持 | M5 规划 |
| FR-020 | 可选 Hermesh CLI 桥接，不要求 Go 后端，不承诺其底层协议兼容 | M5 规划 |

## M1 接口与任务契约

当前接口以 [api.py](../src/deermate/api.py)、[models.py](../src/deermate/models.py) 和 [CLI](../src/deermate/cli.py) 为实现依据。详细运行方法见 [local-worker.md](local-worker.md)。

| 操作 | 当前接口 | 关键约束 |
| --- | --- | --- |
| 存活检查 | `GET /health` | 不含任务内容，不要求 token |
| 能力查询 | `GET /capabilities` | 版本 1；持久 `instance_id`；`remote: false` 描述 Worker 自身的 loopback API |
| 提交/列表/查询 | `POST /tasks`、`GET /tasks`、`GET /tasks/{id}` | 已注册 project ID；幂等键必填；新任务 201，重复任务 200 |
| 事件 | `GET /tasks/{id}/events` | 按游标前进，分页返回；默认与上限均为 100 |
| 补丁 | `GET /tasks/{id}/diff` | 只提供已收集的结果；尚无证据时返回 409 |
| 取消 | `POST /tasks/{id}/cancel` | 请求与确认分离；排队任务可直接取消 |
| 继续 | `POST /tasks/{id}/resume` | 保留 native session；独立幂等键；不确定恢复需要显式确认 |
| 回答问题 | `POST /tasks/{id}/input` | 仅对应存活的受支持表单请求 |

除 `/health` 外，上述业务接口均要求本地 bearer token。当前服务只监听 loopback，不是远程安全网关。

提交内容包含 `project_id`、`prompt` 和 `idempotency_key`。管理员配置的 root、Agent 命令、验证命令与权限来自配置文件，而非模型生成的请求。任务接纳时记录策略快照；运行前策略发生变化则拒绝静默执行。

### 状态语义

完整状态集合见 [State](../src/deermate/models.py)。

| 状态 | 必须表达的含义 |
| --- | --- |
| `queued` / `starting` / `running` | 排队、准备或正在执行；不能据此声明完成 |
| `input_required` | 原生会话中有可处理的待答问题 |
| `cancelling` | 已发出取消请求，尚未确认停止 |
| `cancelled` | 排队任务取消，或执行中断/自有进程停止已确认 |
| `completed` | 原生执行完成、证据收集成功且配置的验证命令返回零 |
| `needs_review` | 没有验证命令、发生权限拒绝或存在需检查的晚到取消 |
| `failed` | 执行、验证、配置、证据收集或时限失败 |
| `recovery_required` | 重启/中断留下不确定结果，未自动重放 |

验证命令返回零只是一条执行记录，不保证测试数量、测试独立性或语义正确性。Agent 可能修改项目中的测试；更强的验收与独立审核属于后续工作。

## 非功能约束

| 编号 | 约束 | 当前边界 |
| --- | --- | --- |
| NFR-001 | 主后端、管理后端、用户登录及前端 API 使用 Go；Python 运行时与 Worker 为明确集成边界 | 迁移见 [专项规格](specs/go-control-plane.md)；原 Python-only 控制端约束已被用户取代 |
| NFR-002 | 不自创加密协议；明确加密端点与中继是否能读明文 | 直接 AsyncSSH 已实现，SSH 两端可读明文；Hermesh MCP 网关可读取其会话；无审计或中继部署声明 |
| NFR-003 | 在模型提示词之外接纳权限，使用明确执行边界 | M1 仅可信本地项目；无多租户/生产隔离承诺 |
| NFR-004 | 正常测试不需要模型凭据；真实模型测试明确标识并限定范围 | 离线协议 fixture、临时 Git 仓库和 opt-in live smoke 已具备 |
| NFR-005 | 保存可复核的状态、事件、补丁和验证记录 | Worker 本地 SQLite；本地 Docker 命名卷与 Gateway 重启保留结果已验证；ACK 云盘实际部署待验收；无总容量配额或通用脱敏保证 |
| NFR-006 | 区分实现、验证、合并和发布，维护可接续文档 | 以 STATUS、EVOLUTION、ADR 和 Git/CI 证据管理 |
| NFR-007 | 明确平台范围与运行限制 | Worker 支持 macOS/Linux、Python 3.11+；ACK 脚本 Python 3.12+ / Helm 3.18+（3.x），快速配置面向普通 ECS 节点；本地 Compose 编排要求 Mac/Python 3.12+，实测 Intel Docker Desktop；暂不支持 Windows |
| NFR-008 | 所有前端遵循统一 Vercel/Geist 风格规范与可访问性基线，React/Go 共用视觉 token | [design.md](../design.md) 为规范；token 同步/CI 检查，现有页面按修改范围迁移 |

## 验收与证据映射

| 验收编号 | 可观察结果 | 当前证据 |
| --- | --- | --- |
| AC-M1-01 | 幂等键跨服务/存储重启仍返回同一任务；冲突不会创建第二份工作 | [test_store.py](../tests/test_store.py)、[test_api.py](../tests/test_api.py) |
| AC-M1-02 | 修复任务返回 native session、diff 和独立验证输出，原 checkout 保持不变 | [test_worker.py](../tests/test_worker.py)、[live_smoke.py](../scripts/live_smoke.py) |
| AC-M1-03 | 中断与继续复用同一 native session | worker 离线测试及 `live_smoke.py --live --lifecycle` 的既有本地验证记录 |
| AC-M1-04 | 重启后的运行中任务要求显式恢复，不自动创建新原生会话 | store/worker 恢复测试；硬崩溃与跨机器恢复尚未实测 |
| AC-M1-05 | 验证失败、无验证、权限拒绝、超时、异常协议不能伪装成验证成功 | [test_worker.py](../tests/test_worker.py)、[test_rpc.py](../tests/test_rpc.py) |
| AC-M1-06 | 无 token、非本地主机、浏览器来源、超大请求或任意执行命令被拒绝 | [test_api.py](../tests/test_api.py) |
| AC-M2-01 | DeerFlow 提交后返回稳定任务 ID，后台查询与取消不依赖模型记忆 | 本地及 SSH 两种实际 Gateway 路径通过：SQL/进程重启、原始查询/取消、Worker 失联恢复；模型选工具由测试入口代替，见[M2.3](specs/m2-gateway-ssh-demo.md) |
| AC-M2-02 | 远程断线、重连、撤权和取消状态真实可见，未知副作用不重放 | SSH 协议及完整 Gateway 链路的同机 fixture 范围通过；撤权后不假称已取消、恢复授权后确认先前取消，且无新原生会话/轮次；真实双机/OpenSSH/NAT 待验收，见[M2.2](specs/m2-ssh-worker.md)与[M2.3](specs/m2-gateway-ssh-demo.md) |
| AC-M2-03 | 本地容器服务可登录，经 SSH 调用真实 Codex 并返回独立验证；重启保留结果，重复请求不重复执行 | [M2.5 规格](specs/m2-local-docker.md)、[本地 Docker 指南](local-docker.md)、[真实验收收据](verification/local-docker-2026-10-26.json)；模型选工具由本地管理员/key 入口替代 |

上述文件是证据入口，不表示每项已覆盖所有边界。当前跑过哪些命令、对应哪个代码版本，以 [STATUS.md](STATUS.md) 为准。

M2.1 的具体映射、取消确认预算、错误与结果边界见[功能规格](specs/m2-deerflow-task-bridge.md)；配置步骤见 [DeerFlow 接入指南](deerflow.md)。桥接仅暴露 `submit_task`、`get_task_status`、`cancel_task`，不直接读取数据库或持有执行进程。表单、review 和 recovery 映射为需要处理的状态，继续使用既有本地 CLI 完成决策。

M2.2 将同一 API 通过管理员注册的 SSH 连接使用；远程 MCP 句柄为 `instance_id:task_id`，本地 ID 不变。所有操作先检查注册权限与 Worker 身份，撤权不代表已接纳任务停止。配置、轮换和撤权窗口见 [SSH 指南](ssh-worker.md)与 [ADR 0004](decisions/0004-ssh-loopback-transport.md)。

## 变更管理

行为变化先更新相关需求/验收；跨服务功能使用[变更规格模板](specs/TEMPLATE.md)。重要架构选择写 ADR，完成阶段更新 STATUS 和 roadmap，重要结果追加到 EVOLUTION。不要用新增文档替代实际验证，也不要把模型输出当作合并或发布凭证。
