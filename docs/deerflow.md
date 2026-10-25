# DeerFlow 本地任务接入

状态：M2.1 本地 Python MCP 桥接已实现。真实 stdio MCP 与固定版本的 DeerFlow 原生任务驱动已验证；完整 Gateway、SQL 任务跟踪和前端部署尚未实测。SSH 远程 Worker 待 M2.2。

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

上游文档提供当前 thread 的查询路由 `GET /api/threads/{thread_id}/mcp-tasks` 及 `GET /api/threads/{thread_id}/mcp-tasks/{task_id}`；这里的 `task_id` 是 DeerFlow 跟踪行 ID，DeerMate 返回的是其保存的 `remote_task_id`。完整部署中应验证 SQL 跟踪行跨 Gateway 重启后还能查询同一 Worker 任务。

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
ruff check src tests scripts/live_smoke.py
python -m build --wheel
```

`test_mcp.py` 使用真实 MCP SDK 客户端和 stdio 子进程、真实 HTTP Worker、临时 Git 仓库及明确标识的离线 Codex 协议 fixture。覆盖连接重建、幂等、取消、成功/失败验证和表单；`test_bridge.py` 覆盖 Worker 重启、恢复与错误边界。这不是本次重新跑真实模型的记录。

可选上游兼容检查使用实际驱动源码，不安装完整 DeerFlow、启动 Gateway 或请求模型：

```bash
git clone https://github.com/bytedance/deer-flow.git /path/to/deer-flow
git -C /path/to/deer-flow checkout --detach a1b89d0432de4e45adc59f512cb25bb386ea1e51
DEERMATE_DEERFLOW_CHECKOUT=/path/to/deer-flow python -m pytest -q tests/test_deerflow_compat.py
```

检查会验证提交和所加载源码未修改，调用上游 `OrdinaryMcpTaskDriver` 经真实 MCP 完成提交、查询、取消、完成、失败、待答，以及用磁盘保存的句柄重建驱动。未设置环境变量时，该项显式跳过。它没有启动 DeerFlow 的 SQL repository/service 或网页，不能代替 Gateway 重启验收；[AC-M2-01](SPEC.md) 仍为部分验证。

移除 DeerFlow 的桥接配置并重启即可停用接入，不删除 Worker 任务或修改数据库格式。当前不支持跨主机通信、多用户授权或 SSH。下一步是实际 Gateway/SQL 跟踪验证，再推进远程连接。
