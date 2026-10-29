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
