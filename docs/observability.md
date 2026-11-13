# 可选调用链与 ARMS 接入

DeerMate 的可观测核心使用 OpenTelemetry 和 OTLP/HTTP；开源部署默认关闭。Go、Gateway、MCP、授权 Relay 与 Worker 共享标准上下文，厂商配置单独放在 `deploy/observability/`。既有云端实例已接入 ARMS，开源部署可以换成其他兼容后端。

规格与验收合同见[可观测规格](specs/vendor-neutral-observability.md)，设计取舍见 [ADR 0017](decisions/0017-vendor-neutral-observability.md)。这是工程运维文档；产品技术说明见[系统架构](product/technical/architecture.md)。

## 已实现的观测边界

| 边界 | Span / 关联 |
| --- | --- |
| Go 入口与运行时请求 | `http.server` / `http.client`，记录注册路由与状态，不记录完整 URL |
| 持久派单与 Router 动作 | `operation.deliver` / `router.action`，从本人 operation 重读原上下文 |
| Gateway 与模型/工具 | `agent.operation`、`agent.model`、`agent.tool`，仅从实际响应读取用量 |
| 记忆读取 | `memory.retrieve`，不记录检索内容或记忆正文 |
| MCP 与 Relay | `mcp.client` / `mcp.server`、`device.relay`；通过元数据和队列传播 |
| Worker 与原生协议 | `worker.request` / `worker.execute`、`codex.session.open`、`codex.turn`、`codex.tool` |
| 独立验证 | `worker.validation`，与原生轮次分别记录 |

固定名字有助于比较各层耗时。实际业务标识保存在 `deermate.*` Span 属性：conversation/incarnation、work/operation、instance/task 和 native session/turn。不是每条 Span 都具有全部字段，也不会用业务 ID 建立高基数指标标签。本轮没有独立 Metrics、Logs、浏览器回放或 AgentLoop 评估管线。

出站 `http.client` 跨度包含响应体的消费时间，适用于 SSE/模型流式输出：收到响应头不会结束计时；响应读到 EOF、读取失败、关闭或请求取消时结束一次。空响应可立即结束。取消和超时只记录固定错误分类，不记录异常原文；不会为了观测而缓存、预读或重放响应。升级响应保留原有双向读写接口，关闭遥测时不包装响应体。

2026-11-12 的实际页面验收发现旧实现只计到响应头：一次 42.44 秒流式请求的客户端跨度仅为 41.28 毫秒。这属于客户端跨度计时缺陷，不能据此评估模型或网络耗时；修复后的具体上线范围与 ARMS 复验见 STATUS。

## 同一话题与异步恢复

一个话题可包含多轮 Trace，原生会话仍遵循既有绑定。不要把整个长期话题当作一个永不结束的 Span。

Go 在独立的 `deermate_operation_trace` 表保存本人 operation 的首次有效上下文；Worker 在 `deermate_task_trace` 表保存 task 的首次关联。后台读取这些记录恢复父链，重复投递不能替换原映射。表中没有模型正文，上下文不进入任务参数、提示词、策略或幂等指纹。存储映射失败不扩大权限，也不增加执行重试。

原生执行中断后，恢复跨度通过 Span link 关联原 Trace，并标记恢复状态。链接表示关联，不表示旧 Span 仍在执行。未知回执仍按原操作只读核对。SDK 队列满、采样或后端丢失数据都可能造成不完整链路，因此任务账本和验证证据仍是事实依据。

## 隐私与故障

默认不导出 prompt、回复、记忆、命令参数、stdout/stderr、补丁、认证头、URL 查询或异常原文。只允许固定操作名、状态/错误类型、合法系统 ID、实际用量和 SDK 时间。资源属性只接受 `service.version`、`service.namespace`、`deployment.environment.name`，其他 `OTEL_RESOURCE_ATTRIBUTES` 项被忽略。ID 也属于运营数据，应为接收后端配置合适的访问权限和保留期。

公网 Go 入口重新开始根 Trace，忽略用户提供的父上下文；内部 HTTP/MCP/Relay 只传播有界 `traceparent`、`tracestate` 和身份白名单，不传播 baggage。Relay 在原有授权检查之后接纳关联，关联本身不授予任何工具权限。Python/Go SDK 的 trace flags 差异在边界兼容，保持原 Trace ID。

每个进程队列最多 512 个待导出 Span、每批最多 64 个，约 500ms 批量发送；正常导出使用约 1 秒超时。接收失败只给固定提示，业务继续。关闭时不初始化 exporter，不向遥测后端发请求。Python exporter 不继承系统代理；需要代理出口时使用明确配置的本地 Collector。关闭或更改配置后需重启进程。

## 配置与预检

```bash
python -m pip install -e '.[observability]'
# 复制通用或 ARMS 样例，在私有文件中填写真实值并 chmod 600。
python scripts/observability.py check --env-file /private/path/observability.env
python scripts/observability.py probe --env-file /private/path/observability.env \
  --receipt /private/path/observability-probe.json
```

使用标准变量：

