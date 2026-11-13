# 可移植的 Agent 调用链与首个 ARMS 接入

- 状态：Accepted；2026-11-10 用户授权实施，交付状态见 STATUS。
- 基线：main `19bcc4d`。
- 需求：NFR-003、NFR-004、NFR-005、NFR-006、NFR-009。
- 决策：[ADR 0017](../decisions/0017-vendor-neutral-observability.md)。

## 目标与范围

开源代码提供基于标准 OpenTelemetry 的、默认关闭的调用链能力。业务层不导入阿里云 SDK、不需要阿里云账号，也不包含厂商 Endpoint 或 Key。ARMS 是本轮部署后端，配置和运行手册独立于核心实现；通用 OTLP/HTTP 接收器是离线验收目标。

覆盖 Go 公开入口/运行时请求、持久操作派单、Python Gateway/Router/模型/工具/记忆、MCP/受控 Relay、Worker 入队与执行、Codex 原生轮次/可观测工具事件，以及独立验证。每段必须以实际事件为证据；原生模型内部未提供的调用、Token、时间或父链保持未知。

本轮不新增 AgentLoop 评估、审计或自动调优，不采集浏览器会话回放，不恢复过期设备授权，不把遥测后端当作任务事实库。

## 分层与配置

1. Go `internal/observability` 与 Python `deermate.telemetry` 只依赖 OTel，提供有界初始化、Span、上下文白名单与导出。
2. 控制面、运行时和 Worker 在既有边界调用这些接口；权限、业务指纹与任务状态机保持独立。
3. 部署使用标准 `OTEL_SERVICE_NAME`、`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`、`OTEL_EXPORTER_OTLP_HEADERS` 和 `OTEL_RESOURCE_ATTRIBUTES`；明确 `DEERMATE_TELEMETRY_ENABLED=true` 才开启。
4. 支持关闭或 OTLP/HTTP 导出，本地 OTLP 接收器用于调试；生产示例使用 HTTPS，localhost HTTP 仅用于本地接收器。凭据放私有环境文件，不进入提示词或普通日志。
5. `deploy/observability/arms/` 仅放厂商配置样例与说明。移除该目录不影响核心库和通用验收。

## 身份与传播

- 业务身份：本人话题/换代、work、operation、Worker instance/task、native session/turn。一个话题继续保持既有原生绑定，每轮产生独立的遥测执行段。
- 同步 HTTP 使用 W3C trace context；只转发严格校验过的 traceparent/tracestate，不透传 baggage 或任意头。公网请求不决定内部授权、采样或其他账号的关联。
- Go 操作上下文与 Worker 任务上下文写入独立表；不进入模型消息、任务参数 schema、策略快照或幂等指纹。首个有效绑定不可被重复投递重写。
- 后台循环从操作记录恢复上下文；Relay 把白名单遥测元数据随任务落盘并返回设备，设备只转换为允许的本机 Header。
- MCP stdio 使用协议元数据；持久异步派单可从已校验的本人规范操作恢复上下文，不能依赖请求线程的 ContextVar 一直存在。
- 取消、查询、重复交付和未知回执核对产生独立 Span；遥测失败不能重放执行。跨重启不能复活已结束的 Span；恢复段使用持久原上下文关联并明确恢复状态。

## 数据与失败边界

默认只采集固定操作名、枚举状态、系统生成身份、实际用量和时间。Prompt、回复、记忆正文、URL 查询、认证头、命令参数、stdout/stderr、补丁和异常原文不导出。业务标识只用作 Span 属性，不用作高基数指标标签。

Exporter 使用有限队列、批量和超时；关闭、拒收、超时或异常后业务继续执行。异常只记录类型和固定分类，不把异常字符串写进 Span。追踪映射写入异常不扩大授权，也不改变已有业务指纹。关闭后不初始化 Exporter、不进行遥测网络请求。

Codex 先使用 app-server 的真实 session/turn/item 生命周期建立跨度；仅有完成事件时不得伪造开始时间。原生 OTel/Pilot 子链是否可以继承父上下文须另行实际验收，不把两个有 session 属性的独立 Trace 宣称为已自动合树。

## 验收

| ID | 可观察结果 |
| --- | --- |
| OBS-01 | 默认关闭、无阿里云依赖；通用 OTLP 接收器可接收 Go/Python Span |
| OBS-02 | HTTP traceparent 连续传播；公网注入与无效/过长元数据被隔离 |
| OBS-03 | Go 后台重读操作恢复原关联，重复投递不改绑定或重执行 |
| OBS-04 | Relay 队列→设备→Worker 保留上下文，白名单外字段不进入本机请求 |
| OBS-05 | Worker 两轮同 Native 根、各自独立验证；任务落盘/进程重启后关联仍在 |
| OBS-06 | Router、模型、工具、记忆和 Native 可见事件有实际 Span；未观测字段保持未知 |
| OBS-07 | 认证材料与合成隐私标记在实际 OTLP payload 中不存在 |
| OBS-08 | 遥测关闭/接收端故障不改变授权、幂等、错误、取消和恢复语义 |
| OBS-09 | ARMS 配置及预检独立；实际导出与云端查询结果分开记录，不以本地接收成功代替云验收 |

## 实施计划

- [x] P0：规范、ADR、通用配置和验收合同。
- [x] P1：Go/Python OTel 模块、关闭/脱敏/故障测试。
- [x] P2：HTTP、持久操作、MCP/Relay 与 Worker 上下文。
- [x] P3：Router/模型/工具/记忆、Native 与验证 Span。
- [x] P4：通用本地 OTLP 端到端验收、部署配置及 ARMS 预检工具（本地合成接收器验收）。
- [x] P5：相关回归、产品/工程文档，合入 main；应用 ce7ce59 已升级现有云端，11 个远端 CI job 通过。
- [x] P6a：取得真实配置，服务器探测与两轮真实 Router 模型调用的 ARMS 接收、索引查询和展示验收。
- [x] P6b：此前两轮合成协议数据的四服务执行树在 ARMS 展示，保留原始时间及 Span ID，没有重放业务操作。
- [ ] P6c：新的真实云端 → 家庭 Worker → Codex 授权任务；当前家庭接入已过期，未恢复权限，不能用合成数据代替。

实际证据由验证脚本生成并脱敏保留；未完成项不得预先勾选。版本发布、云端升级和真实 Native/模型验收各自单列。

## 2026-11-12 本地证据与交付边界

[脱敏收据](../verification/observability-2026-11-12.json)记录实际 protobuf 父链、两轮/同原生根、隐私标记和源码哈希。OBS-01～08 在标明的本地合成模型/原生协议范围内通过；OBS-09 的配置、预检与接收/索引分离已实现，真实 ARMS 接收及查询尚未执行。324 项常规与 76 项固定运行时、Go/实际 Helm/Compose 和文档门禁通过；不将这些结果外推成真实供应方、SSH 全量复验或云端发布。

后续已按用户要求发布：ce7ce59 的 11 项远端 CI 全通过（包含完整 Gateway local/SSH 与固定镜像检查），既有实例的 20 项可信 HTTPS/API 检查通过，原账号与历史数据保留。服务器 probe、两轮真实模型 Trace 和单独标记的合成四服务树均已在 ARMS 核验；见[云端收据](../verification/observability-cloud-2026-11-12.json)。前段“尚未执行”保留为本地收据当时的范围，现有线上状态以本段和 STATUS 为准。
