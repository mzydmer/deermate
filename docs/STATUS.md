# 当前开发状态与 Agent 接续

最后核对：2026-10-27。历史见 [EVOLUTION.md](EVOLUTION.md)。这是开发 Agent/维护者更新的版本化快照，不是自动监控服务。

## 当前交付

| 项目 | 当前事实 |
| --- | --- |
| 阶段 | M1–M2.5 执行链路、M4.1 前端已有证据；M4.2 Go 已验证；M4.3 统一设计规范和页面风格已实现，本地验收已通过 |
| 分支 | `main`；完整开发栈已 fast-forward 合并，集成点 `51d58b2` |
| 语言边界 | Go 控制端；内部 DeerFlow 和现有 Python Worker/MCP/SSH 保留。取代原控制端 Python-only 要求，见 ADR 0007 |
| 用户/管理 | Go 兼容原 UUID/密码/偏好；会话、角色、停用、重置密码、最后管理员保护、CSRF、审计及 `/admin` 页面 |
| 本地运行 | Go/control、Gateway、前端、nginx 四个健康应用容器；入口 `http://localhost:2026`；独立 host Worker/SSH 保留 |
| 当前验收 | Go 迁移历史 27 项 API 检查；本轮 25 项浏览器检查（含主题/手机/管理弹窗），原任务仍可读，模型任务 0 |
| ACK 包 | 五镜像构建/Go sidecar/私有 Service/loopback runtime 已接入；已检查登录后的阿里云控制台并准备创建草案，尚未创建集群/推送 ACR/实际安装 |
| 低成本单机包 | 四镜像 Compose 包已实现；1472 MiB 容器限额下 14 项接口、5 项重启保留检查通过；实际 2 核/2 GiB 云主机已部署；18 项初始接口与 10 项整机重启后检查通过，浏览器登录/工作台/管理页已核验 |
| 公网 IP HTTPS | 新加坡 2 核/2 GiB/40 GiB；首月实付 ¥0、购买时实例自动续费关闭；账号/配置已迁移，Caddy IP 证书签发、41 项 HTTPS/安全/重启检查与浏览器验收通过；证书自动续期已配置，尚未观察实际续期 |
| 交付 | M1–M4.3 全部已有实现进入 main；来源 CI 40318918329 七个 job 全部 success；主线 CI 结果单独核对 |
| 发布 | 已合并 main 的源码 alpha；未发布正式 release |
| 下一步 | 新加坡公网 IP HTTPS 已部署并通过 41 项接口与浏览器/整机重启检查，北京私有实例保留回退；模型与家庭 Worker 后续单独接入；项目级授权与专职 Agent 路由仍待开发 |

运行代码、历史证据与本轮 Go 变更应分别核对；文档 HEAD 可以继续推进。

## 最低成本单机部署 · 2026-10-26

用户要求最便宜、最小配置，原 ACK 创建没有提交。本轮增加可选[单机部署](single-host.md)、[专项规格](specs/single-host-minimal.md)与 [ADR 0008](decisions/0008-single-host-budget.md)：保留 Go 主/管理/登录/API 及 Python 运行时、前端、nginx，复用系统盘和预构建镜像；不依赖 ACK、负载均衡、NAT、ACR 或托管数据库。默认 localhost:2027 经 SSH 转发，与原本地 2026 入口分开。

`scripts/single_host.py` 从固定上游生成可搬运配置与新的内部密钥，拒绝覆盖既有 bundle，空模型/MCP 起步；不复制原账号数据库、模型密钥、Worker/native 凭据或开发 submit shim。四个常驻容器的内存上限分别为 1024/128/256/64 MiB，总计 1472 MiB、CPU 上限合计 2 核；init 完成后才启动应用。仅 nginx 发布 loopback 端口；普通服务非 root、drop ALL、无 Docker socket，使用命名卷和轮转日志。

复用当前已构建应用镜像，在独立 `deermate-budget-check` 项目与新卷验证：四服务健康；14 项真实 HTTP 检查通过（owner/login、工作台、Go 管理页、内部 API、匿名/外域拒绝、空 Worker、40 次并发上限 4 的只读请求）；重启后原登录会话、owner、页面和运行时保留，另 5 项通过。原本地项目和原 Worker 不参与这些操作。检查脚本修正过 HTTP 201/MCP 响应字段/只读 endpoint 的预期，没有为此修改应用认证行为。