- `DEERMATE_TELEMETRY_ENABLED=true` 明确启用；缺省关闭。
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` 是完整 traces URL；或设置 base `OTEL_EXPORTER_OTLP_ENDPOINT` 自动附加 `/v1/traces`。
- `OTEL_EXPORTER_OTLP_HEADERS` / `OTEL_EXPORTER_OTLP_TRACES_HEADERS` 保存接收端要求的写入鉴权。
- `OTEL_SERVICE_NAME` 区分 control、Gateway、MCP 和 Worker。
- `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` 使用 SDK 支持的标准采样配置；默认 parent-based always-on。需要降低用量时可用 `parentbased_traceidratio` 与 `0.1`，被采样丢弃的 Trace 不保证完整。

非本机接收端要求 HTTPS。localhost HTTP 用于本地接收器；`DEERMATE_TELEMETRY_ALLOW_INSECURE=true` 仅为明确隔离的测试网络保留。填写后的文件、endpoint 和写入 Key 不得进仓库、截图或普通日志。

`check` 不联网；`probe` 发送一条合成 OTLP Span，不调用模型。`export_accepted` 仅证明传输接收成功；需在接收后端按回执 Trace ID 查询，才能另行记录索引与展示验收。

## Single-host Compose

先构建包含本轮 Go 二进制和 Python wheel 的镜像，并使用既有备份/升级流程准备 bundle。配置命令只更改明确指定的 bundle，不创建云资源或放开设备权限：

```bash
python scripts/observability.py configure-bundle \
  --bundle /private/path/bundle --env-file /private/path/observability.env
sh /private/path/bundle/start.sh
# 上游地址随服务重建变化时，刷新入口代理的解析。
docker compose --env-file /private/path/bundle/.env \
  -f /private/path/bundle/compose.yaml restart nginx
```

命令原子写入 mode-0600 `observability.env`，为 control/Gateway 加载它，指定独立 service name，复制配置工具并更新首次初始化所用的 MCP seed。**已有实例实际使用的 MCP 配置需要另行更新**：stdio 不会自动继承所有 OTEL 环境变量，seed 也不会覆盖已有配置。

Gateway 更新后，在其已有环境中配置当前启用的 MCP 文件，再重启以更新会话池。以下命令使用容器已有的遥测环境，不在命令行传 Key：

```bash
# 用实际 Compose 项目名替换 PROJECT。
docker exec PROJECT-gateway-1 /app/backend/.venv/bin/python \
  /etc/deermate/observability.py configure-mcp \
  --mcp-config /app/backend/.deer-flow/extensions_config.json
docker restart PROJECT-gateway-1
```

如使用个人 MCP 配置，对相应文件单独执行同一命令。输出会给出匹配的 DeerMate stdio profile 数量；0 表示该文件没有待配置的 profile，不能视为 MCP 已接入。工具只更新 `python -m deermate.cli … mcp` profile 的遥测环境和标准 interceptor，保留原命令参数、其他服务器、授权与凭据。之后新建的 profile 也需配置，不能假定一次执行覆盖所有未来连接。

旧实例如果使用 `uvx --offline --from …whl … deermate --relay-config … mcp`，该命令会报告 0；它不会升级旧 wheel。先备份实际启用的配置，再将这个已识别的入口迁移为当前 Gateway 环境的 `/app/backend/.venv/bin/python -m deermate.cli --relay-config <原路径> mcp`，保留原 relay 路径、其他参数和 profile 字段；在隔离环境检查当前 CLI、MCP/SSH 与 OTel 依赖后再应用。2026-11-12 既有实例使用了这项显式迁移，并逐字段核对了其他设置与设备授权。

独立 Worker/MCP 在各自宿主机安装 extra 并以服务管理器加载私有配置后重启，不能通过云 bundle 自动获得设备执行权限。ACK/Kubernetes 使用相同环境变量，通过既有 Secret 注入 control/Gateway 与 MCP 子进程；本轮没有新增 Operator 或开通 ACK/ARMS 资源。

## 更换后端与停用

更换兼容 OTLP/HTTP 后端只替换私有 endpoint/headers，重新配置并重启全部发出方。业务代码不需要更改。可选 Collector 也使用这个边界；本轮没有强制增加驻留 sidecar。

停用时将 control、Gateway、每个 MCP profile 和 Worker 的 `DEERMATE_TELEMETRY_ENABLED` 改为 `false` 后重启。`configure-mcp` 是启用预检工具，要求 true；停用使用原服务配置或直接编辑明确的 profile，不能再次执行启用命令。已保存的关联和任务数据无需删除，不会导致任务重放。单独安装的原生探针需独立停用，历史后端数据按其保留/删除策略管理。

ARMS 的地域、获取配置、索引验收与限制见[ARMS 接入](../deploy/observability/arms/README.md)。2026-11-12 已验证现有北京工作空间接收新加坡服务器的 HTTPS OTLP，并查询到两轮真实 Router 模型调用；[上线收据](verification/observability-cloud-2026-11-12.json)区分真实模型和合成执行树。原生内部模型调用、Pilot 自动子链合树和供应方缺失的 Token 用量仍保持未知。

## 可复现验收

```bash
python -m pytest -q tests/test_observability.py tests/test_observability_mcp.py \
  tests/test_observability_cli.py
# 编译本机 Go 后运行真实 Go → connector → Worker 协议测试：
DEERMATE_GO_BINARY=/absolute/path/deermate python -m pytest -q tests/test_agent_relay.py
```

本地 Docker 验收复用 `prepare_continuous_fixture.py`、`verify_continuous.py` 与 `verify_continuous_native.py --telemetry-env-file /private/path/fixture.env`，使用独立 loopback 端口、隔离网络、Fake 模型、toy 项目和合成原生协议。测试用接收器 `tests/otel_receiver.py` 只用于这类受控环境，不是生产 Collector；原始 protobuf 保留在私有测试卷中，仓库仅保留脱敏收据。
