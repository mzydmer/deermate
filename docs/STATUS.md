# 当前开发状态与 Agent 接续

最后核对：2026-10-26。历史见 [EVOLUTION.md](EVOLUTION.md)。这是开发 Agent/维护者更新的版本化快照，不是自动监控服务。

## 当前交付

| 项目 | 当前事实 |
| --- | --- |
| 阶段 | M1–M2.5 已实现并有对应证据；M4.1 首个只读秘书工作台正在完成最终浏览器回归 |
| 分支 | `feat/deermate-workspace`，继承运行栈和 ACK 包，新增版本化前端 overlay |
| Worker/MCP/SSH 运行代码 | 仍为 [`f7804ee`](https://github.com/mzydmer/deermate/commit/f7804eee9f45647222ef5a48e8d19d342a161d1b)；本次改动集中在前端 overlay、构建和本地配置种子，不改 Worker/MCP/SSH 核心 |
| Gateway 验收工具 | [`728deb7`](https://github.com/mzydmer/deermate/commit/728deb7df1553f10c2d016b91607a615961d2b10) 新增 `--transport ssh`、`--replay`；收据脚本哈希 `aaa2934058d0…` |
| ACK 部署 | Python 配置/ACR 构建/Helm 安装脚本已准备；本轮同步修正非 root 用户身份、Node 前端启动与构建网络重试；未连接 ACK/推送 ACR |
| 本地运行 | 用户目录 Docker Desktop 已启动；Gateway/前端/nginx 三个健康容器，入口 `http://localhost:2026`；独立 host Worker/SSH 运行 |
| 主线/PR | 上次核对 `main` 为 `e9f228d`，无开放 PR；[比较分支](https://github.com/mzydmer/deermate/compare/main...feat/deermate-workspace) |
| 发布 | 源码 alpha `0.1.0a1`；未合并主线、未发布 PyPI 或正式 release |
| 下一步 | 本轮按用户选择先交付页面/登录/真实 Codex；云端凭据之后再接 ACK。聊天模型、真实家庭账户/设备另行配置验收 |

运行代码与验收工具哈希不随纯文档提交改变；文档 HEAD 可以继续推进。接续时核对 Git 和远端状态。

## 已实现

- Python API/CLI、SQLite 持久任务/会话/事件、幂等与策略快照；Codex app-server、中断/同会话继续、表单、独立 worktree、diff 和管理员验证命令；时限、并发、显式恢复和 loopback 鉴权边界。
- 三个 stdio MCP 工具，Worker 独立运行。真实上游 Gateway/SQLite、原始 HTTP 查询/取消、后台轮询可通过本地 HTTP 或 SSH 使用同一 Worker。
- 管理员 SSH 注册包含显式 known_hosts、专用密钥/token、期限、预期实例及唯一 loopback 目的地。禁用默认配置/agent/认证回退，不执行 shell/SFTP。
- 每个 HTTP 操作重新检查授权、凭据和实例；到期/禁用/移除拒绝访问。凭据内容轮换重新认证，注册字段变化要求新进程；空闲隧道默认 60 秒过期，受正在执行的有限 HTTP 操作约束。
- 持久 Worker `instance_id`；远程 MCP 句柄为 `instance_id:task_id`。断线重建传输不自动重发修改请求；丢响应由相同幂等键显式恢复。撤权不代表已接纳的任务停止。
- M2.3 一条命令启动真实 Gateway → MCP → SSH → Worker，同一收据证明修复/验证失败、Gateway 重启、SSH-only 失联/重连、撤权/取消与 Worker 恢复；生成可离线回放的单文件 HTML。

使用：[本地](local-worker.md)、[DeerFlow](deerflow.md)、[SSH](ssh-worker.md)、[组合演示](demo.md)。设计：[SPEC](SPEC.md)、[M2.3](specs/m2-gateway-ssh-demo.md)、[ADR 0004](decisions/0004-ssh-loopback-transport.md)。

## 本次工作 · M4.1 DeerMate 前端与动效

用户要求安装 transitions-dev、transitions-polish、text-to-lottie 并重构前端。三项 skill 已从作者固定版本安装到本机 Codex 目录，版本/许可见 [前端 NOTICE](../frontend/NOTICE.md)。未把 skill 集合入库。[功能规格](specs/m4-workspace-refresh.md)、[ADR 0006](decisions/0006-frontend-overlay.md)、[构建与验证](../frontend/README.md)。

源码位于 `frontend/overlay`，Python 仅在临时 Git archive 构建上下文应用 hash 校验的补丁；固定上游 checkout、认证逻辑与 lock 保持不变。本地和 ACK 共用 overlay，新增 `build --frontend-only`。页面包含品牌登录页、默认私人工作台、真实任务筛选/证据抽屉、原始记录和会话草稿交接，支持深色/手机/减少动态效果。

任务列表限最近 20 个对话、每个最多 20 条，失败/部分结果不冒充完整数据或成功零计数。MCP 已配置不代表在线；Claude/DeepSeek Harness 标明规划中；模型未配置时只准备草稿，不触发模型任务。停止/继续仍通过原对话面板/CLI，设备探测、完整时间线和专职路由未完成。

本地 MCP 只读配置接口此前因只读目录不能创建 sibling lock 而 500；init 改为向 owner-only home 普通文件复制种子，每次 up 重新应用。GET 已实际返回 200，专用凭据/staging 仍只读，未扩展宿主权限。

首轮生产镜像、TypeScript 与 13 项真实浏览器检查通过，使用既有已完成任务，没有模型提交。原创透明 Lottie 已在官方 Skia Skottie player 检查 0/45/89 帧，产品内也已渲染。最后补齐默认入口、易读验证摘要、主题对比度与关闭焦点恢复，最终构建/浏览器收据待完成后追加。常规回归 94 passed、6 skipped（73.59 秒）；实际 Chart/本地/overlay 用例 22 passed（2.00 秒）；Ruff 通过。未用旧 CI 代替新 overlay 证据。

## 历史验证 · M2.5 本地 Docker 与真实 Codex

[使用说明](local-docker.md)、[规格](specs/m2-local-docker.md)、[有限收据](verification/local-docker-2026-10-26.json)、[实际工作区截图](assets/local-workspace-2026-10-26.png)。用户明确选择先完成页面、登录与真实 Codex，聊天模型暂不配置。

- 官方 Intel Docker Desktop 4.96.3 安装到用户 Applications；Apple 签名和 DMG 校验已记录。Engine 29.9.2、Compose 5.6.1、Buildx 0.38.1 与 hello-world 通过。Mac 锁屏，图形首次设置界面未操作；后台引擎可用。
- 本地构建四个镜像，运行 Gateway/前端/nginx，唯一映射 `127.0.0.1:2026`；非 root、drop ALL、无 Docker socket/宿主目录挂载。允许的生成配置和专用 SSH 凭据通过 Docker API 放入命名卷，不依赖 Mac Documents 文件共享。
- 14 项实际 Gateway → MCP → SSH → host Worker 检查通过：真实 Codex `0.164.0-alpha.11.1` / `gpt-6.1-sol` 完成一行修复，独立 unittest 通过、diff 返回；重复提交仍为同一 Worker 任务和 attempt 1，SQL 不创建第二个 owner；Gateway 重启保留登录、原 SQL ID 和原生会话结果。
- 隔离 Linux Chromium 实际填写登录表单，进入 `/workspace/chats/new`，认证接口确认 session，四项浏览器检查通过，无 page errors，已查看截图。它使用私有 Compose 网络和全新浏览器 context，未访问锁屏 Mac 桌面或个人浏览器资料。
- 已实际执行完整 profile 的 `down`/`up`，重新登录和读取原任务通过，原 Worker 实例/原生会话/attempt 保留；重启后的新 SSH capabilities 查询通过，未增加模型任务。当前三个容器健康，保留运行。
- 常规 `pytest`：91 passed、6 skipped（49.68 秒）；实际固定 Chart/本地策略 19 passed（2.23 秒）；Ruff 与 wheel 通过。[`bf02720`](https://github.com/mzydmer/deermate/commit/bf027200b68af6c6ec89505ad8621e6fadd41088) 已推送；[CI 40295603001](https://github.com/mzydmer/deermate/actions/runs/40295603001) 现已核对六个 job success；[ACK 镜像收据](verification/ack-package-2026-10-26.json)来自 ZIP digest 已核对的 artifact `12638651102`，六项镜像探针通过。该证据绑定 `bf02720`，在本轮前端 overlay 之前。

本地 owner 密码仅在 `.deermate/local-docker/admin.json`（0600）；原生账号在主机上使用，不复制 `.codex` 目录进容器。模型列表为空，本地专用 owner/key 提交入口只代替模型选工具，不进入 ACK 镜像。生成密钥 SSH 开发服务不代表实际系统 OpenSSH/账户、双机/NAT/云端。完整聊天、通知和专职路由未宣称完成。

## 历史验证 · M2.4 ACK 部署包

用户明确要求 ACK，取代此前暂缓 Kubernetes 的建议。[部署指南](ack-deployment.md)和 [ADR 0005](decisions/0005-ack-control-plane.md)定义单实例控制端：官方固定 Chart、扩展 Gateway 镜像、20Gi RWO 云盘、Recreate、默认鉴权和私有 port-forward，Worker 可后续启用。部署脚本使用 Python 3.12+；不创建集群、不开放公网入口、不把 Codex/桌面搬进控制 Pod。

本地检查：14 项部署用例通过，包含两种实际 Chart 模式、拒绝扩权/多写者、Secret 私密输入与文件复制；最终常规回归 86 passed、6 skipped（49.01 秒）。清单已实际经 Helm 3.19.0 post-renderer 输出，Secret 内容脱敏；固定上游 AppConfig 已加载并接受生成的模型/存储/工具配置。源码仍使用此前 Worker/MCP/SSH。

[CI 40266316155](https://github.com/mzydmer/deermate/actions/runs/40266316155) 在 `ca23f2c` 完成：两平台常规检查、原生驱动、Gateway local/SSH 和新增 ACK 共六个 job 均 success。ACK job 实际构建 Gateway、前端、nginx、工具四个 linux/amd64 镜像；Gateway 以 UID 1000 就绪，拒绝匿名任务访问，MCP/SSH 导入与非 root 凭据复制均通过。

[保存证据](verification/ack-package-2026-10-25.json)来自已下载且校验 ZIP digest 的 CI artifact `ack-package-verification`（`12626344052`），包含脱敏清单与真实镜像探针收据。保留证据绑定 CI 提交、上游 pin、源码文件哈希和镜像 ID；不是公开镜像发布。未执行用户 ACK 安装、ACR 推送、模型调用、前端登录或真实家庭设备连接。

## 历史验证 · M2.3 Gateway/SSH 组合

| 检查 | 实际结果 |
| --- | --- |
| 常规 `python -m pytest -q` | 74 passed、4 skipped，49.84 秒；跳过两种上游驱动及两种 Gateway opt-in 用例；一条已有 Starlette 弃用提示 |
| 实际 Gateway pytest | 2 passed，92.59 秒；完整固定上游后端，local/SSH 两种模式分别通过 14/21 项检查 |
| 保留证据 | [SSH 组合收据](verification/gateway-ssh-2026-10-25.json)、[回放 HTML](assets/gateway-ssh-demo.html)；最后一项检查 +44.779 秒，含源码/fixture/renderer 哈希、依赖、实例/任务/会话 ID 与 SSH 计数 |
| 回放页面 | 浏览器检查单步、10×播放和全部 21 项事件；无控制台警告/错误；已查看窄屏布局 |
| Ruff | `AGENTS.md` 所列检查通过，包含新增两个演示脚本 |
| wheel | `python -m build --wheel` 通过，仍为 `0.1.0a1` |
| 该阶段 CI | [40255200451](https://github.com/mzydmer/deermate/actions/runs/40255200451) 在 `728deb7` 完成并 success；两平台常规检查、实际上游驱动、local/SSH Gateway 共五个 job 均通过 |

环境：macOS/Python 3.12.14；控制端 AsyncSSH 2.24.1、cryptography 48.0.1；固定上游 `a1b89d0` 使用原始 lock，Gateway 环境 cryptography 50.0.0。凭据均临时生成，无真实模型、用户密钥、真实 SSH daemon 或系统配置修改。提交测试入口仅替代模型选工具；成功/失败验证经 Gateway 返回，原始 diff 由只读 Worker 观察连接取得。

收据与当前源码哈希已核对，HTML 嵌入同一收据。保留文件没有私密路径、密钥、token、原始日志或数据库。CI 仅上传有界 JSON/HTML。

已核对本次 artifact：`deerflow-gateway-local`（`12622301410`）、`deerflow-gateway-ssh`（`12621728883`）、`ssh-receipt-ubuntu-latest-py3.11`（`12621993322`）、`ssh-receipt-macos-latest-py3.12`（`12621764111`）。Gateway 两包各包含该模式的 JSON/HTML；artifact 元数据与上传步骤已核对。

## 历史证据与范围

- M2.2 [SSH 协议收据](verification/ssh-transport-2026-10-25.json)保留 22 项用例：身份、凭据、期限、撤权、轮换、丢响应和显式幂等恢复。固定上游驱动 local/SSH 两变体已通过。此前 [CI 40206131865](https://github.com/mzydmer/deermate/actions/runs/40206131865) 在 `96ca52b` 四组均 success，核对过两平台 SSH 和本地 Gateway 三个 artifact；不把旧 CI 扩展为本次新增验收工具证据。
- [旧 Gateway 收据](verification/deerflow-gateway-2026-10-25.json)属于原本地路径及旧源码，14 项检查；[CI 40201412129](https://github.com/mzydmer/deermate/actions/runs/40201412129) 四组通过。
- M1 `7dfe34a` 的 [CI 40175946902](https://github.com/mzydmer/deermate/actions/runs/40175946902) 两组通过。既有真实 Codex 验证使用 `0.164.0-alpha.11.1` / `gpt-6.1-sol`，完成修复、独立测试、diff 和同原生会话中断/继续。方法见 [local-worker.md](local-worker.md#verification)；原始临时日志未保留；本轮另有真实 Codex 修复，见 M2.5 收据。

## 未完成或未证明

| 范围 | 边界 |
| --- | --- |
| 真实双机/OpenSSH 账户 | 未部署验收；当前是同机真实 SSH 协议 fixture，未修改用户主机或账户 |
| NAT、反向隧道、设备配对、自动密钥注册、中继 | 未实现；现有传输要求直接可达 SSH 端点 |
| 秘书模型派单、通知和完整对话 | 未配置/未验证；空模型通知 run 无法完成。页面/登录已单独通过，但验收提交入口仍替代模型选工具 |
| 表单/review/recovery 秘书入口 | 三个 MCP 工具不自动回答、审批或恢复；现有 CLI 可在授权内处理 |
| 多岗位路由、Claude/DSH/Qoder、GitHub 维护、调研/邮件/桌面 | 后续阶段 |
| 硬崩溃/孤儿进程、历史库升级、生产隔离/脱敏/加密/总配额 | 尚无完整实现或验收，不由有序重启和 fixture 推断 |

删除服务端公钥不会自动断开已认证会话；立即撤权还需终止对应会话。已接纳任务按 Worker 策略继续，需要停止时使用仍有效的本地权限。见 [SSH 撤权说明](ssh-worker.md)。

此前 PR 创建遇到连接器写权限与浏览器限制；当前没有开放 PR，代码保存在开发分支，未声称合并或发布。

## 下一项工作

1. 本地保持可运行；按用户选择暂不接聊天模型。云端凭据准备好后，按 [ACK 指南](ack-deployment.md)使用用户 ACR 和明确 kubeconfig context 安装控制端。
2. 对明确注册的真实设备验收受限 OS/OpenSSH 策略、网络可达性与服务重启；不扫描或登录未注册主机。
3. 配置模型后单独验证通知和聊天入口；保留任务身份、取消确认和外部输入权限边界。
4. NAT/反向连接独立设计，再扩展专职 Agent 路由与工作台。

按 [AGENTS.md](../AGENTS.md) 接续；行为变化更新 spec，有意义结果追加 EVOLUTION，当前状态维护于此。