常规回归 **96 passed / 7 skipped（50.84 秒）**；固定 Chart/本地/overlay/单机包专项 **25 passed（1.37 秒）**；Ruff、wheel 通过。CI 已纳入新脚本 lint 和实际 bundle 渲染契约检查，远端结果另查。见[有限收据](verification/single-host-2026-10-26.json)。受限容器仍在现有约 8 GiB Docker VM 上运行，**不等于真实 2 GiB 主机或模型负载验收**；模型调用为 0。

阿里云已登录购买页显示：北京通用型 2 vCPU/2 GiB、40 GiB、Ubuntu 24.04、200 Mbps 峰值、无固定流量，1 年首购活动价 ¥68，选现有优惠券后预览 ¥0，自动续费未选中。截图与私人价格计划保留在 Git 忽略目录；不公开账号/优惠券标识。首年活动和券后预览不保证同价续费，提交前须重新核对条款/优惠券与最终金额。上述为准备阶段报价记录；本次已按用户确认购买并完成免密运维登录，实际结果见下。云端模型和家庭 Worker 尚未接入。

### 云端应用已启动并通过有限验收 · 2026-10-27

已按用户确认创建北京轻量 Ubuntu 24.04 / 2 vCPU / 2 GiB / 40 GiB，订单实付 ¥0、购买时自动续费关闭。未创建 ACK、NAT、负载均衡或 ACR。最初云资源准备见[历史收据](verification/single-host-cloud-2026-10-26.json)；首年优惠不保证续费同价。

用户明确批准临时 SSH 后，经已登录 Workbench 注册专用公钥，并从该控制台核对、固定服务器公钥。密钥配置 24 小时登录期限；`restrict`/`permitopen` 与 admin 的服务端本地转发限制配合，实际拒绝 `-R` 和其他目的端口。初版公钥的 `permitlisten=none` 写法不适用，已修正，并完成 sshd 语法与生效配置检查；没有放宽已确认的访问范围。私钥、账号、云标识和访问脚本只在本机忽略目录。

两份上传归档 SHA-256 均通过；四个预构建镜像均与本地已验收 image ID 一致。Docker 29.1.3 / Compose 2.40.3 下四服务健康运行；仅 nginx 绑定 `127.0.0.1:2027`，原本地 2026 四服务持续健康。云端创建全新 owner，不复制旧账号、模型/Worker 密钥或运行数据。

实际完成 **18 项初始 HTTP 检查、40 次并发上限 4 的只读请求**：owner/login、Go API、工作台、管理页、模型/MCP 配置、匿名/Host/Origin/CSRF 拒绝。随后执行一次受控整机重启，boot identity 改变，四服务自动恢复；**10 项重启后检查**通过，原 owner 身份及原 HTTP 登录会话保留。独立内置浏览器实际登录、显示 Gateway 正常与未配置模型/Worker，并在重启后刷新管理页与工作台成功。使用 canonical localhost；固定上游会重定向 127.0.0.1，不能依靠两种写法隔离两套应用的 Cookie。

套餐内核可见总内存 1613 MiB；本轮请求后/重启后 available 约 695/831 MiB，磁盘剩余约 26.9 GiB。观察点无 OOM、应用容器重启计数为 0；这些是有限页面/API 工作量，**不证明模型负载或更高并发容量**。本轮模型调用 0、家庭 Worker 未注册，没有公网 Web/TLS 或云到家庭执行链路声明。见[目标机验收收据](verification/single-host-cloud-2026-10-27.json)。下一步配置模型与家庭网络需分别验收。

### 公网域名与 HTTPS 准备 · 2026-10-27

用户进一步要求域名和 HTTPS，并选择先查询可注册候选与首年/续费报价。已通过万网公开查询页核对，候选和截图留在私人目录，待用户选定；未下单、修改 DNS 或签发证书。域名控制台要求重新登录，未读取实名认证资料。

