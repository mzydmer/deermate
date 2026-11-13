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

## E-009 · 2026-10-25 · Gateway → MCP → SSH → Worker 组合演示

- **目标：** 完成 M2.3，把此前分开的 Gateway 与 SSH 验收接成同一条实际链路，推进 FR-012/FR-013 和 AC-M2-01/AC-M2-02。
- **实现：** 既有 verifier 增加 `--transport ssh`，启动使用临时密钥的受限 SSH 进程并注册真实 Worker 实例；保留本地模式。`--replay` 根据实际收据生成离线 HTML，含事件时间、实例/任务身份、修复 diff 和验证输出。产品运行代码仍为 `f7804ee`，未增加产品权限或工具。
- **结果：** 21 项组合检查通过，覆盖 SQL 提交、实例绑定、Gateway 替换、原始取消接口、成功/失败验证、SSH-only 失联重连、撤权后取消失败及恢复授权后确认、Worker 恢复与无原生会话/轮次重放。五次提交对应五个原生会话/轮次。
- **验证：** 实际 Gateway local/SSH pytest 2 passed（92.59 秒），常规 74 passed、4 skipped；Ruff 与 wheel 通过。[收据](verification/gateway-ssh-2026-10-25.json)含当前源码/工具/renderer 哈希；[回放](assets/gateway-ssh-demo.html)已在浏览器检查单步、10×播放、21 项结果及窄屏布局，无控制台警告/错误。
- **边界：** 同机真实协议与离线 Codex fixture；测试入口只替代模型选工具。原始 diff 从只读 Worker 观察连接获得，任务验证经 Gateway 返回。没有真实设备/OpenSSH/NAT、模型通知、产品 UI、历史升级或硬崩溃声明，也没有修改用户 SSH 配置或调用模型。
- **交付：** 分支 `feat/gateway-ssh-demo`；CI 增加两种 Gateway 模式及 JSON/HTML artifacts，远端结果核对后追加。`main` 本次核对仍为 `e9f228d`，无开放 PR、未发布。
- **接续：** 已注册设备上的受限账户部署与服务验收，之后单独推进配置模型的通知/聊天体验。见[演示指南](demo.md)、[M2.3 规格](specs/m2-gateway-ssh-demo.md)和 [STATUS](STATUS.md)。

