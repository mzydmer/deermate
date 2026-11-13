# 当前开发状态与 Agent 接续

最后核对：2026-11-12。标准 OpenTelemetry 核心与独立 ARMS 配置已合入 main，应用 `ce7ce59` 的 11 个远端 CI job 全部通过，既有新加坡实例已升级并启用遥测。20 项可信公网 HTTPS/API 检查、原账号和历史数据核对、两轮同秘书会话的真实模型调用通过；两轮 Trace 均已在 ARMS 查询到。四服务执行树使用此前合成协议数据单独验证，未恢复过期家庭设备权限。正文与上线证据见下文。

## 2026-11-12 · 流式 HTTP 计时修复（发布中）

页面实测发现一次 42.44 秒请求的出站 http.client 只记了 41.28 毫秒，原因是 Transport.RoundTrip 在响应头返回时结束 Span。新增真实 SSE 回归先验证旧实现失败，修复后由响应体 EOF、读取失败、关闭或上下文取消中的首个终止事件结束一次；不预读/缓存正文，保留 n/error、HTTP 错误状态和升级响应的 io.Writer，关闭追踪时原样返回 body。

Go mod verify、vet、全包 race 和本机/Linux 无 CGO 构建通过；源码、部署与 ARMS 复验分开记录，尚未切换本次控制面版本。只需升级 Go 控制面，不重建前端或修改 Python/MCP/设备权限。MCP 预检缺少服务端 Span 和真实家庭执行授权仍是独立未验收事项，本次不据计时修复宣称它们已通过。

文档影响说明见 [变更记录](change-notes/http-stream-span-lifetime-2026-11-12.md)，生命周期合同见 OBS-10，运维判读见 [调用链指南](observability.md)。

## 2026-11-12 · 可选调用链与 ARMS 已上线

按用户要求将开源核心与厂商接入分开。Go/Python 使用标准 OTel API/SDK 与 OTLP/HTTP，默认关闭，核心没有阿里云 SDK 或接入地址；ARMS 样例、预检与接收/索引操作说明位于独立部署目录。规格、实现、验收和下一步分别见[实施规格](specs/vendor-neutral-observability.md)、[ADR 0017](decisions/0017-vendor-neutral-observability.md)、[运行手册](observability.md)与[脱敏收据](verification/observability-2026-11-12.json)。

已实现 Go HTTP/持久派单、Gateway/模型/工具/记忆、MCP/受控 Relay、Worker 执行、原生协议轮次/已观测工具事件和独立验证的跨度。首次 operation/task 关联独立持久化，避免上下文进入提示词或改变幂等指纹；公网关联隔离、本人映射及重复投递约束保留。后台以原操作重读关联，Worker 恢复通过 Span link 另开执行段，Exporter 失败不增加任务重试。默认不采集正文、命令、补丁、认证或异常原文。

本地实际接收的 protobuf 验证了两轮 Go → Gateway → MCP → Relay → Worker → 原生协议/独立验证：四个服务的父子链连续、同一原生根、两组 operation/task/turn 与 Trace、两次验证通过；885 个接收跨度的私有标记匹配为零。Fake 模型与原生协议进程只操作 toy 仓库，不构成真实供应方或 Codex 验收。固定运行时中的实际 LangChain 图另验模型/工具包裹和合成 usage 字段。也修正了系统代理影响本机导出、Python SDK `03` trace flags 被 Go propagator 拒绝，以及非法 MCP 元数据影响工具调用的问题。

验证：常规 Python **324 通过 / 7 跳过**，跳过的四个 DeerFlow 模块和一个 LangChain 模块已在固定 Gateway 环境以 **76 项通过**覆盖；两个独立 full Gateway local/SSH 验证器未重跑，不能把 Docker 子集称为完整 SSH 复验。Go mod/vet/全包 race/无 CGO 与 Linux 构建、关闭重开数据库关联、实际固定 Helm/Compose 契约、Ruff/wheel 和产品文档/图示/设计门禁通过。新增无云凭据的跨语言 CI job；后续 ce7ce59 的 11 个远端 job 全部通过，包含完整 Gateway local/SSH、固定镜像和跨语言协议检查。

