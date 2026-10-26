# 当前开发状态与 Agent 接续

最后核对：2026-10-26。历史见 [EVOLUTION.md](EVOLUTION.md)。这是开发 Agent/维护者更新的版本化快照，不是自动监控服务。

## 当前交付

| 项目 | 当前事实 |
| --- | --- |
| 阶段 | M1–M2.5 执行链路、M4.1 前端已有证据；M4.2 Go 已验证；M4.3 统一设计规范和页面风格已实现，本地验收已通过 |
| 分支 | `feat/vercel-design-system`，基于 `e7db6dd` Go 控制端 |
| 语言边界 | Go 控制端；内部 DeerFlow 和现有 Python Worker/MCP/SSH 保留。取代原控制端 Python-only 要求，见 ADR 0007 |
| 用户/管理 | Go 兼容原 UUID/密码/偏好；会话、角色、停用、重置密码、最后管理员保护、CSRF、审计及 `/admin` 页面 |
| 本地运行 | Go/control、Gateway、前端、nginx 四个健康应用容器；入口 `http://localhost:2026`；独立 host Worker/SSH 保留 |
| 当前验收 | Go 迁移历史 27 项 API 检查；本轮 25 项浏览器检查（含主题/手机/管理弹窗），原任务仍可读，模型任务 0 |
| ACK 包 | 五镜像构建/Go sidecar/私有 Service/loopback runtime 已接入；实际 Chart 校验通过；未连接 ACK/推送 ACR |
| 交付 | 源码 `4af38d6` 已推送 `feat/go-control-plane`；Go 轮次 CI 40313922279 七个 job 均已成功；本轮设计变更在 `feat/vercel-design-system` 收尾 |
| 发布 | 源码 alpha；未合并主线、未发布正式 release |
| 下一步 | 秘书模型配置、项目级授权与专职 Agent 路由；云端凭据提供后再进行 ACK 实际部署验收 |

运行代码、历史证据与本轮 Go 变更应分别核对；文档 HEAD 可以继续推进。

## 已实现

- Python API/CLI、SQLite 持久任务/会话/事件、幂等与策略快照；Codex app-server、中断/同会话继续、表单、独立 worktree、diff 和管理员验证命令；时限、并发、显式恢复和 loopback 鉴权边界。
- 三个 stdio MCP 工具，Worker 独立运行。真实上游 Gateway/SQLite、原始 HTTP 查询/取消、后台轮询可通过本地 HTTP 或 SSH 使用同一 Worker。
- 管理员 SSH 注册包含显式 known_hosts、专用密钥/token、期限、预期实例及唯一 loopback 目的地。禁用默认配置/agent/认证回退，不执行 shell/SFTP。
- 每个 HTTP 操作重新检查授权、凭据和实例；到期/禁用/移除拒绝访问。凭据内容轮换重新认证，注册字段变化要求新进程；空闲隧道默认 60 秒过期，受正在执行的有限 HTTP 操作约束。
- 持久 Worker `instance_id`；远程 MCP 句柄为 `instance_id:task_id`。断线重建传输不自动重发修改请求；丢响应由相同幂等键显式恢复。撤权不代表已接纳的任务停止。
- M2.3 一条命令启动真实 Gateway → MCP → SSH → Worker，同一收据证明修复/验证失败、Gateway 重启、SSH-only 失联/重连、撤权/取消与 Worker 恢复；生成可离线回放的单文件 HTML。

使用：[本地](local-worker.md)、[DeerFlow](deerflow.md)、[SSH](ssh-worker.md)、[组合演示](demo.md)。设计：[SPEC](SPEC.md)、[M2.3](specs/m2-gateway-ssh-demo.md)、[ADR 0004](decisions/0004-ssh-loopback-transport.md)。

## 本次工作 · M4.3 统一前端设计规范

用户要求采用 Vercel 风格，并让后续前端持续遵循统一指导。根目录 [design.md](../design.md) 作为当前设计规范，已接入 AGENTS、贡献指南和前端 README。覆盖色彩/字体/间距/圆角/组件、页面模板、真实任务状态、动效与验收流程；采用 DeerMate 自有品牌。

React 与 Go 管理页共用 [canonical tokens](../frontend/overlay/src/styles/design-tokens.css)，Go 内嵌副本由同步脚本生成。构建和 CI 检查两端一致，避免重复主题；登录页、工作台与管理页已采用中性配色、无衬线排版、细边框与可读字号。最终 25 项浏览器检查通过（无 page errors、无模型任务）；包含登录标题无衬线、共享浅/深色、手机字号/触控、原任务、Go 密码弹窗关闭/焦点/提交。未安装外部 UI 库或运行时字体/CDN 依赖；Geist 字体当前使用可用的本地/系统回退。

[本轮收据](verification/vercel-design-2026-10-26.json)与[工作台截图](assets/vercel-workspace-2026-10-26.png)记录实际范围。标准前端 Docker 构建通过；最后的登录字体/输入边界修正在已核对 package/lock 完全一致的标准镜像依赖上重新编译，来源与镜像 ID 已保留。Go 7 项测试通过（6.798 秒），实际 Chart/本地/overlay 22 passed（2.99 秒），Ruff、token 同步与文档链接检查通过。

## 历史工作 · M4.2 Go 主服务与管理后台

