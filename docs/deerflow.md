# DeerFlow 本地任务接入

状态：M2.1 本地 Python MCP 桥接已实现。真实 MCP、固定上游驱动，以及实际 Gateway/SQLite 的后台任务和有序进程重启均已通过 fixture 验收。模型通知、浏览器 UI 和 SSH 远程 Worker 仍待后续验证。

## 运行方式

```text
DeerFlow → stdio MCP 桥接 → 鉴权 loopback HTTP → 独立 DeerMate Worker → Codex
```

桥接不启动 Worker、不直接访问数据库。DeerFlow 关闭或重建 MCP 连接后，Worker 继续持有任务；新的 MCP 连接使用相同任务 ID 查询。Worker 本身重启后，运行中的任务会要求显式恢复。

M2.1 适用于同一可信主机、单一所有者。DeerFlow 后端进程必须能运行桥接的 Python、访问同一配置和 token 文件，并通过 `127.0.0.1` 到达 Worker。容器中的 loopback 指向容器自身；本指南没有提供 Docker 到宿主机或跨机器的连接方案。

## 安装并启动 Worker

按[本地 Worker 指南](local-worker.md)注册可信 Git 项目、验证命令和 Codex。安装可选 MCP 支持：

```bash
python -m pip install -e '.[mcp]'
deermate --config /absolute/path/to/deermate/deermate.toml --port 18777 serve
```

将示例中的绝对路径换成你的实际路径。Worker 创建私有 `api.token`，桥接只读取已有文件。不要把 token 放进 DeerFlow 配置或工具参数。配置中的 `state_dir` 也应改为绝对路径，避免从不同工作目录启动时指向不同状态目录。

DeerFlow 将自行启动这个 stdio 命令：

```bash
deermate --config /absolute/path/to/deermate/deermate.toml --port 18777 mcp
```

它在标准输入/输出上传输 MCP 帧，不是交互终端，也不会创建新的 Worker。普通 CLI 保持原用法；查看证据、回答表单或恢复时使用与 Worker 相同的 `--config` 和 `--port`。

## 配置 DeerFlow