**当前发布进度：**应用 ce7ce59 已升级现有单机，Go/Gateway/前端安装内容哈希匹配；一致备份、原表旧列值和模型/journal/授权文件核对通过，原 1 个账号、9 个话题、19 个 run、5 条任务及原密码保留。活动 MCP 从旧离线 uvx wheel 显式迁移到当前 Gateway Python，保留同一 relay 配置、其他 profile 字段和设备授权。20 项可信公网检查及两轮真实 Router 回复通过；测试新增秘书记录单独计入，不冒充旧数据。云端服务健康，没有增加服务器或恢复家庭权限。

现有北京工作空间实际接收了新加坡服务器 probe，两轮真实 Router 的 operation、记忆和模型跨度均已按 Trace ID 查询；标准 SERVER/CLIENT/PRODUCER 类型在实际调用树可见。另将此前本地已验证的两轮合成协议 protobuf 作为诊断数据发送，保留原始时间与 ID；ARMS 首轮展示四服务、47 个 Span 和独立验证。这不重放业务、不调用模型或真实 Codex。原始凭据、工作空间身份、protobuf 和浏览器截图保持私有；[云端收据](verification/observability-cloud-2026-11-12.json)记录脱敏证据。

发布后的产品文档已同步 `73040b4`，2,823 个部署文件哈希、隔离 Linux 渲染、23 项可信公网检查（十四篇文章、二十个资源）及最终六项桌面/手机页面检查通过。Go/Gateway 和设备授权未再重启或改变。该发布源的 11 个远端 CI job 全部通过；Mac 首次在既有 RPC 子进程退出测试出现 PermissionError，源码未变，本机 100 次未复现，单项重跑通过。此处保留首次失败，不把重跑解释为已修复该问题。

旧版试用到期提示与 2.0 工作空间分开核对，没有提交付费购买订单。原生内部模型/Pilot 子链合树、厂商 AI 专属视图、AgentLoop 评估和独立 Metrics/Logs 管线未验收。下一步是在有效设备授权下完成新的真实云端 → 家庭 Worker/Codex 链路；本轮请求的 ARMS 接入、main 合入和既有实例升级已完成。


## 2026-11-10 · README 技术品牌方案（main 设计交付）

用户反馈操作录屏和朴素头图无法体现项目特点，要求先出架构与技术理念方案，再由专门 UI 设计子 Agent 美化。已完成[方案](prd/readme-tech-v3.md)、[README 骨架](prd/readme-tech-v3-outline.md)、[高保真预览](prd/readme-tech-v3-review.html)、原创矢量主视觉/架构/分镜，以及 36 秒架构概念片与 6 秒 GIF。深色控制空间、蓝青执行信号和紫色来源记忆强调 Go 接纳、持续 Router/Worker、原生会话连续性及独立证据；规划适配器明确分区。

设计提交 `6414ecb` 先推送到 `design/readme-tech-20261110`，随后按用户要求连同交付记录合入 main；这不是线上应用发布。预览默认暂停，含键盘、时间轴、减少动态与手机排版；[设计记录](prd/readme-tech-v3-validation.json)保留合入前的本地浏览器和媒体验收快照。这轮没有模型、Native 或生产操作。下一步按这套视觉语言接入正式中英文 README；此前真实操作素材保留为补充资料。

## 2026-11-10 · README 与操作演示

以 main 860390c 为基线精简中英文 README，保留当前定位、启动路径、能力边界和研究问题；旧中间里程碑和测试流水移交既有状态与演进文档。首屏改用真实工作台截图，视频展示实际记忆更正和临时话题。素材使用独立无模型、无设备的本地实例及合成账号，模型投递和浏览器脚本错误为零；不代表新增的模型、Native 或云端验收。旧概念素材保留原链接，复现与范围见[媒体说明](media.md)和[收据](verification/readme-media-2026-11-10.json)。线上应用与文档版本保持以下 595f654 / bfa91aa。