用户明确改用 Go 维护主后端、管理后端、用户登录和前端接口。[专项规格](specs/go-control-plane.md)、[ADR 0007](decisions/0007-go-control-plane.md)、[Go 后端/API](../backend/README.md)。Go 采用标准库 net/http、纯 Go SQLite 与 bcrypt，独立镜像以 UID 1000 运行。主 API 和管理 API 是同一二进制内的模块/权限边界，不重复维护账号。

Go 接管浏览器和 SSR 登录，使用摘要持久化的随机会话与会话绑定 CSRF；更改角色、密码或停用会撤销会话，保留最后一个活跃管理员。管理页 `/admin` 可创建、启停、变更角色和重置密码，并读取近期审计。前端原 API 形状继续兼容；Agent API 经真实用户/版本绑定的短期 JWT 适配到内部运行时，不使用其 internal 超级身份。

本地先做 SQLite 在线备份，保留原 UUID、密码和任务归属，只要求重新登录。27 项真实 API 验收通过：跨用户访问拒绝、执行权限、CSRF、角色撤权、密码重置、停用、退出和 Go 重启后会话/原任务保留。18 项浏览器验收通过，包含原工作台 16 项和 Go 身份入口、管理页创建/停用，页面错误为零。[有限收据](verification/go-control-plane-2026-10-26.json)、[管理页截图](assets/deermate-admin-go-2026-10-26.png)。复用原真实 Codex 任务，本轮未触发模型调用。

Go 模块校验/vet、7 项竞态测试（8.666 秒）、Python 94 passed/6 skipped（51.10 秒）、实际 Chart/本地/overlay 22 passed（1.50 秒）、Ruff 和 wheel 通过。标准 Go Dockerfile 已构建，运行镜像与收据一致。[源码 `4af38d6`](https://github.com/mzydmer/deermate/commit/4af38d69061c4c60e1e2f19efa1abe1788c42d88) 已推送；[CI 40313922279](https://github.com/mzydmer/deermate/actions/runs/40313922279) 七个 job 已核对全部 success（含标准五镜像构建），不代表实际云端安装。

普通用户当前只可读取自己的线程/任务；项目级执行授权、OAuth/PAT、邮件找回/MFA 尚未完成。共享 SQLite 只支持固定运行时和单实例本地盘；Go 化不等于将 DeerFlow 或 Worker 重写。ACK 配置将 Go 放进原 Gateway Pod，Service 只指向 Go，Python runtime 仅监听 loopback；云端仍待实际部署。

## 历史工作 · M4.1 DeerMate 前端与动效

用户要求安装 transitions-dev、transitions-polish、text-to-lottie 并重构前端。三项 skill 已从作者固定版本安装到本机 Codex 目录，版本/许可见 [前端 NOTICE](../frontend/NOTICE.md)。未把 skill 集合入库。[功能规格](specs/m4-workspace-refresh.md)、[ADR 0006](decisions/0006-frontend-overlay.md)、[构建与验证](../frontend/README.md)。

源码位于 `frontend/overlay`，Python 仅在临时 Git archive 构建上下文应用 hash 校验的补丁；固定上游 checkout、认证逻辑与 lock 保持不变。本地和 ACK 共用 overlay，新增 `build --frontend-only`。页面包含品牌登录页、默认私人工作台、真实任务筛选/证据抽屉、原始记录和会话草稿交接，支持深色/手机/减少动态效果。

任务列表限最近 20 个对话、每个最多 20 条，失败/部分结果不冒充完整数据或成功零计数。MCP 已配置不代表在线；Claude/DeepSeek Harness 标明规划中；模型未配置时只准备草稿，不触发模型任务。停止/继续仍通过原对话面板/CLI，设备探测、完整时间线和专职路由未完成。

本地 MCP 只读配置接口此前因只读目录不能创建 sibling lock 而 500；init 改为向 owner-only home 普通文件复制种子，每次 up 重新应用。GET 已实际返回 200，专用凭据/staging 仍只读，未扩展宿主权限。

最终 [UI 收据](verification/frontend-workspace-2026-10-26.json)保存 16 项真实浏览器检查：实际 owner 登录、默认入口、配置读取、真实任务与独立验证证据、状态键盘操作、草稿交接、关闭焦点恢复、深色/手机/减少动态效果和隔离故障注入，page errors 为零；使用既有任务，未提交模型工作。已查看 [工作台](assets/deermate-workspace-2026-10-26.png)、[证据抽屉](assets/deermate-evidence-2026-10-26.png)、[深色](assets/deermate-dark-2026-10-26.png)、[手机](assets/deermate-mobile-2026-10-26.png)截图。原创透明 Lottie 在官方 Skia player 检查 0/45/89 帧及播放推进，产品自托管 renderer 也通过。

最终本地生产源码/TypeScript 编译通过。因 npm 下载变慢，核对已构建镜像的 package/lock 与 pin 完全一致后复用依赖，重新编译全部当前源码；来源/镜像 ID 均在收据中。常规回归 94 passed、6 skipped（73.59 秒）；实际 Chart/本地/overlay 22 passed（2.00 秒）；Ruff 通过。

[`fa452e3`](https://github.com/mzydmer/deermate/commit/fa452e32a02859bd61ed9dad3e0a784c0a6950dc) 已推送；[CI 40303558560](https://github.com/mzydmer/deermate/actions/runs/40303558560) 六个 job success，包含当前 overlay 的标准四镜像构建与非 root 前端探针。[镜像收据](verification/workspace-package-2026-10-26.json)来自 artifact `12641727909`，ZIP digest 已核对；不代表 ACK 集群安装。当前三个应用容器健康，入口 `http://localhost:2026`。

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