当前北京节点对外提供域名网站需先完成 ICP 备案，见[阿里云说明](https://help.aliyun.com/zh/simple-application-server/user-guide/manage-domain-names/)；注册、实名认证和备案不是安装 HTTPS 可替代的步骤。选定域名后，先核对注册结算及备案状态，再安排 DNS/公网入口和 HTTPS 验收。

已准备 Caddy HTTPS → 现有 loopback nginx → Go/前端的草案，以及 Go Origin/Host 变更草案；示例域名配置在本地隔离容器以 Caddy v2.11.7、network=none 通过 validate。仅为语法/模块准备，不证明证书签发、续期、真实域名或 HTTPS Cookie/流式请求；云端仍仅应用 loopback 2027，没有启动公网 Web 监听。使用 [Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)与 [Let's Encrypt](https://letsencrypt.org/getting-started/)的方案待域名确认后实施。

### 公网 IP HTTPS 已部署 · 2026-10-27

用户选择过域名候选，随后明确暂不买域名、优先实现公网访问。域名注册草案已停止，未创建域名订单。现有北京实例仍是已验收的 SSH/loopback 部署；阿里云[通用网站备案说明](https://help.aliyun.com/zh/icp-filing/basic-icp-service/product-overview/icp-filing-requirements-for-a-regular-website)也将中国内地服务器的 IP 网站访问纳入备案要求，没有将 IP 或其他端口当作替代方案。

用户明确确认新实例、条款、24 小时临时 SSH、账号/配置迁移与 80/443 公开入口后，已创建新加坡国际型 2 vCPU/2 GiB/40 GiB、Ubuntu 24.04 实例：非中国优化 BGP、200 Mbps 峰值、无固定流量、1 IPv4；1 个月标价 ¥39、优惠券抵扣 ¥39，收银台支付成功、实付 ¥0，购买时自动续费关闭。首月优惠不代表后续免费或续费同价。北京四服务仍健康，Web 仍仅绑定 loopback；原 Mac 2026 四服务也保持健康。

通过已登录 Workbench 核对固定新主机公钥，登记独立 24 小时 admin 临时公钥；实际验证允许 loopback 2027、拒绝其他转发目标和远程转发。私钥始终留在本机。直传较慢后，用既有北京运维连接中转 SSH 字节流，仍使用本机密钥及新主机公钥校验，没有复制私钥或放宽转发授权。

上传归档哈希通过，四应用镜像 ID 与原验收镜像一致；新增 digest 固定的官方 Caddy 2.11.7。原云数据库通过 SQLite online backup、quick_check 与目标空账号检查后恢复，原 owner UUID/密码继续有效；5 份源应用配置与迁移包哈希一致，没有复制 Mac/native/Worker 凭据。新节点先私有启动，再恢复账号，最后启动公开 edge。

新增 `scripts/single_host_https.py`，保留私有默认和原 Compose 备份，精确设置 Go HTTPS Origin/Host；edge 使用只读根文件系统、仅 `NET_BIND_SERVICE`、128 MiB 限额、独立持久证书卷与 loopback 管理 API。实际签发 Let's Encrypt `shortlived` IP 证书（约 160 小时），正常信任链和 IP SAN 验证通过。外部验收修正了不发送 SNI 的 IP 客户端证书选择，以及错误 Host 的空响应；最终 `default_sni` 精确绑定公网 IP，未知 Host 明确返回 421。没有绕过 TLS 校验。

**24 项初始 + 17 项整机重启后 HTTPS 检查通过**，含 40 次、并发上限 4 的只读请求：旧账号登录、UUID、工作台/Go 管理页/API、匿名拒绝、Secure/HttpOnly/SameSite Cookie、外部及明文 Origin、Host/CSRF 限制。浏览器真实登录并加载 owner 管理行，整机重启后刷新工作台与管理页仍有效。boot identity 确认改变，原登录会话及同一张证书保留，四应用容器健康、edge 运行，观察点无 OOM 或应用容器重启计数增加。由另一云节点外部探测确认 80/443 可达，2027/8001/8080/3000/18777/2019 关闭或被过滤；本机代理会影响裸 TCP 探测，未将该结果作为隔离证据。

内核可见 1613 MiB，有限请求后 available 约 717 MiB，重启后约 829 MiB，磁盘剩余约 26.7 GiB。证书持久存储和自动续期已配置，**尚未观察真实续期**；模型调用 0、模型/MCP 为空、家庭 Worker 未接入，没有模型容量、云到家庭任务或 HA 声明。公网地址、账号密码、云标识和截图留在私人目录；公开[验收收据](verification/single-host-public-ip-2026-10-27.json)不含这些值。设计见[专项规格](specs/single-host-public-ip.md)、[ADR 0009](decisions/0009-public-ip-https.md)与[部署指南](single-host.md)。

最终代码回归 **103 passed / 7 skipped**；实际固定 Chart/本地 Compose/overlay/单机/HTTPS 契约 **32 passed**，Ruff、wheel 与隔离 Caddy validate 通过。来源与本轮 CI 分开记录；未发布正式 release。下一步单独配置聊天模型、家庭 Worker，再做受限真实任务验收。

## ACK 创建准备 · 2026-10-26

用户确认尚无 ACK 集群，最初要求先准备创建方案，随后否决以下费用。已通过其已登录的控制台检查杭州、北京列表（均为 0 条）及北京 ACR（个人版尚未创建）。原草案 `deermate-dev` 使用北京 ACK 基础版、普通 amd64 ECS 单节点 `ecs.e-c1m2.xlarge`（4 vCPU/8 GiB）、80 GiB 系统盘、120 GiB 容器运行时盘；应用另申请现有部署包要求的 20 GiB RWO PVC。未提交此方案；保留历史价格依据，单节点与 SQLite 均不提供 HA。

控制台显示 ECS/系统盘/运行时盘分别约 ¥0.45/0.08/0.13 每小时，另有 NAT ¥0.184/小时、出口 EIP ¥0.020/小时及 API Server 私网 CLB ¥0.147/小时；这些已列固定项合计约 ¥1.011/小时、720 小时约 ¥727.92。**尚未计入应用 PVC、NAT CU、CLB LCU、公网流量、模型调用及可选监控等，不能视为总价或费用上限。** Pro 控制面报价另加 ¥0.640/小时。价格仅记录本次控制台观察，实际创建前重新核对。

私有 `.deermate/ack/` 保留创建计划、故意使用不可访问占位 registry/context 的应用配置草案、脱敏 Helm review 清单及报价截图。使用实际固定 Chart 离线渲染通过：11 个资源、3 个应用 Deployment；Gateway 同 Pod 的 Go/Python 边界、无自动 ServiceAccount token、ClusterIP 与单实例 PVC 保持。没有访问 Kubernetes API、复制模型密钥或调用模型。

创建向导还需要 `AliyunOOSLifecycleHook4CSRole` 授权；未接受任何 RAM 授权、协议或创建订单。ACR 仍需开通并由用户完成访问凭证设置。草案 API Server 为私网，本机无法直接连接；实际部署前必须选择同 VPC Workbench 或明确批准的受限公网 API 方案。家中 Worker 保持禁用，尚无云端可达链路。见[准备记录](verification/ack-console-plan-2026-10-26.json)与[部署指南](ack-deployment.md)。

## 主线集成 · 2026-10-26

用户明确要求将目前开发内容合并 main。已将主线从 `e9f228d` fast-forward 到 [`51d58b2`](https://github.com/mzydmer/deermate/commit/51d58b270e45069ad7ae6596949517528373f220)，包含所有十个功能分支的已有提交，保留开发分支及全部历史。GitHub PR 连接器写操作返回 403；采用已有 SSH Git 权限普通推送完成，没有强制推送或绕过仓库规则。

功能代码与来源 CI 全部通过的 `c349431` 一致，之后仅改文档。来源 [CI 40318918329](https://github.com/mzydmer/deermate/actions/runs/40318918329) 七个 job 已核对全部 success。主线安装说明改用 `main`；前端规范依然由根目录 design.md/AGENTS.md 管理。合并不触发原生任务、不更改本地凭据/数据库；本地服务保持运行。集成记录见 [收据](verification/main-integration-2026-10-26.json)。本次主线推送的 CI 结果独立于来源证据，不提前标记通过。

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

[设计源码 `c349431`](https://github.com/mzydmer/deermate/commit/c3494319a493bec801947d2ff4eda221308c62dd) 已推送；[本轮 CI 40318918329](https://github.com/mzydmer/deermate/actions/runs/40318918329) 七个 job 已核对全部 success；已按用户要求于本轮合并 main，集成点 `51d58b2`。当前本地四个应用容器健康。

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

1. 暂缓域名购买。待用户确认新加坡零元首月草案后，重新核对金额/续费状态并创建单个实例，固定新主机身份后迁移，使用公网 IP HTTPS 验收；保留北京回退。
2. 本地保持可运行；云端单机基础验收已通过；保持现有私密入口，下一步按[单机指南](single-host.md)单独配置聊天模型并验证有限模型负载。ACK 作为可选方案保留。
3. 对明确注册的真实设备验收受限 OS/OpenSSH 策略、网络可达性与服务重启；不扫描或登录未注册主机。
4. 配置模型后单独验证通知和聊天入口；保留任务身份、取消确认和外部输入权限边界。
5. NAT/反向连接独立设计，再扩展专职 Agent 路由与工作台。

按 [AGENTS.md](../AGENTS.md) 接续；行为变化更新 spec，有意义结果追加 EVOLUTION，当前状态维护于此。