## 设计基线 · 统一设计系统与前端门禁（2026-11-05）

`design.md` 已重构为 YAML tokens/组件配方与独立设计说明；YAML 是唯一来源，生成 React/Go 共享 tokens 和组件 CSS。工作台、登录、对话/设置公共组件、记忆、持续秘书、文档、工具与 Go 管理/授权界面迁移到共享视觉基准：成功蓝色、普通控件8px圆角/默认40px、普通卡片无阴影、浮层分级。固定上游状态色通过哈希约束补丁桥接，源码 diff 保留内容增删语义。

新增 `design-system` CI、前端 overlay 构建前门禁与反例测试；AGENTS、PR模板和前端说明要求每次 UI 变更遵循规范。门禁检查生成漂移、引用、独立颜色、字号/圆角/阴影、空间值与内联样式；不能代替设计评审、键盘和完整浏览器验收。该设计规范轮次按当时要求仅交付 main；后续工作台 v2 已包含此规范并部署，见下文。远端分支保护尚未配置。19项设计/overlay回归、8项意图恢复、Ruff、TypeScript/最终Next生产构建、Go mod/vet/race/无CGO构建与文档门禁通过。原Chrome基线为30项公共组件/Go外壳和20项React文档路由检查。2026-11-06补齐真实Go登录、生产React与合成运行时的169项页面矩阵和16项交互状态检查，六宽度/浅深色、页面错误0、模型执行请求0；已修正平板设置分栏、当前导航可见性、侧栏token与手机浮层关闭命中区。记忆与资料写入使用独立本地SQLite；运行时为合成数据，不能替代真实Gateway/模型/Native验证。见[登录后验收](verification/design-authenticated-2026-11-06.json)。验证结果与范围见[专项记录](verification/design-system-2026-11-05.json)。

## 2026-11-09 · 私人助手工作台 v2（已上线）

用户已批准按最新 main 的 design.md 对齐设计，连续实现、本地验收后推送并部署。独立工作区 deermate-workspace-v2-20261109，基线 780173a，原 main 工作区保持不动。S0/S1 已提交 35f9005；后续实现和发布以[计划](specs/workspace-assistant-v2-plan.md)区分。

已接入普通表达快路径、本人私有项目/话题范围、阶段有效期、同槽位更正、来源及用途、自然最近指代遗忘、持久模型整理和调用/删除屏障。一般整理每天最多四次，快路径分开调度；供应方回执未知不重发。规范来源覆盖普通 interactive run 与 Go 接纳的完整本人 Inbox；最终 Router 重新加入个人参考，背景 Assessor 不继承。最近七天/最多十话题/每话题五消息的整理可停止与撤销，历史不覆盖当前偏好。

新版助手首页、我的工作、关于你和来源抽屉已实现。首页确定性读取最多三项，已读、当地次日暂缓和不再提醒持久保存；单一输入与本人目标建议沿用原 Router/intent。临时话题在创建前写入禁止读写策略，未确认发送在当前浏览器会话保留原操作编号。

当前本地检查：Go mod/vet/race 与 Linux/macOS 无 CGO 构建；Python 292 passed / 12 skipped，固定 DeerFlow 专项 59 passed；真实固定 Helm/Compose/文档等契约 59 passed；Ruff/wheel、TypeScript/Next 与设计/token/产品文档/图示门禁。离线 Go→Gateway 43 项和基础专项 45 项通过。独立 Docker localhost:2036 健康，原 localhost:2026 实例未修改。