本次兼容目标是 [DeerFlow 提交 a1b89d0](https://github.com/bytedance/deer-flow/commit/a1b89d0432de4e45adc59f512cb25bb386ea1e51)，其 backend 版本为 `2.2.0-dev`，不是对所有版本的支持声明。依据该版本的 [MCP 配置文档](https://github.com/bytedance/deer-flow/blob/a1b89d0432de4e45adc59f512cb25bb386ea1e51/backend/docs/MCP_SERVER.md)和[后台任务驱动](https://github.com/bytedance/deer-flow/blob/a1b89d0432de4e45adc59f512cb25bb386ea1e51/backend/packages/harness/deerflow/mcp/tasks/ordinary.py)。

1. 将 [deerflow.extensions.json](../examples/deerflow.extensions.json) 中的 `deermate` 条目合并到 DeerFlow 根目录 `extensions_config.json` 的 `mcpServers`。替换 Python、配置和 `cwd` 的绝对路径；不要覆盖已有的其他服务器。
2. 将 [deerflow.runtime.yaml](../examples/deerflow.runtime.yaml) 的设置合并到已有 `config.yaml`，开启 SQL 持久化和 `mcp_tasks`。现有 PostgreSQL 部署保留 PostgreSQL，不能为了复制示例切换数据库。
3. 启动 Worker，然后重启 DeerFlow。任务工具配置、连接和超时变化需要重启。

绑定使用三个**原始工具名**：`submit_task`、`get_task_status`、`cancel_task`。DeerFlow 可能向模型展示带 `deermate_` 前缀的名字，不能把该前缀写进 `task_toolsets`。开启后台任务后，上游只向模型暴露提交工具，查询和取消由其后台运行时处理。

提交参数示例：

```json
{
  "project_id": "demo",
  "prompt": "Investigate and fix the failing addition test.",
  "idempotency_key": "addition-fix-001"
}
```

`project_id` 必须预先注册。相同请求重试使用相同键；不同任务使用新键。提交返回稳定 ID 及上游要求的 `running` 接纳状态，随后查询真实执行状态。即使重复提交已结束的任务，也不会重新运行它。

上游提供当前 thread 的查询路由 `GET /api/threads/{thread_id}/mcp-tasks` 及 `GET /api/threads/{thread_id}/mcp-tasks/{task_id}`；这里的 `task_id` 是 DeerFlow 跟踪行 ID，DeerMate 返回的是其保存的 `remote_task_id`。下面的实际 Gateway 验收已证明 SQL 跟踪行跨有序进程重启仍能查询同一 Worker 任务。

## 状态与证据

| Worker 状态 | DeerFlow 契约 | 含义 |
| --- | --- | --- |
| queued / starting / running / cancelling | running | 仍未确认结束，`worker_status` 保留真实阶段 |
| completed / failed / cancelled | 同名终态 | 保留实际结果，取消与完成竞争时不伪造 cancelled |
| input_required | input_required | 用现有本地 events/answer 处理表单 |
| needs_review | input_required | 检查验证、补丁和权限拒绝，再决定是否继续 |
| recovery_required | input_required | 先核实旧执行已停止，再通过本地 resume 显式恢复 |

结果包括有长度限制的摘要、验证退出码和输出片段、原生 session ID、attempt 及 diff 查询提示。不会原样复制任务 prompt、配置、项目路径或完整 diff；摘要和命令输出仍可能包含项目内容，不提供通用秘密脱敏保证。`*_truncated` 标识节选；完整证据保留在本地 Worker。CLI 提示不是远程可下载的 artifact URL。

取消最多等待 8 秒确认。仍在执行、需要 review/recovery 或 Worker 不可达时，工具返回 `isError: true`；这不是取消成功或任务失败。DeerFlow 可重试查询/取消。真正缺失的 ID 返回正常结构化 `failed` 和 `error_code: task_not_found`，以便上游停止无效跟踪。原生表单回答和恢复不由这三个工具自动执行。

## 验证与当前限制

常规验证不调用模型：

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
ruff check src tests scripts/live_smoke.py scripts/verify_deerflow_gateway.py
python -m build --wheel
```

`test_mcp.py` 使用真实 MCP SDK 客户端和 stdio 子进程、真实 HTTP Worker、临时 Git 仓库及明确标识的离线 Codex 协议 fixture。覆盖连接重建、幂等、取消、成功/失败验证和表单；`test_bridge.py` 覆盖 Worker 重启、恢复与错误边界。这不是本次重新跑真实模型的记录。

可选上游兼容检查使用实际驱动源码，不安装完整 DeerFlow、启动 Gateway 或请求模型：

```bash
git clone https://github.com/bytedance/deer-flow.git /path/to/deer-flow
git -C /path/to/deer-flow checkout --detach a1b89d0432de4e45adc59f512cb25bb386ea1e51
DEERMATE_DEERFLOW_CHECKOUT=/path/to/deer-flow python -m pytest -q tests/test_deerflow_compat.py
```

该驱动检查会验证提交和所加载源码未修改，调用上游 `OrdinaryMcpTaskDriver` 经真实 MCP 完成提交、查询、取消、完成、失败、待答及句柄重建。未设置环境变量时显式跳过。它本身不启动 Gateway/SQL；下面另有实际后端进程验收。

## Gateway 与 SQL 验收

新增 [verify_deerflow_gateway.py](../scripts/verify_deerflow_gateway.py) 实际启动上游原始 `app.gateway.app`、lifespan、SQL repository/service、MCP 工具发现/提交包装、后台 poller 及原始 HTTP 查询/取消路由；没有用 mock 替换这些组件。它独立启动 DeerMate Worker，并完成 Gateway 进程关闭/重启、取消、验证成功/失败、Worker 失联和恢复。

为避免消耗模型额度，只有“模型选择并调用工具”这一步由带单次密钥的 verifier 专用提交入口代替。原生 Codex 使用明确标识的离线协议 fixture。该入口只存在于验收子进程，不是产品 API。子进程使用临时 dotenv、应用 home、SQLite 和测试仓库，过滤模型凭据、仅监听 loopback，并拒绝其非 loopback socket 连接；这不是对生产网络隔离的声明。

完整上游后端要求 **Python 3.12+**，另建环境；DeerMate Worker 自身仍支持 Python 3.11+。在 DeerMate 仓库中运行：

```bash
python -m pip install 'uv==0.13.5'
uv sync --project /path/to/deer-flow/backend --frozen --no-default-groups --python 3.12
python scripts/verify_deerflow_gateway.py \
  --checkout /path/to/deer-flow \
  --gateway-python /path/to/deer-flow/backend/.venv/bin/python \
  --receipt .deermate/verification/gateway-receipt.json
```

上游 checkout 必须是前述固定提交且 `backend` 没有本地修改。安装使用该提交的 `uv.lock`，不扩大 DeerMate 默认依赖。某些 macOS Intel 运行时需要为上游固定的 cryptography 50.0.0 提供 OpenSSL 开发库；本机用位于忽略目录的 OpenSSL 3.5.9 静态构建和安装命令环境 `OPENSSL_DIR` / `OPENSSL_STATIC=1` 完成，未降级上游依赖或修改系统安装。

可加 `--work-dir /new/empty/path` 保留本机日志和临时状态，目录必须尚不存在；默认工作目录在结束后清理。不要将原始日志、临时配置、数据库或 token 提交到仓库。仅提交由已知 fixture 生成并检查过的有限 JSON 收据。

现有[验收收据](verification/deerflow-gateway-2026-10-25.json)在 macOS/Python 3.12.14 完成 14 个检查，保留上游 commit/lock、脚本哈希、依赖版本、跟踪 ID 及场景结果。独立 pytest 入口也已通过：

```bash
DEERMATE_DEERFLOW_CHECKOUT=/path/to/deer-flow \
DEERMATE_GATEWAY_PYTHON=/path/to/deer-flow/backend/.venv/bin/python \
python -m pytest -q tests/test_deerflow_gateway.py
```

常规测试现为 51 passed、2 skipped；两项较重的上游检查均要求显式环境变量。CI 另有独立的 `deerflow-gateway` job，从固定源码和 frozen 环境执行同一脚本，并上传 fixture 收据。

验收只覆盖新 SQLite 数据库和有序进程重启。由于没有配置聊天模型，上游通知 run 会在模型装配阶段失败；本次验证的是任务 HTTP/SQL 结果，不是模型生成通知、聊天 UI、历史数据库升级、硬崩溃、SSH 或跨主机容错。详细条件见[验收规格](specs/m2-gateway-verification.md)。

移除 DeerFlow 的桥接配置并重启即可停用接入，不删除 Worker 任务或修改数据库格式。下一步为 M2.2 的 SSH 身份、密钥与远程连接设计。