- **追加远端验证：** [`728deb7`](https://github.com/mzydmer/deermate/commit/728deb7df1553f10c2d016b91607a615961d2b10) 已推送；[CI 40255200451](https://github.com/mzydmer/deermate/actions/runs/40255200451) 完成且五个 job 均 success，包含实际 Gateway local/SSH。已核对 Gateway local/SSH artifact `12622301410` / `12621728883` 和两平台 SSH 收据 `12621993322` / `12621764111`。此后仅补验证记录，产品运行代码与验收工具未变。

## E-010 · 2026-10-25 · 阿里云 ACK 控制端部署包

- **目标：** 按用户明确要求准备 ACK 部署脚本和快速安装方式；这一要求取代此前暂缓 Kubernetes 的建议。
- **实现：** Python CLI 生成私有配置、准备固定上游、构建/推送 ACR 镜像、脱敏预览、显式 context 的 Helm 安装升级、状态、port-forward 和 SSH capabilities 查询。复用上游 Chart/Dockerfiles，以 Python post-renderer 注入受限凭据和策略，见 [ADR 0005](decisions/0005-ack-control-plane.md)。
- **边界：** 单 Gateway、20Gi RWO 云盘、SQLite/checkpoints、Recreate；保留应用鉴权。默认无 Worker、无公网入口、无 provisioner/RBAC 或云端 bash 工具。私钥/token 进入内存卷中的私密普通文件，部署重启更新；MCP 配置由 Helm 管理。
- **本地验证：** 14 项部署用例通过，包括实际固定 Chart 的 Worker 关闭/启用两种配置；常规初次回归 86 passed、6 skipped。真实 post-renderer 输出已生成；镜像与非 root 启动 CI 结果核对后追加。
- **交付：** `feat/ack-deployment`；[部署说明](ack-deployment.md)、[规格](specs/m2-ack-deployment.md)、公开配置与可选 Ingress 示例。未连接用户 ACK 或私有设备，未调用模型或宣称真实部署成功。

- **追加远端验证：** [CI 40266316155](https://github.com/mzydmer/deermate/actions/runs/40266316155) 在 `ca23f2c` 六个 job 全部 success；ACK job 构建四个 linux/amd64 镜像，并通过 UID 1000 启动、就绪、匿名拒绝、MCP/SSH 导入和 root-owned fsGroup 卷中的凭据复制检查。[保留证据](verification/ack-package-2026-10-25.json)来自已核对 SHA256 的 artifact `12626344052`。未执行 ACR 推送、真实 ACK 安装、前端登录、模型调用或家庭 SSH 连接；此后仅更新文档和证据索引。

## E-011 · 2026-10-26 · 本地 Docker、真实浏览器登录与 Codex 执行

- **目标：** 按用户要求先安装 Docker、启动项目并验收真实执行，云端 AK/SK 后续再接。用户明确选择先验收页面/登录/Codex，暂不接秘书模型。
- **实现：** 新增 Mac 本地 Python 编排与受限 Compose profile，复用 ACK 镜像；只开放 localhost:2026。专用生成配置/SSH 凭据经 Docker API staging 到命名卷，无宿主目录或 Docker socket 挂载。独立 host Worker 使用本机 Codex 登录和生成的 demo 项目；owner/key 入口调用实际上游 MCP/SQL，替代模型选工具。
- **运行反馈：** 修复非 root 无本地用户名导致 AsyncSSH 失败、前端 Corepack 运行时下载，以及构建 HTTP/下载瞬态问题；同步到 ACK layer/post-renderer 和镜像探针，不修改固定上游 checkout/lock。见 [ADR 0005](decisions/0005-ack-control-plane.md)。
- **结果：** 实际容器 Gateway → MCP → SSH → 真实 Codex 修复一行代码，独立 unittest 通过并返回 diff；14 项验收含重复提交、认证边界、Gateway 重启保留 session/SQL/结果。上游 duplicate-owner 409 保留原 Worker handle，attempt 始终 1；重复检查复用持久幂等键，没有新增模型任务。
- **浏览器：** 隔离 Linux Chromium 实际提交登录表单，进入工作区，四项检查通过、无 page errors，截图已查看。未操作锁屏 Mac 桌面或使用个人浏览器资料；Docker 图形首次设置未操作，后台 daemon/实际容器正常。
- **验证：** 本轮常规 91 passed/6 skipped；真实固定 Chart + 本地部署策略 19 passed；Ruff、wheel 通过。[有限收据](verification/local-docker-2026-10-26.json)包含 Docker/镜像身份、源码快照哈希、真实任务/会话、diff 和测试输出；owner 密码、凭据、原始日志不入库。
- **交付：** `feat/local-docker-runtime`；[本地指南](local-docker.md)、[M2.5 规格](specs/m2-local-docker.md)。远端 CI 推送后核对追加；主线本轮核对仍为 `e9f228d`、无开放 PR，未合并或发布。
- **边界/接续：** 秘书模型未配置、无完整对话/通知/路由声明；无实际 ACK/ACR、双机/OpenSSH/NAT 验收。维持本地服务，后续收到云端配置再按 ACK 指南部署。

- **追加本地停启验收：** 已实际执行 profile 的 `down`/`up`，重新登录、原 SQL 结果、Worker 实例/原生会话/attempt 保留，新 SSH capabilities 查询通过；未新增模型任务。三个容器恢复健康并保持运行，结果追加到同一有限收据。

- **追加远端交付：** `bf02720` 已推到 `feat/local-docker-runtime`；[CI 40295603001](https://github.com/mzydmer/deermate/actions/runs/40295603001) 的两平台常规、驱动和 Gateway local/SSH 共五个 job 已核对 success。ACK job 仍构建镜像，尚未确认本轮完整 CI 或取得新镜像探针 artifact；本地真实功能验收已完成。此后只补文档/收据，不修改运行源码。

## E-012 · 2026-10-26 · DeerMate 工作台与统一动效

- **目标：** 按用户明确请求安装 transitions-dev、transitions-polish、text-to-lottie，并在既有本地运行栈上重构前端。M4.1 先做只读工作台，M3 路由/专职 Agent 仍待实现。
- **实现：** 作者固定版本 skill 安装在用户目录；DeerMate 品牌登录/默认首页、真实近期任务筛选和证据、账户作用域 session 草稿交接。使用 hash 校验的源码 overlay，复用原认证、API 和 composer，本地/ACK 共用，无上游 checkout/lock 修改。见 [ADR 0006](decisions/0006-frontend-overlay.md)。
- **动效：** transitions-dev 原 sliding-tabs snippet、transitions-polish 时序/不对称抽屉/短 stagger；原创透明 Lottie 使用官方 Skia player 检查 0/45/89 帧，再在产品自托管 MIT light player 渲染。保留静态 fallback、减少动态效果与键盘交互；不分发 skill 集合。
- **运行反馈：** 本地 MCP 配置 GET 需要同目录锁文件；init 改为 home 卷内 owner-only 普通配置种子，每次 up 应用；staging/凭据仍只读。实际 GET 恢复 200，没有修改 Worker 核心或宿主授权。
- **阶段验证：** 94 passed/6 skipped，实际 Chart/本地/overlay 22 passed，Ruff 通过。首轮生产构建/TypeScript、13 项真实浏览器检查和 Skia 帧检查通过；最终入口/证据摘要/主题和焦点修正的浏览器验收随后追加，不提前宣称完成。
- **边界：** 只读任务范围限最近 20 对话、每对话 20 项；配置不代表设备在线，未配置模型不派单；M3 专职路由、真实云端/设备/NAT 和完整任务控制未新增验收。
- **补记此前 CI：** `bf02720` 的 CI 40295603001 六个 job 均 success；[历史 ACK 收据](verification/ack-package-2026-10-26.json)绑定 artifact `12638651102` 且 ZIP digest 已核对，不覆盖此后前端 overlay。

- **追加最终交付：** `fa452e3` 已推送；本地最终生产/TypeScript 编译、16 项浏览器检查通过，未新增模型任务，已有 Worker 会话/attempt 保留。已查看工作台、证据、深色/手机截图；Skia 0/45/89 及实际播放推进通过。[有限收据](verification/frontend-workspace-2026-10-26.json)保留源码/镜像/依赖身份和检查结果，不含凭据。
- **构建范围：** 本地 npm 下载变慢后复用经 package/lock 摘要核对的同 pin 依赖镜像，重新编译最终源码。[CI 40303558560](https://github.com/mzydmer/deermate/actions/runs/40303558560) 独立执行当前源码的标准四镜像构建，六个 job success，[probe artifact](verification/workspace-package-2026-10-26.json) `12641727909` 已核对 ZIP SHA256。此后只补文档/收据；保持本地应用运行，移除临时浏览器/类型检查容器。


## 2026-10-26 · Go 主服务、登录与管理后台（M4.2）

用户最新要求将主后端、管理后端、用户管理登录及前端接口改为 Go，取代原 Python-only 控制端方向。新增 [ADR 0007](decisions/0007-go-control-plane.md) 与 [迁移规格](specs/go-control-plane.md)，保留原决策的历史理由。

实现独立 Go 二进制：本地登录、摘要持久化会话、会话绑定 CSRF、用户/角色/停用/密码重置、最后活跃管理员保护、偏好、近期审计、工作区摘要和 `/admin` 页面。复用原用户 UUID/密码哈希与偏好；短期真实用户 JWT 连接内部 DeerFlow，去除浏览器伪造 internal 身份和上游认证 Cookie。普通用户执行/配置被拒绝，项目级授权另行设计。DeerFlow、现有 Worker/MCP/SSH 与部署工具保留 Python。

本地 Compose 增加非 root Go 服务，只注入必要 bridge secret，先用 SQLite online backup 保存原数据，再切换 nginx/SSR 入口。ACK 五镜像构建及 Go sidecar/Service 接入保持原 RWO/Recreate 单实例；Python runtime 改为 Pod 内 loopback，健康探针携带固定允许 Host。未连接 ACK、推送 ACR 或宣称生产/HA。

验证：Go 模块校验、vet、7 项竞态测试通过（最终测试 8.666 秒）；常规 Python 94 passed/6 skipped（51.10 秒）；实际固定 Chart/本地/overlay 22 passed（1.50 秒）；Ruff、wheel、原 Chart post-renderer 和标准 Go Dockerfile 构建通过。实际本地 27 项 API 检查及 18 项浏览器检查通过，原账号/历史真实 Codex 任务保留，管理页面可创建/停用，浏览器 page errors 为零。追加 Go 重启后会话/任务保留验证；本轮模型任务为零。Go/API/browser [有限收据](verification/go-control-plane-2026-10-26.json)与[管理页截图](assets/deermate-admin-go-2026-10-26.png)区分本轮和历史原生执行证据。

交付补记：源码 `4af38d6` 已推送 `feat/go-control-plane`；本轮 [CI 40313922279](https://github.com/mzydmer/deermate/actions/runs/40313922279) 的 Go、双平台 Worker、契约及双传输 Gateway 六个 job 已通过，ACK 标准镜像构建仍在运行。另以实际在线备份核对原 owner ID 与密码哈希完全一致，未记录这些值。


## 2026-10-26 · Vercel 风格与统一前端设计规范（M4.3）

用户要求形成 `design.md` 并约束后续所有前端。新增根目录 [设计规范](../design.md)，参考官方 Geist 与 Web Interface Guidelines，定义 DeerMate 自有中性浅/深色 token、无衬线排版、组件、页面模板、状态、动效和验收流程。AGENTS、贡献指南、中英文 README、前端说明均接入该规范；NFR-008 记录长期约束。

React 和 Go 管理页共用 canonical CSS，Go 副本由 Python 标准库脚本同步，构建和 CI 拒绝漂移。首轮落地登录、工作台、证据界面和管理页；保留鹿标、原交互和动画时序。截图复核发现的登录标题衬线继承已修正。管理页移除主说明中的实现细节，密码重置改为遮罩输入的原生 dialog，覆盖 Escape、焦点恢复和提交。未引入 Vercel 内部组件、额外运行时字体或 CDN。

验收：最终 25 项真实浏览器检查通过，原任务 1 条仍可读、page errors 0、模型任务 0；检查浅/深色、390px 手机、键盘/减少动态效果及管理功能。已查看桌面、登录、手机和深色管理截图，见[有限收据](verification/vercel-design-2026-10-26.json)。色彩基础对比度已计算（正文/状态色 >=4.5、必要边界/焦点 >=3）；未声称完整独立 WCAG 审计。Go 7 项测试通过（6.798 秒）、固定 Chart/本地/overlay 22 passed（2.99 秒）、Ruff/token 同步/相对链接通过。标准前端镜像构建通过；最终少量样式修正在 package/lock 完全一致的标准镜像依赖上重新编译，保留 base/最终镜像身份。

当前分支 `feat/vercel-design-system` 基于 Go 分支 `e7db6dd`。补记上一轮 Go [CI 40313922279](https://github.com/mzydmer/deermate/actions/runs/40313922279) 七个 job 现已核对全部 success，含标准五镜像构建；这不是本轮新风格的 CI，也不代表 ACK 部署。本轮设计源代码交付状态另见 STATUS。

设计交付补记：源码 `c349431` 已推送 `feat/vercel-design-system`，最终验收为 25 项浏览器检查通过；[CI 40318918329](https://github.com/mzydmer/deermate/actions/runs/40318918329) 正在运行。本地四个应用容器保持健康。


## 2026-10-26 · 完整开发栈合并 main

按用户明确要求，将主线从 `e9f228d` fast-forward 到 `51d58b2`。当前开发 head 包含所有十个功能分支，保留原有提交历史及分支，没有压缩、重写或删除。GitHub 连接器创建 PR 返回 403；改用已有 SSH Git 权限，通过普通推送完成远端主线更新。无 PR 创建，不声称存在审阅/批准记录。

合并包含 Worker/Codex、MCP/SSH、Go 主服务/管理/认证/前端 API、Docker/ACK 包，以及工作台和 design.md。已核对来源 `c349431` 的 [CI 40318918329](https://github.com/mzydmer/deermate/actions/runs/40318918329) 七个 job 全部成功；其后为文档更新，实际功能代码与已验收来源一致。主线安装说明改用 main；主线 CI 结果另行核对。原生模型任务未重跑，本地服务/账户/任务数据保留。此为源码 alpha 集成，不是 release、ACK 安装或专职路由完成声明。

## 2026-10-26 · 阿里云 ACK 控制台检查与创建草案

用户请求部署 ACK，随后明确尚无集群、先准备创建方案。已检查登录后的杭州/北京 ACK 列表及北京 ACR，并填写尚未提交的基础版单 ECS 开发集群草案。记录实际控制台列出的节点、磁盘、NAT、EIP、CLB 固定报价及未计价项；创建预算、RAM 角色授权、ACR 凭证和集群 API 连通方式仍待确认。账号、网络标识、截图和私有草案留在 Git 忽略目录。

应用草案未复制任何凭据，registry 使用 `pending.invalid`、context 使用 `ACK_NOT_CREATED`，防止被误认为可执行的云配置。实际固定 Chart 离线渲染为 11 个资源/3 个 Deployment，未访问集群 API；没有创建资源、RAM 授权、镜像推送、Helm 安装或模型任务。当前控制台报价与范围见[有限记录](verification/ack-console-plan-2026-10-26.json)；不构成 ACK 实际验收或家庭 Worker 连通证明。

## 2026-10-26 · 最低成本单机运行候选

用户认为 ACK 报价过高，要求最便宜的最小配置。增加可选 [Compose 单机包](single-host.md)与 [ADR 0008](decisions/0008-single-host-budget.md)，使用已有四镜像、本机磁盘和新生成内部密钥，无需 ACK/NAT/负载均衡/镜像仓库。保留 Go 用户/API 权限、非 root、loopback 发布与 SQLite/home；移除本地开发 submit shim，默认模型/MCP 为空，不搬运原生账号或原数据。2 核/2 GiB 是待目标机验收候选，限额不是低内存主机保证。

独立新卷测试四个容器，在合计 1472 MiB/2 核的常驻限额下健康运行，14 项 HTTP 检查和 5 项重启保留检查通过；原部署/Worker 保留。首次探针的 HTTP 状态码、MCP 字段和只读路由预期已按源码修正，应用认证未改变。模型调用 0，未做模型并发或实际 2 GiB 云主机测试。常规回归 96 passed/7 skipped（50.84 秒），实际 Chart/本地/overlay/单机专项 25 passed（1.37 秒），Ruff/wheel 通过；新脚本 lint/渲染检查已接入 CI，远端结果另查。

控制台核对北京轻量 2 核 2 GiB/40 GiB/Ubuntu 24.04 的首年活动与券后报价，自动续费关闭；价格截图/私人计划留在忽略目录，账号/优惠券标识不入库。没有购买、接受协议或声称云端安装完成。来源和边界见[有限收据](verification/single-host-2026-10-26.json)。


## 2026-10-26 · 最低成本云主机创建与 Docker 就绪

用户确认北京 2 核 2 GiB / 40 GiB / Ubuntu 24.04、1 年首购券后零元、自动续费关闭和服务条款后，重新登录阿里云并完成单个轻量服务器订单。收银台显示实付 ¥0 与支付成功，控制台显示实例运行中；没有提交原 ACK 方案或创建其附加资源。此前“未购买”的记录属于准备阶段，现由此条追加更新。

现有 Workbench 免密普通 Shell 已连接，sudo 可用。通过 Ubuntu 官方 apt 源安装 Docker，实际验证引擎 29.1.3 active 与 Compose 2.40.3。内核可见总内存 1613 MiB，Docker 安装后 available 1108 MiB、磁盘剩余约 35 GiB；标称套餐尚不等于应用容量验收。

本机部署包及摘要已准备。浏览器上传要求扩展本地文件权限；当前采用待确认的独立临时 SSH 访问方案，密钥尚未添加，应用未上传/启动。没有云端模型、家庭 Worker 或应用验收声明。[资源准备收据](verification/single-host-cloud-2026-10-26.json)只记录有限事实；私密标识、凭据和截图不入库。


## 2026-10-27 · 最低成本云端单机部署与整机重启验收

收到用户对临时 admin SSH 的明确确认后，完成专用公钥登记、控制台核对的主机公钥固定和传输限制。初版 `permitlisten=none` 公钥选项写法不适用，改用 admin 的 sshd 本地转发限制，语法/生效配置通过；`-R` 与其他目的端口实际被拒绝。24 小时公钥、私人访问脚本和凭据不入库。

上传约 1464 MiB 预构建镜像与新配置，两份 SHA-256 通过；四个 image ID 与已有验证来源一致。Ubuntu Docker 29.1.3 / Compose 2.40.3 下四服务健康，唯一应用入口为 loopback 2027。原本地 2026 四服务及其数据保持。本轮无需新构建镜像或修改应用认证。

实际 18 项初始 HTTP 检查通过，包含 40 次、并发上限 4 的只读请求及匿名/Host/Origin/CSRF 边界。随后受控重启整台主机，boot identity 改变、四服务自动恢复；10 项重启后检查证明原 owner 与会话保留。内置浏览器实际登录、工作台 Gateway 正常、管理页账号列表和重启后页面均核验。初次验收探针修正 canonical localhost 与初始 email 格式；固定上游 redirect 和现有 Go 校验保持不变。

目标机 OS 可见总内存 1613 MiB，负载后/重启后 available 约 695/831 MiB，磁盘约 26.9 GiB；观察点没有 OOM、服务重启计数为零。[有限收据](verification/single-host-cloud-2026-10-27.json)不含云/账号/订单/密钥标识。模型调用 0、家庭 Worker 为空；没有声称模型容量、云到家庭执行链路、公网 TLS、HA 或硬崩溃恢复。下一步单独接模型并设计受限家庭网络。


## 2026-10-27 · 域名候选查询与 HTTPS 草案准备

用户要求进一步配置域名和 HTTPS，并明确选择先查域名候选及报价。已从万网实时公开结果核对可注册状态、首年与续费展示价；域名尚未选定，没有下单或修改 DNS。候选名称、报价和截图仅留在私人目录，避免在注册前公开计划。

核对官方文档：现有北京节点的对外网站需先完成阿里云 ICP 备案，不能由 HTTPS 代替。域名控制台当前要求重新登录，未进入实名资料填写。准备 Caddy edge 与 Go Origin/Host 草案，示例配置使用官方镜像 Caddy v2.11.7 在无网络、无发布端口的临时容器 validate 通过；临时容器已移除。这是配置准备，不是实际证书/HTTPS 或备案通过证明；云端当前仍为原 SSH/loopback 入口，后续依次完成域名选择、注册/实名/备案与公网 HTTPS 验收。


## 2026-10-27 · 暂缓域名，准备公网 IP 与零元首月候选

用户在选定一个域名候选后改为“先开公网访问，先不买域名”。没有提交域名订单或购买域名。核对阿里云关于内地 IP 网站也需备案的官方说明后，准备非中国内地的新加坡候选，未直接公开原北京实例。

同账号重新登录后实际比较通用型与国际型，选择更低标价的国际型 2 核/2 GiB/40 GiB / Ubuntu 24.04，1 个月 ¥39、使用现有券后预览 ¥0、自动续费关闭；非中国优化线路的取舍保留。新订单/资源、跨地域账号配置迁移、24 小时临时 SSH、80/443 公网入口与证书条款已组成可审核草案，等待用户确认，没有提前创建新实例或授权。

原云端 SQLite online backup 与 quick_check 已完成，原服务保持。IP HTTPS 的 Let's Encrypt shortlived/Caddy 示例在 network=none 的隔离容器 validate 通过，issuer 内目录字段按实际 CLI 结果修正为 dir；临时容器已移除。此证据不代表证书签发或自动续期验证。私人密钥、备份路径、账号、优惠券及报价截图不入库。

## 2026-10-27 · 公网 IP HTTPS 部署验收

用户明确批准新加坡零元首月方案、条款、临时 SSH、云账号/配置迁移及公网 80/443 后，已完成国际型 2 vCPU/2 GiB/40 GiB Ubuntu 24.04 实例购买，实付 ¥0、购买时自动续费关闭。保留北京私有实例回退，域名未购买；首月券后优惠不保证续费价格。

新增 `scripts/single_host_https.py` 和 [ADR 0009](decisions/0009-public-ip-https.md)：可选受限 Caddy 2.11.7 edge、持久证书卷、精确 Go HTTPS Origin/Host 与 Secure Cookie，保留原 Compose 备份及私有默认。目标主机公钥经 Workbench 核对；临时密钥限制已实际验证，私钥未离开本机。现有云 SQLite 一致性快照和 5 份应用配置核对后恢复，原 owner UUID/密码保留，没有复制 Mac/native/Worker 凭据。外部验收修正了 IP 无 SNI 客户端的证书选择和未知 Host 空响应，最终正常证书校验与 421 拒绝均通过。

实际完成 24 项初始 HTTPS 检查（含 40 次、并发上限 4 的只读请求）、17 项受控整机重启后检查，以及浏览器登录/工作台/管理账号行与重启后会话保留。证书签发为 Let's Encrypt `shortlived`，正常链/IP SAN 验证通过，同一证书在重启后保留；自动续期配置已启用，尚未观察到真实续期。另一云节点验证 80/443 可达、6 个内部应用/管理/Worker 端口关闭或过滤；没有将受本机代理影响的裸 TCP 结果作为隔离证据。目标机可见内存 1613 MiB，请求后/重启后 available 约 717/829 MiB，磁盘剩余 26.7 GiB，观察点无 OOM；北京及原 Mac 四服务仍健康。见[有限验收收据](verification/single-host-public-ip-2026-10-27.json)。

最终 `python -m pytest -q` 为 **103 passed / 7 skipped**；设置实际上游和 Helm 后，固定 Chart/本地 Compose/overlay/单机/HTTPS 专项为 **32 passed**。Ruff、wheel、最终 Caddy 无网络 validate 通过；CI 增加新 renderer 的 lint 和实际 bundle 契约覆盖。模型调用 0、家庭 Worker 未配置；模型容量、云到家庭执行、HA 和实际证书续期仍另行验收。私人地址/账号/云标识/截图留在忽略目录，公开收据只保留脱敏事实。

## 2026-10-27 · 北京旧节点下线，永久退订待确认

用户在公网部署成功后要求下线并退订北京旧节点，取代此前保留在线回退的安排。停止四应用容器后，将最终一致性数据库、完整应用 home 与配置归档保存到本机私人目录，三份归档/数据库哈希及 SQLite quick_check 通过。控制台关机的令牌/安全验证服务失败后，经既有授权 SSH 正常 poweroff，云控制台确认已停机，旧 2027 隧道已关闭。北京关机后，新加坡 5 项正常 HTTPS 页面/API 检查通过。

退订预览：已区分现金与代金券，无新增支付，具体金额留在私人记录；尚未提交不可恢复的退订，已在完整准备后请求永久释放与退订规则的最后确认。实际退款及释放结果另验。见[下线收据](verification/beijing-retirement-2026-10-27.json)。本轮仅运维与状态文档变更，未重复调用模型或重跑应用测试。

## 2026-10-27 · 北京退订已获确认，受阻于官方身份验证

用户已明确确认永久退订北京旧实例及系统盘并接受退订规则，该授权无需重复请求。三次通过正常费用控制台提交同一实例的退订，均出现空白的官方身份验证窗口；首次未完成后清除日期筛选检查退订订单为 0，未盲目重放不确定请求。完整刷新及正常同账号 SSO 刷新恢复了列表，验证窗口仍无法完成；独立打开官方验证入口仅显示流程已结束。尚无成功退订回执、资源释放或实际退款声明。页面保留给用户完成身份验证。

新加坡在此期间另有 5 项页面/API 正常 HTTPS 检查通过；北京最终备份和停机安排保持。更新[下线收据](verification/beijing-retirement-2026-10-27.json)区分已授权、已尝试与已完成状态；本轮仅运维/文档变更，未调用模型或重复运行应用回归。

## 2026-10-27 · 北京永久退订及退款完成

用户完成阿里云身份验证后，已重新核对北京旧节点：详情页显示“当前资源不存在”，北京列表为空；对应退订订单详情明确显示“退款成功（含券）”，全部退回代金券、现金为零、没有新增支付。最终结算较早预览略有变化，具体金额和云标识只留在私人记录。没有重复提交已完成的退订。

新加坡公网工作台、管理页、owner 与两个 API 共 5 项正常 HTTPS 检查通过，保留实例继续运行。北京最终一致性数据库、完整 home/配置与校验记录保存在本机；旧 2027 隧道已关闭，专用北京 SSH 配置归档，新加坡运维配置保留。更新[下线收据](verification/beijing-retirement-2026-10-27.json)、当前 STATUS 和规格，原保留在线回退的安排已由用户退订要求取代。本轮仅运维/文档变更，模型调用为 0，没有重跑应用回归或新增云资源。

## 2026-10-28 · 家庭 Worker 接入前的只读连接预检

继续开发 M2 接入路径，新增 `deermate ... doctor` 和无参数 MCP 工具 `check_worker_connection`。它们复用已有 loopback/SSH 连接，检查凭据、授权期限、SSH 主机身份、Worker 实例及协议能力，输出有界脱敏 JSON 与明确退出码。成功仅表示 API 当时可达；原生登录、容量、项目授权和任务结果明确标记未检查。SSH 在每次转发前检查协议，不兼容响应在修改请求前被拒绝；撤权检查不将运行中任务误报为停止，恢复连接不创建新任务或原生会话。Go 主后端与管理/登录/前端 API 语言边界保持。

预检专项 45 passed；最终全量 148 passed / 7 skipped（63.03 秒，一条已有 Starlette 弃用提示）；固定上游 local/SSH driver 与实际 Gateway 4 passed（104.17 秒）。最终 SSH Gateway 独立跑过 26 项检查，[收据](verification/worker-preflight-gateway-2026-10-28.json)保留源码/脚本哈希与有限结果。Ruff、wheel 和 diff whitespace 检查通过。本机运行中的 Worker 也通过新 doctor 命令的真实 HTTP 检查，未提交新原生任务。

更新[规格](specs/m2-worker-preflight.md)、README、接入指南、SPEC、STATUS 和 roadmap。MCP 增量工具正常出现在 DeerFlow 工具发现中，原三个后台任务契约和 SQL 跟踪继续通过。公网容器未在本轮升级，真实家庭 OpenSSH/NAT、配置模型后的派单/通知与容量仍待单独接入验收；本轮模型调用为 0。

## 2026-10-28 · 真实秘书模型、原生派单与结果通知

复用本机已保存的千问模型，通过受认证 HTTPS 管理接口接入云端，未写出明文模型 key；云端 catalog/key 均为 0600，加密内容和正式聊天 run 已验证。另更新本地 Gateway 的 Worker wheel，保留原账号、数据库、Go/前端镜像，升级前做一致性备份；仅刷新同机生成密钥的开发注册，没有改变系统 SSH 或云端访问授权。

新增 `scripts/verify_secretary.py`，显式 `--live` 后使用正式 thread/run/checkpoint API，让真实模型先做 MCP 预检再提交一次 demo 任务。真实 Codex 的一行补丁、原生会话/attempt 1、独立测试退出码 0 与 SQL/MCP 结果核对通过，通知 delivered。验收器只读访问操作员本机 Worker 的实例/请求指纹映射，不扩大公共 API 或 MCP 读库权限。稳定 intent 和 run attempted 在发送前持久化；超时/重启只核对，不自动重放。修复本地旧 submit shim 按名字选择工具，兼容新增预检。

初次 12/32 图步骤不足，分别留下聊天/派单 run error；已接纳任务仍完成并通知。保留失败证据并只读核对，修正为 128 图步骤后用独立有界新尝试通过。整轮两项原生任务、9 次 runtime 可观测 LLM 调用，另 2 次 provider 工具探针；不将其等同于账单或 SDK 请求数。最终全量 170 passed / 7 skipped（62.46 秒）、实际固定部署契约 29 passed（1.78 秒）；Ruff/wheel 通过。一条已有 Starlette 弃用提示保留。[公开有限收据](verification/secretary-live-2026-10-28.json)记录源码哈希、成功范围和失败尝试。

真实云到家庭仍需网络接入。已准备两组专用账号/限时密钥、loopback 反向转发、到期移除/断开 timer 及回退脚本；目标 Ubuntu 仅临时配置通过 sshd 语法/生效策略检查，没有激活配置、创建账号或注册云 Worker。新增登录/转发权限已请求用户确认，见[方案](specs/m2-home-reverse-link.md)与[拟议 ADR 0010](decisions/0010-temporary-home-reverse-link.md)。Go 主/管理/登录/前端 API 边界保持；本轮不是浏览器派单、家庭系统 sshd 或公网 Gateway 镜像升级验收。

## 2026-10-28 · 获批临时云到家庭链路与真实派单

用户单独批准两组无 shell/无 sudo 的专用 SSH 账号、单端口转发和最多 24 小时期限后，经阿里云命令助手安装。Mac 主动出站，把已有 loopback Worker 接到云端 loopback 监听；独立 reader 账号仅可读取该监听。固定主机密钥、应用实例与 demo 项目权限保持，Mac 系统 sshd 未修改，原 admin 密钥未延长。实际 sshd 语法/生效策略、特权组检查、9 项正负向 SSH 用例和 systemd timer 验证通过。timer 已 active，固定 UTC 2026-10-30 02:29:56 移除公钥/云端 Worker 凭据并终止专用会话；实际到期尚未观察。

云端从已核对 SHA 的公开 `2e7fdac` 源码构建 wheel，采用当前依赖版本约束和预缓存离线 uvx；未放宽 HTTP 命令白名单。原 Gateway 镜像保持；固定上游后台工具快照不支持热启用，按其生命周期账本/锁激活并做受控 Gateway 重启。首次未启用工具的模型 run 接纳零任务，保留其记录，未重放。临时凭据 staging 已从活动配置和回退归档移除，运行时文件仅 owner 可读，反向私钥和原生登录留在 Mac。

正式云端 run success（3 次 LLM 调用）由真实模型先预检再提交一次，家中 Codex 完成一个 demo 修复。MCP/Worker 恰好一个任务，原生 session、请求映射及 attempt 1 对应，补丁只改预期文件，独立 unittest exit 0，通知 delivered。主动断开专用反向会话后 connector 恢复传输，同一 intent 只读重查通过，没有追加模型/原生执行。浏览器确认公网任务、补丁摘要和独立验证抽屉，未重验浏览器输入/流式 UI。

验收器新增可选公网 IP SSH 路径交叉核对，必须与 HTTPS origin 同主机且与独立本机 Worker 身份一致，阻断时在模型 run 前退出。新增 5 项离线用例，验收器专项 27 passed；全量 **175 passed / 7 skipped**（63.83 秒，一条已有 Starlette 弃用提示），Ruff/wheel 通过。上轮固定部署契约 29 passed，本轮未改镜像模板、Go 或前端，未重复运行。更新[接入规格](specs/m2-home-reverse-link.md)、[Accepted ADR 0010](decisions/0010-temporary-home-reverse-link.md)、[验收指南](secretary-acceptance.md)及[独立脱敏收据](verification/home-link-2026-10-28.json)。

本次证明一个手工配置的限时 alpha 链路；两条 SSH 都在可信云主机终止，云端可读内容。通用设备配对、Mac 重启守护、正式永久接入、项目级 Go 授权及专职路由仍需开发；没有新增付费云资源或公开 Worker 端口。

## 2026-10-29 · Codex 多轮会话按轮保留证据

用户希望网页能持续与远程 Codex 问答。采用 [ADR 0011](decisions/0011-codex-conversation-turns.md)：每轮创建子任务，继承原生会话/工作区和项目策略，父结果不变。SQLite head 原子接纳防止并发/旧父任务分叉；原 CLI resume 限于最新任务。新增 capability 标志、鉴权 continue API、CLI 与 MCP；旧基本操作列表保留，旧控制端可继续原操作。

可选 `continue_codex` provider 按实际 user/chat/incarnation 查询已有跟踪行，把公开 task ID 私下映射到已注册 Worker handle，经原 ordinary driver 形成独立后台行。固定上游要求 task toolset 各角色名称不重复，因此子任务查询/取消使用独立 raw 别名。没有改写上游源码、Go 公开接口或前端，没有自动审批恢复或延长 SSH 授权。

全量 199 passed / 7 skipped（70.73 秒，一条已有 Starlette 弃用提示）；会话/固定部署专项 53 passed；原 ordinary driver 两变体通过，实际 Gateway/SQL/SSH 28 项通过，含三轮/结果保留/跨聊天拒绝/同调用核对。真实公网升级和原生问答仍需单独验收，进度见 STATUS。新增可复用 opt-in 多轮验收脚本，先持久化完整 ledger，再发正式模型 run，未知结果只读核对。

### 同日追加 · 真实三轮已部署验收

源码 `f6e8b21` 已推送。家中 Worker 在无活动任务时一致性备份并升级，保留实例和 4 项既有任务/结果。云端从该公开归档核对 SHA，使用既有基底/依赖构建无网络 wheel 镜像层，更新原 Compose image 并仅替换 Gateway；账号、加密模型、home 卷、Go/前端和 SSH 账号/期限均保留。原到期 unit 哈希不变、timer active，未新增付费资源或公网端口。

原对话的两次真实模型 follow-up 各 success（各 2 次 LLM 调用），通过 scoped provider 接入普通后台任务；累计三项 Worker/MCP 任务共用原生 session/workspace/base/policy，独立测试退出 0、通知 delivered、父证据保留。第三轮原文没有重新发送第二轮标记，Codex 仍准确回忆；两次问答没有改变原单文件补丁。相同 ledger 只读复查通过，总 Worker 任务仍为 6。浏览器核对完整对话与结果，截图留在忽略目录，未重验键入/流式交互。[真实有限收据](verification/codex-conversation-live-2026-10-29.json)保留源码/脚本绑定、部署与边界。另补本地 Gateway 20 项检查通过，SSH Gateway 28 项；不将 fixture 等同于真实模型证据。
# 2026-10-29 · Public tools and connection diagnostics

The minimal profile only configured Codex delegation, while the capability catalog
showed guide entries for web tools. Added bundled public search and a screened Jina
page reader to the common deployment configuration. Added an admin-only Tools &
connections page through the pinned runtime's supported extension/assets API,
retaining Go public authentication and its admin runtime gate. Existing MCP forms
still own configuration and credentials; metadata checks snapshot one saved
platform/current-owner connection, reuse upstream discovery, bound time/concurrency,
and never call a business tool or return raw transport errors. Private connectors
still require separately authorized services/accounts.

Validation: full suite **213 passed / 7 skipped**, actual pinned deployment contracts
**32 passed**, Ruff, wheel (including browser resources), JavaScript syntax and shared
token checks passed. Pinned provider assembly, plugin assets, URL rejections, a real
MCP metadata fixture without execution and public search/read smoke **8 checks
passed**, zero model calls. Local fake-IP DNS correctly blocked domain reads; the
public literal smoke used `https://1.1.1.1/` without weakening URL admission. Cloud
deployment and real model/UI acceptance are pending at this source commit. See
[spec](specs/m2-tools-and-connections.md) and [usage](tools-and-connections.md).
## 2026-10-29 · Cloud tool execution verified

Source `815d8d8` deployed to the existing cloud Gateway. The first packaging attempt
stopped before activation on a resource-directory assertion; reconciled the saved
checkpoint and unchanged original configuration, then completed packaging and the
immutable image update. Existing account/model/Codex configuration and expiry units
were retained; no extra cloud instance or SSH grant was created.

HTTPS/admin login, plugin assets, native tool inventory, saved MCP discovery (three
model-visible Codex tools), unknown-server refusal and anonymous denial passed.
One admitted real chat selected both web tools and received search results/page
content. An obsolete profile-name probe was rejected before run admission and its
attempted intent preserved; no uncertain run was replayed. Browser navigation and
connection test passed. A UI-only refinement removes the duplicate host title and
updates the row label after a test; it does not change the verified tool behavior.
See [sanitized receipt](verification/tools-and-connections-2026-10-29.json).

## 2026-10-29 · Tooling delivery complete

UI refinement `e542b7a` is deployed in an immutable offline Gateway layer; final
receipt confirms the existing home/model/account/Codex settings and expiry units
were preserved, readiness passed, zero active work before replacement, no OOM and
restart count zero at the observation point. The final browser page has one title,
three loaded native tools and a successful three-tool MCP discovery with updated
row status. Desktop dark theme screenshot retained privately. Shared tokens, JS
syntax, wheel resource equality and pinned offline plugin/MCP checks passed after
the UI refinement. Retained successful chat was reconciled read-only after upgrade;
no second model run or native task was submitted. Final sanitized
[receipt](verification/tools-and-connections-2026-10-29.json) separates the
model-verified tool implementation from the later UI commit. Private business-data
connectors and actual temporary-grant expiry remain outside this acceptance.

## 2026-10-29 · One chat, one coding session and automatic names

Added a durable chat admission journal and a fail-closed configured runtime
middleware. Registered raw coding submissions bind executor/server/project once;
later submissions use the existing child-task continuation, including after
restart. Deterministic tracking IDs and run/tool-call identity reconcile duplicate
calls without replay; pending/uncertain, active, changed-project/executor and
ambiguous legacy requests cannot create a replacement session. Names derive from
the first human message, using the existing title/rename state. Added an owned
conversation action to inspect the canonical journal. Go public auth/API ownership
and Worker/native grants are unchanged; Claude execution remains unimplemented.

Full suite **244 passed / 7 skipped**, pinned deployment contracts **32 passed**,
configured middleware/real LangChain graph **10 checks**, actual Gateway local/SSH
**22/30 checks** passed. New Gateway cases prove repeated raw submit becomes one
root plus continuation across restart; reconciliation/project refusal adds no
native turn. Ruff, wheel, JS syntax and shared token checks passed. Native/model
work in these receipts is fixture-only; cloud deployment and real Codex/UI checks
are pending at this source commit. See [spec](specs/m2-chat-session-binding.md),
[ADR 0012](decisions/0012-one-chat-one-coding-session.md) and
[offline receipt](verification/chat-session-binding-offline-2026-10-29.json).

## 2026-10-29 · Single-session cloud and browser acceptance

Implementation `4e5c05d` is deployed as an immutable offline Gateway layer. Ready
checkpoint, original home/model/account/Codex configuration, unchanged expiry
units, no OOM and restart count zero were verified in the saved deployment receipt.
No Worker grant, new cloud resource or frontend image rebuild was required.

Two normal user runs deliberately selected the raw `deermate_submit_task` tool.
The server created exactly one root and one child: same binding, native Codex
session, registered project and workspace. Both independent validations exited 0
and completion notifications were delivered. The first message automatically
named the chat; a real browser rename persisted through the second question. The
conversation action displayed the canonical round-two native ID and completed
state. Private screenshot and attempted intents are retained; no uncertain request
was replayed. Public [live receipt](verification/chat-session-binding-live-2026-10-29.json)
contains no account credentials, live chat/native IDs or workspace paths. The
separate [offline receipt](verification/chat-session-binding-offline-2026-10-29.json)
covers failure/concurrency/restart cases. Claude execution and actual temporary
access expiry remain unverified.
## 2026-10-29 · 个人记忆与今日简报规格提案

用户要求对私人助手记忆和首页做大迭代，并明确先出 spec、不写代码。本轮准备
[M4.4 规格](specs/m4-personal-memory-briefing.md)及
[ADR 0013 提案](decisions/0013-memory-backed-personal-briefing.md)，补充 FR-023–FR-028
和未勾选路线图。首页方向为个人问候、可核对的今日关注、可解释的新话题及明确动作；
区分长期记忆、关注主题和进展证据，约定来源时效、更正/遗忘、权限/预算与单会话关联。

核对了当前首页/Go 用户模型和固定 DeerFlow 记忆接口的源码，确认最小部署记忆仍禁用，
称呼/时区和新的简报能力均非现有功能。仅验证文档链接、需求引用和 diff 范围；没有
改应用代码、启用记忆、导入私人历史、调用模型、创建调度或部署。所有新增验收标准待
后续实施与评审，不能视为已通过。

## 2026-10-30 · 记忆技术原型与关键时序设计

按用户要求补充[技术设计](specs/m4-memory-technical-design.md)：五条时序图覆盖采集、
召回注入、简报发布/读取、首页动作、纠正/遗忘竞争，另有事实生命周期图。提交可编辑
Mermaid 源和六张 SVG；用 Mermaid CLI 11.4.2 实际渲染，并逐图检查 PNG 预览。

按固定上游 `a1b89d0432de4e45adc59f512cb25bb386ea1e51` 源码明确原型为 Go/现有 SQLite
产品层加本地 DeerMem：Markdown 事实、JSON 共享摘要、FTS5/BM25 派生检索。说明默认检索
和上下文注入不同、词法相关性模式会绕过 FTS5、提取队列仅在进程内；Go 持久作业、
提交回执/策略门禁、项目过滤及摘要删除谱系需要后续实现。同步主规格、ADR 和接续状态，
仍为 Proposed，保留 MEM-01–MEM-21 待验收状态。

本轮只检查固定源码、文档链接/需求引用、SVG 与 Mermaid 渲染及 diff；没有变更应用依赖、
代码或配置，没有启用记忆、回填历史、调用业务模型、创建调度或部署。渲染工具仅安装在
被忽略的本地工具目录，没有加入产品镜像或运行时依赖；图形验证不代表记忆功能验收。


## 2026-11-02 · M4.4a 个人记忆基础实现与本地验收

用户同意开始实施后，先交付[个人记忆基础](personal-memory.md)：Go 提供称呼/时区、独立启用策略、显式事实 CRUD、来源哈希/版本引用、确定性存储投递与遗忘屏障；工作台提供管理和个人问候。受限 Python 适配器复用固定 DeerMem 文件事务、FTS5/BM25、中文 tokenizer 和上下文格式化；仅本人个人范围，不启用旧全局记忆或共享摘要，不自动回填历史。最多 2,000 条未清理事实/用户、50 条列表页、10 条搜索结果，近期明确偏好有独立召回入口，按约 1,500 tokens 的离线估算预算注入。

投递在短暂共享 SQLite 保留期间复核账号/策略和目标屏障，期间不调用模型；Go 单次投递一个操作，队列跳过停用/待完成账号以免阻塞其他用户，并保留回归测试；重启按固定事实与 provider 操作标记核对，不重放模型或 Native。纠正先撤下旧事实，遗忘先停止读/注入再清理正文；不因另一条事实的删除取消无关显式保存。读取核对规范正文 revision/哈希/来源标记；账号切换时检查身份预期头并清除未使用前端查询缓存。原公开 memory/provider 入口不能绕过个人 Go API。架构选择由 [ADR 0013](decisions/0013-memory-backed-personal-briefing.md)接受并分阶段落实。

[脱敏收据](verification/personal-memory-2026-11-02.json)记录：15 项固定 Provider/真实 LangChain 图契约、21 项实际 Go→Gateway API 和 9 项真实浏览器检查通过；普通 Python **244 passed / 8 skipped**，Go mod/vet/race/无 CGO 构建、Ruff/wheel、前端 TypeScript/生产构建与 token 一致性通过；本轮实际固定 Chart/Compose/单机/HTTPS 子集 **24 passed**。浏览器验证保存/中文搜索/纠正、关闭后管理/遗忘、账号切换、390px/浅深色/减少动态效果。首个缓存验收镜像遗漏旧模板中的 token import，在截图复核时发现；最终从固定源码应用全部集成补丁重建、核对全部源文件，并加入实际样式变量/控件边框检查，不能把先前仅操作通过视为最终视觉验收。

独立四服务在合计 1472 MiB 容器限额下健康，无 OOM 观测；保留证据后停止临时环境，不代表实际 2 GiB 云主机压测。没有真实模型/Native 调用、云访问、新资源、授权延期或既有本地/云端升级。自动提取、项目来源、关注主题、今日简报及一键动作仍待后续阶段；完整 MEM-01–MEM-21 未标记全量通过。原临时 SSH 授权已过期限，实际云端清理和证书续期本轮未核对。


## 2026-11-02 · M4.4b 从新对话保存明确记忆

在 M4.4a 基础上加入默认关闭的独立采集开关；新普通对话中的“请记住：我偏好简洁的中文回答。”可自动保存并从记忆列表打开原对话。采用有边界的确定性规则，仅接纳明确个人偏好/长期目标/学习背景，不调用提取模型，不把项目指令、引用、助手/通知/建议、回放或一次性提问当成稳定偏好。语义推断和自动更正仍待后续带预算实现，见[规格](specs/m4-explicit-memory-capture.md)。

Go 在真实 run 成功接纳后核对固定 SQLite 中的 owner、interactive origin、原消息 ID/正文哈希、当前 incarnation 和个人范围，原子保存来源与现有投递账本；不复制原对话正文，不改变聊天请求/响应或执行授权。存储恢复继续按原操作核对，采集失败不重发聊天。每日明确采集限每用户 50 条、实例 500 条（UTC），独立于主动聊天。旧 schema 升级保留资料和事实，自动采集默认关闭。

手动纠正推进旧采集的版本屏障；显式单事实投递仍按目标屏障复核。内部适配器在规范写入、排名及最终注入前检查来源；对观察到的删除、编辑、换代/范围变更保留单向失效标记，移除编辑记录也不会复活旧偏好。管理页隐藏失效正文并允许清理；用户手动纠正后的事实脱离旧对话来源。provider 文件事务、FTS5、格式化器与单投递队列继续复用。

[脱敏收据](verification/explicit-memory-capture-2026-11-02.json)：**25 项固定存储/图/来源契约、33 项实际 Go→Gateway API、14 项浏览器检查通过**；另用真实输入框/SDK 验证两轮流式对话，普通问答不采集、第二轮明确指令保存成功；Python **244 passed / 8 skipped**，Go mod/vet/race/无 CGO 构建、Ruff/wheel、TypeScript/前端生产构建、24 项固定 Chart/Compose/单机/HTTPS 子集与 token/JS 检查通过。浏览器检查开关、正常合成 run 的来源链接、原对话内容、来源移除后的隐藏/清理、账号切换与手机/深色模式；来源列表及手机截图已复核。完整前端 1,301 个源文件、安装后 Gateway 源码和 Linux 控制端 binary 已核对。

独立四服务在 1472 MiB 合计容器限额下健康，无 OOM 观测；证据保留后停止临时环境。仅使用合成账号和离线 Fake 对话模型，没有真实供应方/Native 调用、云访问、新资源、授权延期或既有本地/云端升级。额外提取模型调用为零，不代表真实模型质量或 2 GiB 主机容量验收。下一步为关注/任务证据与有来源的首页读模型；语义提取、项目范围、简报动作和完整 MEM 标准保留未完成状态。


## 2026-11-02 · M4.4c–e 个人关注、确定性简报和首页动作

连续完成显式长期关注、真实任务证据、最多三项今日关注、已读/暂停/完成/当天隐藏，以及最多两个有效个人目标的新话题建议。关注独立于最近 20 条，来源删除/归档/换代/范围变化隐藏旧内容；任务完成、独立验证、取消请求和最后同步分别展示。Go 继续拥有公开策略和动作账本，DeerMem 仍保存目标正文，没有新增服务或通用记忆引擎。

首页 GET/刷新只读现有记录，语义版本不随核对秒数变化，不调用整理模型或 Native。点击前预览规范问题和范围，持久 intent 后才接纳。只读跟进沿用原对话，目标建议新建有正常名称的本人对话；两种运行的工具集为空，实际工具入口仍强制拒绝。下一条普通消息不继承这次限制。Codex 单轮续接比较原项目/执行器/head 指纹，复用原 journal/ordinary driver；未知结果不盲重放、不会新建替代原生会话。原始插件与保留幂等键由公开 Go 代理封锁。

[收据](verification/personal-home-2026-11-02.json)：固定 Provider/真实图/来源/首页能力 **41 项**、实际 Go→Gateway API **43 项**、浏览器 **14 项**通过；API 包括双进程重启后的 intent/暂停/目标建议保留，浏览器包括结果/新话题命名、反馈、手机 44px 点击区、深色/减少动态、错误恢复、键盘及账号切换。Python **244 passed / 9 skipped**，Go mod/vet/race/无 CGO 构建、Ruff/wheel、TypeScript/生产构建、**27 项**固定部署/overlay 子集、共享 token 和源码对应关系通过。复核 1,302 个前端文件、28 个 Gateway 安装文件和 Linux 控制端 binary；手机及桌面截图已查看。

验收仅用合成资料、离线 Fake 对话模型与 continuation Submitter 测试替身，没有真实供应方/Native、云访问、新权限或 SSH 延期。四服务在合计 1472 MiB 容器限额下健康且无 OOM 观测，保留证据后停止临时环境；不代表实际 2 GiB 主机压测。完整 MEM-01–MEM-21 仍未全量通过：语义自动提取/归并、共享项目、历史导入、持久模型作业预算、外部订阅、真实新入口执行及性能继续跟踪。既有本地与云端未升级。

## 2026-11-03 UTC · M4.4a–e 云端升级与首页显示修正

按用户指令升级既有新加坡单机，没有创建 ACK 或其他云资源。用户单独批准一小时临时 admin/sudo SSH，禁用转发、PTY、Agent/X11；经已登录控制台核对主机密钥，上传 SHA-256 校验后的预构建升级包。升级前保留 SQLite 一致性备份、应用/配置归档及旧镜像，先核对没有活动任务。Go/Gateway 部署 `701a309`，运行配置和后续启动用的源配置同步；保留账号、历史对话/任务和加密模型文件。

首次只读准备因 Node 参数误用停止，修正后才进入正式切换。第一次正式切换发现自制包中的 Go binary 缺执行位，自动恢复旧镜像/配置，未恢复或覆盖数据库；保留失败证据，将执行位修正为 0755 并核对可执行后，第二次切换成功。公网页面又发现未保存个人时区时问候取设备时间、简报取 UTC，以及关注选择器显示 UUID 两处缺陷；`ad37588` 统一个人时区/默认 UTC 并复用既有对话标题工具。TypeScript、生产构建和共享 token 检查通过；该修正后端/Python 源码与 `701a309` 相同，仅替换前端。服务器核对 5,619 个前端源码/编译资产、28 个 Gateway 安装文件和 Go binary 哈希，原安装未混入 Fake 模型。

[脱敏云端收据](verification/personal-home-cloud-2026-11-03.json)：最终公网可信 HTTPS/API **25 项**、实际浏览器 **8 项**通过，覆盖原登录/密码、9 个旧对话及抽样消息、模型目录、个人资料/空关注/简报、默认关闭、owner/CSRF/匿名/原始插件拒绝、时区/对话名称和 5 项历史完成任务。1 个账号、9 个对话、19 次运行、5 个任务的历史行哈希以及模型文件字节保持。五服务运行正常，四个有 healthcheck 的服务 healthy，均未观测 OOM；主机 available 内存观察值约 647 MiB，不是负载或性能验收。最终深色桌面截图已查看，截图和原始私有痕迹仅留在 Git 忽略目录。

临时部署公钥已删除，在配置到期前用同一密钥建立新连接得到 publickey 拒绝；本机部署私钥随后删除，其余公钥保持。旧家庭 Agent 授权期限及配置字节未更改，未恢复链路、调用模型/Native 或创建生产测试事实/关注。记忆/明确采集/目标建议仍默认关闭，不自动导入历史。原 localhost 实例未升级；实现阶段完整本地检查保留 `701a309` 的原收据，本次不重跑或扩张其声明。完整 MEM、真实新首页 Native 入口、实际负载、旧家庭授权到期清理和证书实际续期仍需分别验收。

## 2026-11-03 用户管理 Agent 授权

用户要求从设计进入实现并上线。新增 Go 管理页/API、显式期限/范围、逐版本本机确认、取消待确认、撤销与状态观测；以主动出站 HTTPS 替代新增 SSH 账号/到期 timer 的产品化依赖，保留旧 SSH 方式与历史任务。Go 与 Worker 双向接纳、90 秒观测和单 owner 门禁在提示词外执行；过期队列不启动，在途 finish/stop 策略独立测试。见 [ADR 0014](decisions/0014-user-managed-agent-authorization.md)与[指南](agent-authorizations.md)。

Python 250 passed / 9 skipped；Go mod/vet/race/无 CGO/Linux 构建、Ruff/wheel 和 29 项固定部署子集通过；真实 Go→连接器→Worker→离线 Native 的修复、验证、幂等与撤销通过，浏览器确认待本机状态、取消与 390px 布局。本条先记录本地验收；云端上线与旧过期记录导入在实际完成后另记，不能据此推断已恢复本机执行权限。

## 2026-11-03 · M4.5 持续任务方案待用户审核

用户要求基于前项调研先制定 spec 和 plan，审核通过后再开始改造。以 `19284cd` 为设计基线，新增[持续任务/事件调度/可追溯记忆 spec](specs/m4-continuous-agent.md)、[P0–P7 实施 plan](specs/m4-continuous-agent-plan.md)和 [Proposed ADR 0015](decisions/0015-continuous-agent-control-plane.md)，在基础规格保留 FR-030–FR-032 为拟议需求。

方案复用已经实现的用户授权、出站 HTTPS、原 Worker/driver/journal 和 DeerMem；Go 保存持续工作及事件，DeerFlow 负责受限研判与秘书对话，执行仍保持一对话一原生会话。首期单仓库/Codex，先观察/本人接纳，再接入有边界的 auto；明确引用召回、预算/背压、未知结果核对、来源失效、UI 与升级回退要求。其他执行器、站外写入、语义提取和模型 Watchdog 留在后续。

所有实施项、CONT-01–CONT-19 和实机验收均未开始；本轮只检查设计文档的链接、编号及边界一致性，不调用模型/Native、不调整线上服务或权限。接受设计与实现、验证、发布分别记录。

用户进一步询问是否体现 DSH Router 思想后，明确补入独立持久 Router Session、host 工具边界、异步 Assessor/Worker 回报、已关联 Thread 直通及越范围 handoff。区分 Go 确定性 dispatcher、DeerFlow Router、Codex 任务会话和设备 Worker 服务，避免只有一个改名的聊天入口。新增 CONT-20–CONT-23；全部 23 条仍待验收，spec/plan/ADR 保持待审核。

## 2026-11-03 · README 研究定位与可复现评估方向

按用户要求在中英文 README 增加研究问题、明确标注为 Proposed 的 Router/Worker 图、Go/Router/执行会话分工、五项可测量价值，以及受控对照/消融和开放复现材料的计划。归属 DSH 与上下文工程的设计来源；不宣称新算法、已有 benchmark 或未经测量的性能提升。plan 增加 R-EVAL-01–R-EVAL-05，区分离线调度测试、真实模型质量、功能验收和注意力代理指标。

同时修正 README 中设备配对仍规划、旧临时链路仍可用、个人首页未升级云端等过时表述，保留本地授权验收和历史真实 Native 证据的各自边界。本轮仅编辑文档并核对链接、状态与中英文内容，不运行模型/Native 或上线新架构。

## 2026-11-04 UTC · M4.5 获准进入实施

用户明确批准按 spec/plan 连续开发，设计和 ADR 0015 转为 Accepted。以 `5a1ed3a` 为实现基线，先核对固定运行时、原生 journal、用户授权协议与幂等查询，再逐阶段实现。批准不代表 CONT 或比较实验已经通过，也不恢复旧云端/家庭授权。


## 2026-11-04 · M4.5 第一轮实现进入集成验收

新增 Go 工作/事件/决策与发送屏障，固定 DeerFlow 的持久 Router/无工具 Assessor 适配、原 journal 的 Native 续接、只读 GitHub 来源及来源失效检查、有界检索和工作首页。持续任务协议由设备心跳明确报告；新模块与来源默认关闭，auto 仍需有效范围和非零额度。

隔离 Compose 的合成账号通过真实页面完成两轮离线 Router 对话，使用相同 Thread；既有个人部署未作为 fixture。当前细化仍在测试，完整验收、低内存测量、真实 Provider/Native 与云端交付尚未由本条记录确认。见 [实施记录](specs/m4-continuous-agent-plan.md)。

## 2026-11-04 · M4.5 Alpha 恢复、授权与完整离线链路

`b952ee9` 在 `e172857` 第一轮实现上补齐固定授权/设备/版本检查、Assessor 独立槽、明确拒绝的持久回执、账户重认证后的只读核对、来源规则/批次快照和失效索引、原生 head 改变的显式恢复。新一轮排队清除上一轮验证标记/摘要，历史回执仍保留。新增独立 fixture 准备、API/进程中断、低内存读取、完整 Native 协议和指定旧 Go 镜像回退脚本，默认不接触个人或云端实例。

最终 Go mod/vet/race/无 CGO 构建、Python **260 passed / 11 skipped**、固定 DeerFlow **37 passed**、Ruff/wheel、TypeScript/完整生产构建、共享 token 及实际固定 Helm/Compose **29 项**通过。真实 Go/Gateway 完成两轮同一 Router Thread，并在接纳后丢 ACK/重启 Go 时核对一个原 run，perform 计数为 1。实际 ordinary driver→relay→连接器→Worker→假 Codex 两轮共用一根，两次独立测试通过；Native 在途时 Router 能处理新输入。没有真实模型/Codex 调用。

1,000 个合成工作/10,000 个事件，各 100 次、并发 1 的列表/详情/引用/搜索 p95 为 69.666/39.341/42.354/84.995 ms，四服务健康，无 OOM，容器合计限额 1472 MiB。初次误用跨架构 binary 已排除；amd64 的全量 BM25 评分搜索 p95 505.319 ms 未达标，改为最近索引匹配上限 20 后通过。结果不是冷读、真实 2 GiB 主机或 Router 对照实验。

早期 toy Worker 镜像缺 Git、MCP CLI 命令错误分别阻断准备/派发；后者留未知操作，没有重放。修正后用全新隔离实例完成原生链路。停用模块→指定旧 Go `m4c`→新镜像实际保留账号/线程/工作/journal 及未知操作，未覆盖数据库。最终 Python/Gateway 32 个源文件及前端 16 个 overlay 文件与实际镜像逐文件匹配；完整 Native 镜像早于最终 Go 验证标记修正，后者以专项及最终 race 回归验证。

同源 390px iframe 的浅深色、未授权按钮与键盘焦点已经真实检查并留截图。完整 CONT-16、更多中断/公平性、真实 GitHub/Provider/Codex、云端发布和 R-EVAL 比较仍未完成；原个人 2026 实例未升级，旧 SSH 不恢复。中英文 README、基础规格、plan、STATUS 和[使用指南](continuous-secretary.md)已同步实现/验收/部署边界。[脱敏收据](verification/continuous-secretary-2026-11-04.json)保留失败与限制。

交付核对：本轮 Git SSH/HTTPS 推送分别因公钥/凭据不可用而失败，远端 main 通过 GitHub 连接器核对仍为 `5a1ed3a`。本地提交完整保留；没有借插件另造提交链或改写远端历史。两个独立合成 Compose 已停止，数据/未知操作证据保留。

## 2026-11-04 · 持续秘书真实视口验收与前端恢复修正

用户解锁 Mac 后继续实际浏览器验收，在独立 2037 合成实例发现工作间追问草稿串用、已结束工作仍有输入，以及手机控件被后置样式缩小。现按工作保留草稿，已有原生轮次须填写明确下一步；成功回执只清除本次提交的同工作草稿。另修复未知回执后 revision/head 投影改变可能换操作 ID 的问题：页面内保留原完整请求和 ID，明确拒绝才释放，刷新后的恢复仍走服务端原操作核对。

补工作/回执/规则/建议的加载与空状态，关键读取失败时保留内容、提示过时并停写；局部规则/回执故障可独立恢复。真实 Chrome 390/1280/1440px、浅深色、键盘焦点与减少动态通过；临时 nginx 注入规则/回执 503 和工作列表过时后，写入停用、原操作核对仍可用，恢复后原两条回执和动作重新可读。普通合成用户看不到 owner 的持续工作和草稿。8 个合成阶段只验证文案与布局，不冒充真实取消/路由生命周期。

Node 24 离线意图恢复 8 项、overlay 3 项、相关部署/前端子集 24 passed / 3 skipped、Ruff/token、完整 TypeScript/Next 生产构建通过。最终运行镜像 17 个 overlay 源文件逐一一致。验收前后 run=7、Native task=2、模型预算预留=5，没有新增模型或 Native 调用；Go/Worker 未修改，未重跑上轮完整套件。新增 CI job 尚未在远端运行。macOS 后续自动锁屏时通过浏览器视口能力继续；带原设备工具缩放的截图已排除，公开截图来自新建的正常标签页。

[UI 收据](verification/continuous-ui-2026-11-04.json)与新截图保留实际范围。来源候选/凭据失效/背压的完整 UI 矩阵、真实 Provider/Codex/GitHub、云端及 R-EVAL 仍未完成。浏览器临时视口已恢复，2037 fixture 已停止且保留数据，个人 2026 与云端不变，未恢复旧 SSH 或新增真实设备权限。本轮未重试远端发布。

## 2026-11-04 Agent 授权首期上线

授权源码 `5a1ed3a` 已进入 main 并推送，云端 Go/Gateway 运行相同版本，五服务健康。原账号、数据卷、模型配置、SQLite 一致性备份与旧镜像保留；原家庭 SSH 记录只导入为已过期历史，未恢复 SSH 或新增执行授权。更新后的 Worker 必须声明 `local-grants-v1`，连接器在转发前复核能力与身份，拒绝旧 Worker 忽略授权标记的情况。固定源码最终 Python 251 passed / 9 skipped；线上 HTTPS owner 登录、管理 HTML、CSRF、到期原因及旧对话 API 共 17 项通过，见[收据](verification/agent-authorization-cloud-2026-11-04.json)。

浏览器扩展上传受本地文件权限限制，未开启该权限；临时服务器限额编译随后停止，改通过同一 GitHub 仓库的部署专用分支传输已验收 binary/wheel/脚本，核对 archive/manifest SHA-256 后进行受控切换。binary 未进入 main。线上浏览器地址访问授权被拒绝，没有换浏览器或用其他途径绕过；本次不声称通过线上视觉验收，也不声称已经在真实设备启用新授权或调用原生模型。

## 2026-11-04 · 持续秘书推送与云端发布

按用户要求，将五个本地提交与远端授权上线记录 `77c5c31` 在独立发布工作区合并为 `4636d38` 后推送 main；原工作目录中并行编写的产品文档保持原样。用户明确把本机仓库写入密钥和现有服务器受限 admin/sudo 部署密钥改为长期有效，公钥已安装、私钥仅留本机，云 SSH 保留 restrict、严格固定主机身份。

固定 `274c1b2` 的 amd64 Go、32 个 Python 源文件、5,160 个前端源/产物文件和匹配的 MCP wheel 已部署。首次准备阶段 SSH 中断时没有切换服务；保留证据后改为脱离会话、按组件裁剪上下文的准备方式。首次切换因部署脚本内嵌编辑器缩进错误自动回退原镜像/配置，未恢复数据库；修正并编译所有嵌入程序、验证 YAML 编辑后，保留首轮备份与 checkpoint 再次成功切换。

最终五服务健康，无 OOM；一致性 DB 与应用备份、原镜像保留，账号/9 个线程/19 次运行/5 条任务、模型加密文件、个人资料/记忆/关注和过期设备授权保持。MCP 使用同一源码 wheel 并离线预取、验证 lifecycle 后迁移原 profile。27 项公网 HTTPS/账号/数据/API 和 17 项授权回归通过；用户开关仍关闭、auto=0、来源未配置，零新增模型、Native 任务和设备权限。[上线收据](verification/continuous-cloud-2026-11-04.json)保留版本、产物 hash、回退和限制；未进行线上视觉、实际 Router/Provider/Codex、来源变化或负载/科研对照验收。

## 2026-11-04 · 产品文档中心与强制文档影响检查

按用户要求新增「产品文档」入口及独立 `/docs`：九篇客户使用指南、四篇技术与研究方案、一篇变更日志；暂不增加接口参考和部署指南。参考点金的读者分流方式，内容依据 DeerMate 现有实现与历史证据，明确 Alpha、默认关闭、本地验收和实验待开展边界。Markdown 为唯一正文源，目录生成阅读数据，支持搜索、章节目录、复制 Markdown 与相邻文章。

新增 `docs/DOCUMENTATION_POLICY.md`，根 AGENTS、PR 模板和 CI 引用；代码变更缺少受影响文章与变更日志，或合格的无需更新判定时检查失败，生成文件本身不能满足门禁。CI 验证来源、链接和生成同步；分支保护配置与远端 CI 实际运行仍未执行。

本地文档/overlay 17 项测试、Ruff、共享 token、TypeScript 和 Next 生产构建通过；静态检查 14 篇文章与 86 个本地锚点。真实 Chrome 仅确认桌面首页、技术文章与导航；手机视口设置后浏览器连接连续超时，手机、深色、搜索/复制交互及最终样式复验待补。记录在[文档收据](verification/product-documentation-2026-11-04.json)，不冒充全量浏览器通过。

改动保留本地未提交状态，没有调用模型/Native、更新个人实例或云端。本条新增的评估方法不代表执行了新的比较实验，也不修改历史收据。

## 2026-11-04 · 产品文档提交、代理接入与云端发布

按用户要求提交文档功能 `36e2684`，与远端已部署记录合并为 `1783dd6`，校正产品交付边界后推送 `fb5dd73`。使用匹配依赖的现有 Linux 前端镜像构建、校验 2,742 个源/产物文件，隔离运行实际 Next 文档路由后，只更新前端。首次重载误用默认 nginx 配置，原前端与配置已恢复并逐一确认，再按实际配置重载成功；保留首轮回退与备份。

公网检查发现旧代理仍将 `/docs` 送入 Go，故补产品文档专用的精确首页/子路径前端映射，保持其余后台路由；同步修改固定 Helm/单机生成器并运行实际渲染回归，合计 41 项通过。窄配置更新保留备份，运行中和源配置一并同步，未重启 nginx。43 项可信 HTTPS 页面/资源/登录/原账号数据读取通过，原数据、Go/Gateway 及执行权限保留。浏览器连接仍超时，未声明完整视觉验收。[上线收据](verification/product-documentation-cloud-2026-11-04.json)保留实际版本、内容同步及限制。

最终内容前端 `8aad210` 已完成部署，45 项可信公网检查通过，确认正式变更日志及代理技术说明已实际发布。五服务健康，2,742 个文件校验一致，后端镜像与 9/19/5 条历史线程/运行/任务保持；原备份、镜像和首轮回退证据保留，没有新增产品模型或 Native 调用。完整浏览器视觉与远端合并必需检查配置仍待补；本条仅补实际发布证据。

## 2026-11-04 · 默认秘书与设置中的记忆管理

按用户要求移除秘书独立启用/模型 ID 表单，登录后直接交代工作，沿用对话模型并在首投前冻结。Go 与内部 Python 接纳边界共同区分明确交互和背景操作；旧背景停用仍生效，启用来源不恢复旧自动预算。设置记忆页复用本人管理组件，保留采集选择；手机导航改为横向，避免挤占内容。

Go 必需检查、Python 274/11、固定 Gateway 专项 16/2、实际固定部署/overlay/文档 41 项、8 项意图恢复与前端生产构建通过。真实 Chrome 390/1280px、浅深色、键盘和记忆 CRUD/关闭后管理通过；9 项真实 Go→Gateway Fake 集成验证默认入口、两轮同根、重启核对且不恢复背景。初次缺少运行时 CSRF 的元数据检查停在 waiting_model 且不计费，修复后原输入续行。无实际模型/Native，本条不宣称云端已更新。[专项收据](verification/default-secretary-memory-2026-11-04.json)。

## 2026-11-04 · 默认秘书与记忆设置上线

与并行文档发布记录合并后推送 main，最终应用源码 `161fd29` 已部署 Go/Gateway/前端及匹配 MCP 包。额度修改曾可能隐式开启旧背景状态，已改为保留原状态；真实页面完成 0→1→0，背景始终暂停，模型预留维持 5、Native 为 0。初始 `fb4348b` 仅预构建，未切换服务；最终候选一次成功切换。

一致性数据库与应用备份、旧镜像/配置保留。5,321 个源/产物文件、32 个 Python 源文件和 Go binary 校验一致；五服务健康，无 OOM。28 项公网 HTTPS/账号/数据/API、46 项文档/资源和 17 项授权回归通过；原 1 个账号、9 个线程/19 个 run/5 条任务、模型/资料/记忆/关注保留。交互默认可用，背景仍暂停，自动额度 0，来源未配置，旧设备授权未恢复。本机永久受限部署密钥依用户要求保留。

[上线收据](verification/default-secretary-memory-cloud-2026-11-04.json)与[本地收据](verification/default-secretary-memory-2026-11-04.json)区分范围：没有线上浏览器视觉、真实 Provider/Codex/GitHub 或新研究比较。运行中的文档快照来自 `161fd29`，本条与发布后变更日志记录于 Git；本地合成环境已停止、卷及故障证据保留，临时浏览器视口/标签已清理。

## 2026-11-05 · 产品文档图示

按用户要求补六张架构与流程图，以版本化布局数据生成静态 SVG，正文提供替代文字、全文说明与原图入口；校验图片引用和生成同步，不依赖运行时 CDN。

图示提交 `c893224` 已推送并部署，2,745 个前端文件与镜像校验一致，11 项 SVG/正文嵌入与 45 项公网读取检查通过。个人资料另与即时切换前的一致性 DB 备份逐行核对一致，不以较早公共快照的变化覆盖用户设置。后端镜像、9 个对话/19 次运行/5 条任务保留；并行的未提交设计系统改动未混入该固定版本。网页完整视觉仍受工具不可用限制。[上线收据](verification/product-diagrams-cloud-2026-11-05.json)。

## 2026-11-05 · 统一设计来源与前端门禁

将设计规范重构为可解析 YAML tokens/组件配方与独立说明，由同一来源生成 React、Go 与组件 CSS；迁移第一方页面及固定上游公共组件外壳，状态成功色改为蓝色，保留真实状态和业务流程。新增静态设计门禁、构建入口检查、CI 与反例回归；不以静态检查代替完整视觉与可访问性评审，不配置新的权限或执行任务。此条为本地开发记录，不表示已发布。验证范围见 [专项记录](verification/design-system-2026-11-05.json)。

## 2026-11-06 · 登录后视觉验收与布局修正

使用生产 React、真实 Go 登录/资料/记忆接纳与全新本地数据库，配合无模型的合成运行时，完成169项页面矩阵和16项交互状态检查，覆盖六宽度、浅深色、键盘焦点和减少动态。修正平板设置内容挤压、当前导航不可见、侧栏尺寸未引用规范，以及手机浮层关闭区域偏窄。模型执行请求与最终页面脚本错误均为零。首轮失败保留为诊断，合成接口形状和焦点等待属于验收脚本修正，未混作产品问题。新增可复跑 fixture/验收脚本及[脱敏记录](verification/design-authenticated-2026-11-06.json)。未发布线上，不宣称真实运行时或全面可访问性认证。

## 2026-11-09 · 设计重构交付范围

用户将发布范围调整为仅合并 main；本轮整理统一设计、样式迁移、自动门禁与本地验收记录，不执行线上部署。合并前再次通过设计/token/文档门禁、19项设计及overlay回归与Ruff，保留2026-11-06的185项浏览器验收范围；不将历史验收描述为本日重新执行。

## 2026-11-05 · Workspace v2 产品设计提案

按用户要求先设计不开发，形成助手主导首页、默认自然记忆、近期上下文接回、原话题连续对话与“我了解的你”管理的 PRD，配八张桌面/手机/主题/状态示意图。明确普通偏好、项目约束、阶段要求与执行证据的不同职责；默认记忆不要求前置勾选，旧主动暂停和工具授权仍独立。

当前仅待审核提案；没有修改业务、启用记忆、扫描历史、调用模型或部署。图中数据均为示例，静态样式审阅不等同于浏览器验收。见 [PRD](prd/workspace-assistant-v2.md) 与[文档/图示校验](prd/workspace-assistant-v2-validation.json)。

## 2026-11-06 · 工作台提案文案修订

用户反馈文案过于像 AI 介绍产品，明确要求使用互联网运营 Agent。由产品运营文案子 Agent 逐页审稿，主 Agent 核对操作含义并应用到八张静态图和 PRD v0.2。首页改为直接说明正在忙的事与结果，“我了解的你”改名“关于你”，按钮和异常提示使用明确动作；临时对话的记录保留、暂停需本人恢复、尚未部署等含义没有删除。

保留[完整文案](prd/workspace-assistant-v2-copy.md)和替换对照，供后续实现使用。范围仍是待审核设计，未改变业务或部署；文档、结构与图示检查见[记录](prd/workspace-assistant-v2-validation.json)。

## 2026-11-09 · 工作台 v2 获准开工与第一阶段

用户批准连续实现、本地验收、推送和上线；拉取 main 780173a 并从其建立独立开发分支，接入 PRD/文案，按当前规范重新生成八张设计参考图。Go 增加版本化默认与保守旧选择迁移，临时话题在运行时创建前记录禁止读写；Python 注入按实际持久 run 解析本人话题，不能由客户端模式覆盖。普通表达、项目范围、完整页面和部署继续按计划实施，不把本阶段单元测试写成产品验收完成。

## 2026-11-09 · 工作台 v2 的记忆与助手页面接入

在 S0/S1 后接入普通表达、范围、持久有界整理、Inbox 来源及最终 Router 注入；历史整理、来源与使用记录、遗忘和阶段结束均保留迟到屏障。新增 ADR 0016。首页从真实工作和近期对话构建最多三项的确定性快照，替换营销式多输入；我的工作与关于你分开。使用指南、记忆技术文档和生命周期图已同步。

Go 全包及竞态、Python 常规 292 项、固定运行时专项 55 项、TypeScript/Next 与设计/文档门禁通过；固定专项模型为 Fake。独立本地 Docker 启动及真实登录可用，正在做真实供应方、Native 和完整浏览器验收。此记录不代表已推送或上线。

## 2026-11-09 · 工作台 v2 本地验收完成

完成真实供应方记忆闭环 16 项、独立 Worker→Codex 同根两轮及独立验证、生产 React/真实 Go 浏览器矩阵 33 项和旧镜像卷升级保留。修正手机首屏输入可见性、来源失败遮盖、临时创建丢回执后跨刷新核对，以及模型提取内部 action 的 30 秒截止冲突。持久调用先留标记，后台回执不产生重试模型；失败与未知作业均未重放。

Go mod/vet/race/无 CGO、常规 Python 292 项、固定专项 59 项、真实固定部署契约 59 项、Next 生产构建与设计/文档门禁通过。完整浏览器到家庭 Agent 与研究对照未在此验收中开展；远端发布另行记录。

## 2026-11-09 · 工作台 v2 推送与既有云端上线

应用 595f654 已推送 main，十个远端 CI job 全部通过。修正设计测试 job 漏装共享测试依赖；发布预构建阶段发现云端旧 Docker 不支持 COPY --chmod，改用已带可执行模式的普通 COPY，未在准备失败时切换服务。随后完成一致数据库/全量 home 与配置备份、同源 Go/Gateway/前端升级、旧列值及模型/原生记录/授权文件哈希核对。

22 项可信 HTTPS/API 与 13 项公网 Chrome 登录/页面检查通过。原 1 账号、9 对话、19 run、5 任务保留；安装 owner 依已批准设计采用 V2 默认，其余旧选择不自动迁移。备份和旧镜像保留，家庭到期授权没有恢复。[上线收据](verification/workspace-v2-cloud-2026-11-09.json)与本地真实模型/Native/旧镜像升级证据分开。发布文档再独立同步到前端，不以元数据提交冒充新的模型或执行验收。

## 2026-11-09 · 发布文档完成同步

工作台发布说明 bfa91aa 单独更新前端，2,822 个文件哈希与隔离 Linux 文档渲染通过；23 项可信公网检查覆盖十四篇正文、二十个 JS/CSS/字体资源和原账号工作台/API读取，最终 13 项浏览器检查再次通过。Go/Gateway/nginx/edge 镜像与历史记录、授权保留。功能 595f654 与文档 bfa91aa 的十个远端 CI job 均已实际通过；本次仅追加发布证据，未触发新的模型或 Native 验收。

## 2026-11-10 · README 收敛到已发布产品与真实操作

中英文 README 去掉过时中间状态与重复验收叙述，保留私人助手定位、启动路径、Go/DeerFlow/Worker 分工、Router 研究问题及尚未完成的接入范围。替换 Python-first 概念头图与概念视频入口，使用当前真实界面截图、短操作录屏和轻量 GIF。旧素材留在历史路径，不伪装成当前功能。

录屏环境是全新无模型、无设备授权的本地实例，展示真实记忆保存、更正与空临时话题；没有编排模型回复或执行 Codex。范围与复现见[媒体说明](media.md)，仅仓库文档和素材变更，没有部署新的应用版本。

## 2026-11-10 · README 架构叙事与科技感视觉提案

用户认为前轮视觉与操作视频过于平实，要求先给方案，并明确委派 UI 设计子 Agent 美化。本轮以 main `9ed993a` 为基线建立独立设计分支，完成[架构品牌方案](prd/readme-tech-v3.md)、[文案骨架](prd/readme-tech-v3-outline.md)及[高保真预览](prd/readme-tech-v3-review.html)。主视觉改用分层鹿标控制核心与有职责的信号链路，突出 Go 接纳、持续协调与独立执行、原生会话、来源记忆和结果证据。

设计师提供 SVG 场景和六格分镜，主 Agent 复核技术语义并确定性导出 36 秒概念片、6 秒 GIF 和 PNG。概念片是架构演绎，规划适配器明确标注，不冒充真实执行、性能比较或 E2E 加密。浏览器、媒体与文档验证范围见[设计验收记录](prd/readme-tech-v3-validation.json)。主 README、产品行为及线上版本均未替换；正式 README 接入属于后续交付。

用户随后要求先提交一版，再直接提交到 main：设计提交 `6414ecb` 已先推送独立分支，本次连同当前交付记录合入 main。根 README 和线上应用版本不受此交付影响；设计验收收据保留原时间与合入前范围。本次仅追加交付状态，重新核对文档生成、影响记录与差异格式；浏览器、媒体和产品运行时没有因推送重新验收。

## 2026-11-12 · 标准调用链核心与独立 ARMS 适配

按用户要求，新增默认关闭的 OTel/OTLP 核心和 ADR 0017，厂商配置留在部署层。Go 与 Python 通过有界 HTTP/MCP/Relay 元数据及独立首次绑定表关联异步操作与 Worker；不把上下文写进模型提示或业务指纹。记录模型/工具/记忆读取、原生协议轮次与可见工具事件、独立验证；内容白名单与导出失败保持原授权、幂等和执行策略。

实际 OTLP 验收发现系统代理阻断本机接收，以及 Python 随机 ID trace flags 与 Go SDK 的互通问题，已修复并增加跨语言回归。两个隔离 Docker 轮次保持同一原生根，接收数据验证四服务完整父链，私有标记匹配为零；模型与原生均为合成协议，没有真实模型额度消耗。324 项常规、76 项固定运行时、Go 全包竞态/构建、真实固定 Helm/Compose 和文档/设计门禁通过。详见[验收收据](verification/observability-2026-11-12.json)。

补充可替换后端说明、ARMS 私有配置预检/单 Span 探测、产品技术文章与新图示、待发布日志及 CI 协议 job。当前独立分支完成本地实现和验收，尚未合入 main、未升级线上；用户确认暂无 ARMS 配置，真实接收/索引、AI 展示和原生内部子链需另行验收。

## 2026-11-12 · ARMS 发布准备与标准跨度角色

按用户要求将 66d3088 快进到 main，11 个远端 CI job 全部通过；原账号登录和九个历史话题基线已保留。通过独立浏览器取得北京工作空间公网接入配置，本机与新加坡云端的独立 OTLP probe 均被接收。接收与索引分开验收，尚未在本条记录时切换线上。补齐 HTTP/MCP、模型和异步派单的标准 SpanKind；配置、权限与业务指纹保持原约束。


## 2026-11-12 · ARMS 接入、main 合入与生产升级

ce7ce59 的 11 个远端 CI job 全部通过，包含真实 Go→Relay、完整 Gateway local/SSH 与固定镜像检查；既有新加坡单机完成一致备份、三镜像升级、安装内容哈希和旧表列值核对。活动 MCP 从旧 uvx wheel 显式切换到当前 Gateway Python，逐字段保留其他设置及原 relay 权限。20 项可信公网账号/API/资源与原数据保留检查通过。

现有北京工作空间接收服务器 probe，并按 Trace ID 查到同一秘书会话的两轮真实模型调用，包含持久派单、记忆读取与模型耗时。此前四服务合成协议数据作为诊断 protobuf 另行导出，保留原时间与 Span ID，ARMS 首轮展示 47 个跨度、原生轮次和独立验证；没有重放执行或调用真实 Codex。新加坡原账号、九个历史会话、模型与设备授权保留，家庭接入未恢复。详见[上线收据](verification/observability-cloud-2026-11-12.json)。

更新部署样例以覆盖 CloudMonitor 2.0 的三项写入头，补充旧 profile 和 Docker env-file 的迁移注意事项；厂商差异只保留在配置与运行手册。专属 AI 视图、原生/Pilot 内部子链及新的真实云端到家庭执行仍未验收。


上线后的文档前端同步 73040b4，2,823 个文件哈希、隔离 Linux 与 23 项可信公网检查通过，十四篇文章和二十个资源均可访问；最终六项桌面/手机页面检查无脚本错误。Go/Gateway 与授权未再变更。文档发布源的 11 项 CI 最终全通过；Mac 首轮已有 RPC 子进程退出测试遇到 PermissionError，本机 100 次未复现、单项重跑通过，未声称修复。ARMS 中第二轮模型实际返回的用量为输入 793、输出 29 Token，保留在脱敏收据中；没有据此推算费用。最后的交付记录提交只更新元数据，不改变已经验收的应用或页面正文。


## 2026-11-12 · 流式 HTTP Span 生命周期修复

实际网页工具 Trace 显示 42.44 秒整体请求只有 41.28 毫秒客户端跨度。通过真实 SSE 的响应头/分块/EOF 屏障稳定复现，移除 RoundTrip 返回时提前结束的逻辑；响应消费、关闭、取消与失败统一为一次终止，原字节/错误及双向读写能力保留，未启用追踪时不包装 body。Go 全包 race、mod/vet、无 CGO 构建和文档门禁通过；发布及真实 ARMS 前后结果另记 STATUS。本次修复不恢复设备授权，不将 MCP 缺跨度解释为已解决。


流式计时修复源码 bc69dab 已合入 main，11 项远端 CI 全通过；只更新既有 Go 控制面，保留 Gateway/前端镜像、原账号与十三个历史话题、模型和设备授权。24 项实际部署合同与二十项可信公网检查通过。真实页面的临时话题输出后，ARMS Trace 5909596c62a19300cd85e02238536cb9 显示客户端 18.60 秒、Gateway 18.51 秒、模型 17.53 秒；客户端已覆盖完整响应流。前后请求内容不同，这不是性能提升比较。见[上线收据](verification/http-stream-timing-2026-11-12.json)。此后交付记录只更新工程文档，不修改已发布应用或产品页面。

## 2026-11-12 · 组件化前端与 Design issue #2

基于最新 main `3b28af7`，按 P0–P5 完成 [前端重构](specs/frontend-overhaul.md)：YAML 生成 Tailwind 语义主题，建立 typed primitives / patterns / features / routes，迁移工作台、记忆、聊天、持续秘书、设置、登录、文档及 Go/tooling 外壳。删除旧 CSS，预算 1100 行只能收紧，新增原生控件/视觉 class/内联双语等门禁反例与合成浏览器 CI。

生产构建、lint/types、全量前端与 Python/Go 检查、九个浏览器脚本和组件原基线比较通过；实际数量及范围见 STATUS。验收修复了列表与设置裁切、聊天标题和发送形状、隐藏 Tooltip 拦截 Esc，以及本地代理遗漏 SDK 路径重写。保留业务权限、操作身份与记忆屏障；全新 Fake Gateway 验证来源删除、关注重复操作和两轮真实 Composer/SDK，不调用真实供应方或 Native。

[PR #10](https://github.com/mzydmer/deermate/pull/10) 独立交付评审，截图只保存在私有目录；本次不合入 main、不部署，不把本地矩阵称为全面可访问性认证。

## 2026-11-13 · 组件化工作台合并与云端升级

用户在本地验收与 PR 检查通过后明确授权 main 合并和线上部署。PR #10 合并 `06f09d5`；合并后菜单焦点断言的时序失败由 `85f768e` 改为严格等待原触发器恢复焦点，后续 12 项 main CI 全通过。

完成三个候选镜像、完整源码/文件哈希与服务器 Linux 隔离启动。第一轮入口关闭期间发现固定上游对 17 条已结束 run 的 pending 证据执行恢复，数据守卫触发后回退原备份与旧镜像；确认业务字段未变，旧版本已完成同样恢复后，以新一致备份再次逐字段核对通过才开放入口。原账号、14 个话题、模型/个人设置/授权保留；HTTPS 与真实浏览器无任务投递验收通过，详情见上线记录。产品发布说明快照另行同步，未调用真实模型或 Native。

发布文档 `69bf1ce` 已单独同步线上前端，2869 个安装文件逐项校验，24 项正文/资源与 8 页手机/桌面浅深色浏览器复验通过，最终 26 项 HTTPS/API 再次通过。Go/Gateway、历史记录和授权保持，发布说明提交的 12 个远端 CI job 全通过；后续仅追加工程验收事实，无需重建运行时。

## 2026-11-13 · 真实交互走查与对话高度修正

真实临时对话两轮分别验证了过期授权的阻断与公开网页读取。流中刷新保持原操作；合成记忆经保存、纠正、取消/确认忘记后清理。未续期授权、未执行 Native；模型完成不等于命令执行成功。手机内容加载完成后暴露临时说明撑高页面及绝对定位提示贴底，改用有界 flex 分配与正常文档流，并扩展浏览器合同覆盖已有话题和历史分页响应。交付与最终验证见 STATUS，不把初步走查记录当成已发布修复。

## 2026-11-13 · 统一 DeerFlow 构建与验证版本（Issue #9）

新增 `deploy/deerflow.lock` 与标准库读取/checkout 校验器，消除构建、验证、前端工具及 CI checkout 的重复 SHA。保持现有上游提交，非法锁不导出 CI ref，错误 HEAD 输出 expected/actual 并保留现场；构建预检先于 Go/Docker，Gateway 预检先于进程启动。实际版本写入构建收据、镜像标签、Helm annotation、前端/本地/单机和 Gateway 收据。历史 ADR 与已提交收据未改写。

本地全量 371 passed / 6 skipped，实际 Gateway local/SSH 及纯驱动合同通过；最终受影响合同 60 passed。产物核对发现 Worker 模式额外生成的 ConfigMap 漏标，补齐后两种真实 Helm 模式均通过。前端固定归档/overlay 准备、实际 Helm CLI 和单机包版本一致；Ruff、wheel、设计/token、文档影响及七幅图通过。远端镜像/前端 CI 与实际 main 合入另记交付，不以本地准备代替镜像构建；无需部署运行服务或恢复设备授权。

修复 main `2d7d5f6` 的 [CI 43396448018](https://github.com/mzydmer/deermate/actions/runs/43396448018) 12 项 job 全通过：Linux 五镜像、非 root 认证/凭据/MCP/SSH 和生产前端 HTML、前端生产构建/lint/types、3529 项单元与 103 项浏览器合同。实际 ACK/前端/Gateway 日志的完整 SHA 一致；构建和前端版本收据纳入 artifacts。Issue #9 的三项验收标准已完成并关闭；后续提交只同步此工程交付记录，无需更新运行应用。