真实供应方完成 16 项记忆闭环；独立 Worker→Codex 完成同根两轮与每轮独立验证。浏览器 Chrome 33 项、四屏宽/浅深色/键盘/2×等效重排通过，页面脚本错误和模型投递均为零。旧镜像实例升级保留原密码、资料、暂停、规范事实与关注，新增默认没有覆盖旧选择。见[模型](verification/workspace-v2-model-2026-11-09.json)、[Native](verification/workspace-v2-native-2026-11-09.json)、[UI](verification/workspace-v2-ui-2026-11-09.json)及[升级](verification/workspace-v2-upgrade-2026-11-09.json)。

应用源码 595f654 已推送 main；[远端 CI](verification/workspace-v2-ci-2026-11-09.json)十个 job 全部通过，首次设计 job 的依赖缺失已修正。既有新加坡单机完成一致备份、三个应用镜像升级、安装内容哈希和旧列值核对。22 项可信 HTTPS/API、13 项实际公网浏览器检查通过，原 1 个账号、9 个对话、19 次 run、5 条任务与模型、原生记录及授权保留。安装 owner 明确采用 V2 默认，其他旧选择不自动迁移；[上线收据](verification/workspace-v2-cloud-2026-11-09.json)。

发布后的文档前端已同步 bfa91aa：2,822 个部署文件哈希、隔离 Linux 渲染、23 项可信公网检查（十四篇正文和二十个资源）以及最终 13 项浏览器检查通过。Go/Gateway 与授权未变；该文档提交的十个远端 CI job 也全部通过。最终版本与镜像见上线收据。

下一步是观察有界历史整理、补充更复杂语义与来源反例，并按研究计划开展对照评估；这些不是本次发布未完成的步骤。未恢复家庭 Agent 到期授权，独立 Native 验收不等同于完整浏览器→家庭设备的新验收。

## 历史基线 · 默认秘书与记忆设置

按用户新要求，秘书交互和手动工作默认可用，复用对话模型并在首次投递前冻结；无模型时等待，未知结果只核对原操作。旧背景停用不阻挡明确交互，也不会被交互自动恢复。来源、自动预算、设备授权仍独立检查。设置 → 记忆复用本人管理组件，首页提供快捷链接，记忆与采集选择保持。

专项规格：[默认入口与记忆设置](specs/default-secretary-memory-settings.md)。本地验收已通过：Go mod/vet/race/无 CGO 构建；Python 274 passed / 11 skipped；固定 Gateway 中专项 16 passed / 2 项非本轮 Native 驱动 skipped；实际固定 Helm/单机/HTTPS/overlay/文档 41 项；8 项意图恢复；TypeScript/完整 Next 构建与 token/文档门禁。Chrome 实际验证 390/1280px、浅深色、键盘、默认入口对话和记忆保存/搜索/纠正/关闭后管理/遗忘。9 项 Go→Gateway Fake 验收包含默认模型、两轮同根及接纳后重启核对；没有真实模型或 Native 调用。见[专项收据](verification/default-secretary-memory-2026-11-04.json)。此变更已推送并部署既有新加坡单机；28 项可信公网 HTTPS/账号/数据/API、46 项文档/页面/资源和 17 项授权回归通过，五服务健康。原 1 个账号、9 个线程、19 个 run、5 条任务及模型/个人资料/记忆/关注保留；交互默认可用，旧背景保持暂停、auto=0、来源未配置、无新增设备权限。备份与回退镜像保留，长期本机部署密钥按用户要求保留。见[上线收据](verification/default-secretary-memory-cloud-2026-11-04.json)。线上视觉、真实模型/Native/GitHub 与研究比较未在本轮执行。以下 `274c1b2` 默认关闭和产品文档单独发布记录为历史事实。

## 产品文档中心 · 已推送并上线

新增登录页、工作台顶栏/侧栏「产品文档」入口与独立 `/docs`。14 篇 Markdown 分为九篇客户指南、四篇面向技术/研究的方案与一篇变更日志；不增加接口参考或部署指南。正文、目录、搜索、复制及上下篇使用同一生成内容源。见[专项规格](specs/product-documentation.md)、[文档入口](product/guide/overview.md)。

