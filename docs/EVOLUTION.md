# 项目演进记录

按事件追加项目的重要变化，保留当时的背景、选择、结果和证据。当前状态见 [STATUS.md](STATUS.md)，需求见 [SPEC.md](SPEC.md)。日期按项目记录日期，不把未来计划写成已经发生。

若历史记录有误，追加明确的修正及引用；不要悄悄将旧事件改写成当前结论。后续 commit 可以在合并时补上引用，但无需为了填写自身哈希反复提交。

## E-001 · 2026-10-25 · 项目定位与开源设计预览

- **背景：** 希望一个私人秘书能协调本地和云端 Agent，按职责派工，返回进展与产物。
- **结果：** 确定名称 DeerMate，建立公开仓库，提供中英文 README、架构、安全边界、接入契约、M0–M5 路线、贡献模板和概念视频。
- **交付：** [`9eb2079`](https://github.com/mzydmer/deermate/commit/9eb207939c4cabb0788001cf6424a948af3925b8)。此阶段交付文档与原创概念媒体，没有声称运行能力已经实现。
- **验证边界：** 视频使用模拟数据，不是 live 产品录屏；页面和媒体已检查。

## E-002 · 2026-10-25 · 选择 Python 自有后端

- **原因：** Hermesh 符合远程派工方向，但项目维护者希望后端使用 Python。
- **决定：** DeerMate 自有控制服务、Worker 和适配器使用 Python；计划用标准 SSH；Hermesh 保留为可选桥接，不移植或承诺兼容其底层协议。
- **依据：** [ADR 0001](decisions/0001-python-first.md)，随初始设计记录。
- **影响：** 需要独立完成会话、身份、恢复和远程安全设计，不能将 Hermesh 的能力算作默认方案已经具备。

## E-003 · 2026-10-25 · 建立首个实施目标

- **结果：** 创建 [Issue #1](https://github.com/mzydmer/deermate/issues/1)，定义 Python Worker 与 Codex 单任务生命周期的验收标准，并链接到 README 与 roadmap。
- **交付：** [`e9f228d`](https://github.com/mzydmer/deermate/commit/e9f228dbc443422490cb74c7f695bf24d3e9d360)。
- **影响：** 将大范围私人助手愿景拆为先证明本地任务，再扩展远程与秘书入口的顺序。

## E-004 · 2026-10-25 · M1 本地 Worker 与 Codex 适配

- **结果：** 实现 Python API/CLI、SQLite 任务、幂等提交、Codex 原生会话、worktree、补丁与独立验证记录、取消和继续、显式重启恢复，以及本地接纳边界。
- **关键选择：** 保存原生会话身份；不确定任务不自动重放；无验证或能力被拒绝时要求检查，不将模型文字当作验收证据。见 [ADR 0002](decisions/0002-durable-local-tasks.md)。
- **代码基线：** [`7dfe34a`](https://github.com/mzydmer/deermate/commit/7dfe34ac610a4f2ecd600ab77d28432786916b6a)，分支 `feat/m1-local-worker`。
- **验证：** 18 项离线测试、Ruff 与 wheel 构建通过；[GitHub CI](https://github.com/mzydmer/deermate/actions/runs/40175946902) 的 Ubuntu/macOS 两组通过。真实 Codex 完成临时修复、独立测试与 diff；真实中断和继续保留同一原生会话。
- **证据范围：** 本地 live 测试环境和结果记于 [local-worker.md](local-worker.md#verification)；临时原始记录未保存在仓库。远程、硬崩溃恢复、完整秘书和仪表盘不在本次验证范围。
- **交付状态：** 已推送开发分支；未合并主线、未发布包。PR 创建遇到连接器写权限与浏览器操作问题，不影响代码和既有 CI。

## E-005 · 2026-10-25 · 建立 Agent 接续与规格追踪

- **原因：** 已有 roadmap、架构和操作文档，但缺少统一的 Agent 入口、稳定需求编号、当前交付快照和演进记录。
- **结果：** 增加根目录 [AGENTS.md](../AGENTS.md)、[SPEC.md](SPEC.md)、[STATUS.md](STATUS.md)、本演进日志、决策索引、已有 M1 决策记录和[变更规格模板](specs/TEMPLATE.md)。README、贡献指南和 PR 模板提供接续入口。
- **范围：** 只补文档与协作规则；运行代码基线仍为 `7dfe34a`。本次文档提交是该事件的版本化交付记录。
- **验证：** 本次检查本地文档链接、规格编号与测试/源码映射，并核对远端主线和 PR 状态；不将旧测试或 CI 声称为本次重新运行。
- **下一步：** 优先推进 M2.1 的 DeerFlow 后台 MCP 契约，之后再做 SSH 远程边界。

## E-006 · 2026-10-25 · 本地 Python MCP 与 DeerFlow 驱动兼容

- **目标：** 推进 FR-012 / AC-M2-01，使秘书连接能够提交持久任务，在连接重建后查询同一个 Worker 任务。
- **结果：** 新增独立于执行进程的 stdio MCP 桥接、三个严格 schema 的工具、状态和证据映射、8 秒取消确认预算、错误与身份边界、DeerFlow 配置示例及[接入指南](deerflow.md)。不增加 Go 服务或数据库迁移。
- **关键取舍：** Worker 独立运行；MCP 不持有执行生命周期或直接访问 SQLite；review/recovery 不映射为成功；取消只能确认后返回终态。见 [ADR 0003](decisions/0003-independent-mcp-bridge.md)。
- **代码交付：** [`2a941b1`](https://github.com/mzydmer/deermate/commit/2a941b140348727b6298009dcdf04a3397691caf)，新分支 `feat/m2-deerflow-bridge`，继承此前 M1 和 Agent 文档。
- **验证：** 常规检查 51 passed、1 skipped；显式运行真实上游驱动与桥接/MCP 检查 34 passed；token 边界调整后相关 28 项通过；Ruff 与 wheel 构建通过。新增固定上游驱动的 CI job，但不预先宣称远端 CI 通过。
- **兼容证据：** 实际加载 DeerFlow `a1b89d0432de4e45adc59f512cb25bb386ea1e51` 的未修改 ordinary-task 驱动，经真实 MCP/HTTP 完成提交、重建句柄、取消、完成、失败、待答；底层 Codex 使用离线协议 fixture，本次没有调用真实模型。
- **验收边界：** 没有启动完整 DeerFlow Gateway/SQL tracker 或前端，AC-M2-01 仍为部分验证；没有 SSH/跨主机连接。主线本次核对仍为 `e9f228d`，无开放 PR、无正式 release。
- **接续：** 先补完整 Gateway/SQL 重启验收，再推进 SSH；规格与当前任务分别见 [M2.1 规格](specs/m2-deerflow-task-bridge.md)和 [STATUS](STATUS.md)。
- **追加远端验证：** 推送后的 [CI 40180093367](https://github.com/mzydmer/deermate/actions/runs/40180093367) 在 `6f0a51f` 完成，Ubuntu/Python 3.11、macOS/Python 3.12 及 `deerflow-contract` 三个 job 均 success。此后只补验证记录，未修改运行代码。

## E-007 · 2026-10-25 · 实际 Gateway/SQLite 进程验收

- **目标：** 补上 AC-M2-01 的真实后台服务路径，证明先前驱动检查未覆盖的 SQL 跟踪、进程替换和 HTTP 查询/取消。
- **实现：** 新增 [verifier](../scripts/verify_deerflow_gateway.py)、独立 opt-in pytest 入口与 CI job。启动固定 DeerFlow 的原始应用/lifespan、SQL repository/service、MCP 工具发现/包装/调用及后台 poller，不用 mock 替换这些组件。
- **结果：** 14 项检查通过：Gateway 停止后 Worker 继续运行；新 Gateway 接续同一 SQL/Worker/native ID；原始取消路由取得确认；验证成功/失败返回 SQL/HTTP；Worker 失联成为可重试的跟踪异常，恢复后要求显式处理，没有重复原生会话或轮次。
- **代码交付：** [`14b0d8d`](https://github.com/mzydmer/deermate/commit/14b0d8da17e1978c10a80e7e997aa3f5d962aeb7)，分支 `feat/m2-gateway-verification`，继承此前实现。Worker/MCP 产品运行代码仍为 `2a941b1`。
- **证据：** [有限 JSON 收据](verification/deerflow-gateway-2026-10-25.json)保存源码/lock/verifier 哈希、依赖版本、fixture ID 和检查结果，没有私密路径、token、原始日志或数据库。独立 pytest 入口 1 passed（37.72 秒）；常规 51 passed、2 skipped；Ruff 和 wheel 构建通过。
- **环境：** macOS/Python 3.12.14，完整上游 frozen 环境。为锁定的 cryptography 50.0.0 在忽略目录构建 OpenSSL 3.5.9，没有修改系统安装或正常配置。新增 CI 尚需实际核对远端结果，不能用本地通过替代。
- **边界：** 临时数据库、离线 Codex fixture、带单次密钥的测试提交入口代替模型选工具；没有配置聊天模型，通知 run 在模型装配阶段失败。未验证 UI、模型生成通知、历史库升级、硬崩溃或远程 SSH。未创建产品端点或扩大运行权限。
- **下一步：** M2.2 SSH 身份、密钥和远程 Worker；模型/通知与 UI 体验另行验收。
- **追加远端验证：** [CI 40201412129](https://github.com/mzydmer/deermate/actions/runs/40201412129) 在 `28d6cc5` 完成，两个常规平台、原生驱动和实际 Gateway 共四组均 success；`deerflow-gateway-receipt` artifact 已上传，ID `12601528420`。此后只更新验证记录，未改验收脚本或产品运行代码。

## E-008 · 2026-10-25 · 注册式直接 SSH Worker

- **目标：** 推进 FR-013 / AC-M2-02，通过标准 SSH 使用独立 Worker，保持权限、任务身份和不确定副作用的边界。
- **实现：** AsyncSSH 固定 loopback 目的地转发；显式 known_hosts、专用私钥/token 和可选加密私钥口令引用；注册期限/撤权、定时连接过期、凭据轮换；CLI `--worker` 和远程 MCP；SQLite 实例身份与 `instance_id:task_id` 绑定句柄。没有增加 shell、SFTP、公共 HTTP 或新的加密协议。
- **取舍：** 沿用 HTTP/恢复契约；断线不自动重试修改请求；服务器公钥撤销的既有会话窗口明确可见；权限失效不误报任务停止。见 [ADR 0004](decisions/0004-ssh-loopback-transport.md)。
- **代码：** [`f7804ee`](https://github.com/mzydmer/deermate/commit/f7804eee9f45647222ef5a48e8d19d342a161d1b)，分支 `feat/m2-ssh-worker`，继承此前实现；主线本次核对仍为 `e9f228d`、无开放 PR。
- **验证：** 常规 74 passed、3 skipped；22 项 SSH 协议用例通过并保存[有界收据](verification/ssh-transport-2026-10-25.json)；实际固定 DeerFlow 驱动的 local/SSH 两变体通过；Ruff、wheel 和依赖一致性通过。包括身份错误、凭据权限、撤权/过期、空闲连接关闭、轮换、接纳后丢响应与幂等恢复。
- **环境：** macOS/Python 3.12，AsyncSSH 2.24.1、bcrypt 5.0.0、cryptography 48.0.1、MCP 1.30.0。测试只用生成的密钥、临时真实 SSH 服务器和离线原生 fixture，未访问真实 SSH daemon/用户密钥或请求模型。
- **边界：** 尚非真实双机/OpenSSH/NAT 部署验收；既有实际 Gateway 演示为本地路径，SSH 上游驱动已单独通过。新 CI 将回归并保存两平台 SSH 收据，远端结果需核对后追加。
- **接续：** 合并 Gateway 与 SSH 为同一演示/验收链，再推进已注册真实设备与受限账户部署。规格与操作见 [M2.2](specs/m2-ssh-worker.md)、[SSH 指南](ssh-worker.md)和 [STATUS](STATUS.md)。
- **追加远端验证：** [CI 40206131865](https://github.com/mzydmer/deermate/actions/runs/40206131865) 在 `96ca52b` 四组均 success，覆盖两个常规平台、两种驱动绑定及实际本地 Gateway 回归。已核对两平台 SSH artifact `12604035037` / `12603233873` 与 Gateway artifact `12602959515`；此后只补验证记录，运行代码未变。