[文档更新约束](DOCUMENTATION_POLICY.md)已接入 AGENTS 与 PR 模板，CI 新增 `product-docs`：检查来源/链接/生成同步，并要求代码变更附产品文档和变更日志，或有具体理由的无需更新记录。文档功能已提交、合并远端上线记录并推送；已完成既有实例的文档前端与窄代理路由发布，远端分支保护尚未配置，未宣称远端 CI 已通过。

本地文档/overlay **17 项通过**，Ruff/token/TypeScript 与完整 Next 生产构建通过；14 篇文章的静态 HTML、文档链接和 86 个页内锚点通过检查。Chrome 实际确认了桌面首页、文章与导航；切换手机视口后浏览器连接连续超时，手机、深色、搜索/复制交互及最终样式的实际浏览器复验未完成。最终核对见[文档收据](verification/product-documentation-2026-11-04.json)。

文档功能提交 `36e2684`，合并提交 `1783dd6`，首次上线前端源码 `fb5dd73`，最终文档前端为 `8aad210`；最终内容版本见[上线收据](verification/product-documentation-cloud-2026-11-04.json)。最终 45 项可信公网 HTTPS/文档/资源/原账号检查通过（包含正式发布日志与技术说明），9 个线程/19 个 run/5 个任务保留；41 项文档与实际固定 Helm/单机/HTTPS/overlay 回归通过。Go/Gateway/edge/nginx 镜像未变，只更新前端及 `/docs` 代理配置，数据库一致性备份、原镜像和配置保留。首次默认配置重载失败已核对回退，再使用实际 nginx 配置重载成功；原 `/docs` 后台路由也已修正，生成器纳入回归。浏览器矩阵待恢复连接后补验。本段不改变以下持续秘书的历史验收和接续事项。

## 历史基线 · M4.5 持续秘书 Alpha

用户已批准按 spec/plan 连续开发。以 `5a1ed3a` 为代码基线，`18f437e` 接受设计，`e172857` 加入第一轮实现；`b952ee9` 补齐恢复、来源、授权与负载修正，并加入可复现离线验收脚本。初始 Alpha 的模块默认关闭已由本页默认交互更新取代；原账号、聊天、记忆和原生绑定不自动迁移。

已实现：

- Go 唯一保存版本化工作/事件/规则/决策/Inbox、预算和投递屏障；owner/CSRF/revision/幂等检查，来源与项目范围在接纳时重查。
- 固定 DeerFlow 中每 owner 一个持久 Router；Router 只有类型化路由工具，Assessor 无工具，执行复用原 journal/ordinary driver/授权 relay。独立 lane 避免 Native 等待占住秘书入口。
- 工作创建、明确执行与追问、暂停/关闭、停止请求及原操作核对；未知不重发，接纳前明确拒绝也有持久回执。原对话 head 改变时先拒绝并更新指针，由本人重新确认下一步。
- 单仓库 GitHub 只读基线/增量/ETag/分页/退避、observe/本人接纳与有界 auto；已绑定 Thread 进入原工作上下文，范围报告可 handoff。auto 默认额度 0。
- 本人 FTS5 与 3 跳/20 对象/32 KiB 引用；来源不可读/停用/换代移除旧搜索内容，迟到结果不能重新索引失效来源。高频词按最近索引匹配返回，避免全历史评分。
- 首页秘书、工作详情、候选和来源/规则设置，沿用共享 design tokens。执行按钮依赖实际设备授权和协议，接纳前不会出现可打开的虚构执行对话。
- 追问草稿按工作隔离，已有 Native 轮次要求明确下一步；未知回执的页面内重试冻结原请求/操作 ID。局部读取失败有明确提示，关键状态过时停用写入，原操作核对仍可用。
- Worker/连接器协商 `work-orders-v1`，逐版本本机确认持续任务范围，冻结授权 ID/版本/设备并在执行前复核；持续任务独占原生轮次，最多 30 分钟。

## 本轮验证与限制

[原脱敏验收记录](verification/continuous-secretary-2026-11-04.json)分别记录组件、实际 API、恢复、负载与早期 UI 范围；[本轮 UI 收据](verification/continuous-ui-2026-11-04.json)单独记录后续前端修正与真实视口验收，不覆盖历史记录。

| 检查 | 当前结果 |
| --- | --- |
| Python | 260 passed / 11 skipped；Ruff/wheel 通过；一条已有 Starlette 弃用提示 |
| 固定 DeerFlow | `a1b89d0432de4e45adc59f512cb25bb386ea1e51`，37 项角色/图/SDK/适配契约通过 |
| Go | Go 1.27.3；mod verify、vet、race、无 CGO 构建通过；排序/来源/验证状态修正后再次通过 |
| 部署契约 | 实际固定 Helm/Compose 29 passed，非占位渲染 |
| 前端 | 最终 TypeScript/完整 Next 生产构建、共享 token、17 个 overlay 文件与运行镜像一致；Node 24 意图恢复 8 项与 overlay 3 项通过，相关部署/前端子集 24 passed / 3 skipped |
| 实际 Go→Gateway | 7 项离线 API 检查：同一 Router 两轮、输入去重、原始插件封锁、无授权不接纳、生命周期；接纳后重启 Go，只核对一个原 run、perform 投递计数为 1 |
| 有界负载 | 1,000 个合成工作 / 10,000 个事件，各 100 次、并发 1；p95 列表 69.666、详情 39.341、引用 42.354、搜索 84.995 ms；四服务健康，无 OOM；合计限额 1472 MiB |
| 浏览器 | 真实 Chrome 390/1280/1440px、浅深色、键盘焦点/跳过禁用动作与减少动态；逐工作草稿、已结束工作无输入、普通账号隔离、规则/回执 503、工作过时停写与恢复通过。8 个阶段卡为显示样本；完整来源/候选状态矩阵仍待补验 |
| 实际 Native 协议闭环 | Go→Gateway→ordinary driver→授权 relay/连接器→Worker→假 Codex：两轮、一个原生根、两次独立验证；Native 在途时 Router 可答新输入。CLI 配置错误的早期尝试保留未知，不重发 |
| 兼容回退 | 停模块→指定旧 Go `m4c`→新镜像，账号/工作/线程/Native journal 和 1 条未知操作保留；未恢复或覆盖 DB，仅证明该旧 Go 镜像兼容 |
| 本次云端交付 | 既有单机已升级 `274c1b2`，Go/Gateway/前端与 MCP 包同版本；27 项 HTTPS/账号/数据/API 与 17 项授权回归通过，五服务健康。[收据](verification/continuous-cloud-2026-11-04.json) |
| 真实来源 / 模型 / Codex | 本次发布未运行；本地 Fake 或只读上线检查不能替代这些验收 |

负载首轮误装 ARM64 Go 程序，已排除；随后 amd64 全量评分搜索 p95 505.319 ms，修正排序后通过，失败记录仍保留。上述不是冷文件系统、真实 2 GiB 主机容量或 Router 对照实验。

完整 CONT-01–23 尚未全部通过：仍须来源/候选等完整 UI 状态、更多跨进程中断/公平性、来源删除语义及实机验收。R-EVAL-01–05 尚未开展，不能宣称性能、模型质量或注意力成本改善。前述 UI 轮次仅修改前端及 fixture；本次发布另做产物分层验证与云端只读回归。Go/Worker 的完整套件数量仍属于历史基线，未在发布轮次重跑。

## 已有交付基线

| 能力 | 已有事实与证据 |
| --- | --- |
| Go 主/管理/登录/API | 保留现有账号 UUID/密码/偏好、会话撤销、CSRF、角色和最后管理员保护；内部 Python 仍为 DeerFlow/Worker/MCP |
| 工具与连接 | 公开搜索/网页读取及工具检查页已有云端证据；私人账户连接需独立服务/授权。[指南](tools-and-connections.md) |
| 一个对话一个 Native | 自动命名/改名、真实 Codex 多轮同根与独立验证已有历史收据。[会话指南](chat-sessions.md) |
| 记忆与首页 | 显式事实、本人 FTS、遗忘屏障、来源撤销、确定性简报/关注与首页动作已实现；本轮 v2 已增加有界语义提取，本地证据见前文。[记忆](personal-memory.md) / [首页](personal-home.md) |
| 用户管理设备授权 | 配对、逐版本本机确认、期限/项目/操作/到期策略、续期取消、撤销与出站 HTTPS 已本地验收；Go/Gateway `5a1ed3a` 已部署，17 项 HTTPS/API 通过，线上视觉未验。[指南](agent-authorizations.md) / [本地](verification/agent-authorization-local-2026-11-03.json) / [云端](verification/agent-authorization-cloud-2026-11-04.json) |
| 云端 | 现运行 `161fd29` 默认秘书与记忆设置；原账号、9 个线程/19 个 run/5 个任务、模型文件、个人资料/记忆/关注及到期授权保留。交互默认可用，背景仍暂停，auto=0，来源未配置。[最新上线](verification/default-secretary-memory-cloud-2026-11-04.json) |
| 家庭接入 | 历史反向 SSH 授权已于 2026-10-30 截止，不能复用；本机 Worker 可达不等于当前产品授权/新协议就绪 |
| 本地 | 个人入口 `localhost:2026` 本轮未升级；原 API/负载用独立 2036，本轮 UI 用独立 `deermate-native-check`/2037、合成账号及隔离网络。验收前后 run=7、Native task=2、模型预留=5，零新增调用；fixture 现已停止并保留卷 |

## 接续任务

1. 补 CONT-16 的有效来源候选/来源失效/背压界面矩阵、CONT-03 删除可观测边界及长时公平性；界面项目/授权 ID 改为可视化选择。尺寸/主题/键盘/减少动态和本轮读故障已补验，勿重复作为待完成项。
2. 配置明确仓库的产品只读 token、受支持实际模型和有效 `work-orders-v1` 项目授权后，按 P7 上限验收一次真实闭环。不得借 Codex 研究连接或过期 SSH 配置产品权限。
3. 后续升级复用本次用户明确批准的长期本机部署密钥，仍须核对活动任务、备份和固定镜像；部署权限与设备执行授权分别管理。本次云端 API/HTML 已验收，线上视觉及真实工作闭环仍待验证。
4. 独立执行 R-EVAL 对照/消融和公开复现数据。真实模型研究请求额度须另行确定，不挪用有限实机验收上限。

本轮用户已要求推送和云端发布，发布工作区合并远端 `77c5c31` 授权上线记录；应用源码仍为已验收 `274c1b2`，未提交的产品文档不纳入此发布。用户明确将本机仓库/服务器部署密钥改为长期有效；代码已推送，云端已升级，27+17 项公网检查通过。新增离线意图恢复 CI job，未声明远端 CI 已运行。合成 Compose 验收实例均已停止，私有卷和故障证据保留，浏览器临时视口已恢复；个人环境不作为 fixture。

## 2026-11-05 · 产品文档图示

本轮新增六张产品文档架构/流程图，源与 SVG 同步检查、图片安全检查已纳入文档门禁；19 项文档/overlay 检查、Ruff、共享 token 与完整 Next 生产构建通过；六张 SVG 已进入生产 HTML，原图渲染已检查，网页完整视觉验收受浏览器工具不可用限制。图示版本 `c893224` 已上线，六个 SVG 哈希及五篇文章共六处嵌图通过 11 项公网检查；45 项账号/页面读取检查另核对即时切换前 DB 备份，个人设置与备份一致。早期个人设置哈希与后续值不同，未覆盖当前设置。后端镜像和历史任务保留。见[上线收据](verification/product-diagrams-cloud-2026-11-05.json)。
