# 连续追问远程 Codex

在已有 Codex 任务完成后，继续使用同一个秘书对话，例如：

1. “让 Codex 修复这个问题。”
2. “继续问刚才的 Codex，解释为什么这样修改。”
3. “沿用这个 Codex 会话，再检查负数的情况。”

秘书工具 `continue_codex` 从当前用户、聊天及其 incarnation 中解析已有任务，沿用其原生会话和 worktree。每次追问会创建新的后台任务，分别保存状态、摘要、独立测试、取消及通知。原任务结果保留。多个会话混在同一聊天时，需指定最新的 **DeerFlow task ID**；不能填原生 session ID 或 Worker handle。自然语言选工具仍由秘书模型完成；需要明确要求继续 Codex，而非假定所有聊天消息都会自动转发。

## 接入已有 DeerFlow

升级 Worker 与控制端的 DeerMate wheel，保留原数据库和配置，先备份 SQLite。Worker 的 `/capabilities` 应包含 `continuation: child-tasks-v1`；这个附加字段不会改变旧的基本操作列表。旧 Worker 会在修改请求前被新工具拒绝，不自动新建替代会话。

合并最新 [本地 MCP 示例](../examples/deerflow.extensions.json)或 [SSH 示例](../examples/deerflow.ssh.extensions.json)。两个后台 toolset 的 raw 名称须分别为：

| 轮次 | 提交 | 查询 | 取消 |
| --- | --- | --- | --- |
| 首轮 | `submit_task` | `get_task_status` | `cancel_task` |
| 追问 | `continue_task` | `get_continuation_status` | `cancel_continuation_task` |

固定上游要求各角色名称唯一，后两项是相同 Worker 操作的独立 MCP 别名。不要自行复用第一组名称。后台绑定变化需要受控重启 Gateway。

Gateway 的 Python 环境也需安装该 wheel，随后在现有 `config.yaml` 合并：

```yaml
tools:
  - name: continue_codex
    group: deermate
    use: deermate.deerflow_tools:continue_codex
tool_groups:
  - name: deermate
```

这是固定 DeerFlow 支持的内部 tool provider，不增加浏览器 Python API。公开登录、管理和 API 仍由 Go 提供。ACK 已注册 Worker 的配置和本地 Docker Worker 接入会生成这些条目；空模型/空 Worker 的新单机配置保留为空。已有部署须合并配置，不能覆盖原模型、账号、其他工具或凭据。

## CLI 与边界

低层客户端也可继续指定的最新 Worker 任务：

```bash
deermate --config controller.toml --worker home continue WORKER_TASK_HANDLE \
  --key unique-round-2 --message 'Explain the earlier change.'
```

它返回新的任务 handle，后续 status/events/diff/cancel 使用这个新值。重复同键同内容返回已接纳的子任务，不追加轮次；复用键但改变内容会冲突。原有 `resume` 保留显式恢复用途；有子任务后，旧父任务不能再 resume，避免分叉共享工作区。

执行中的会话、旧轮次、缺失原生会话、已改变的项目策略，以及待输入/审核/恢复状态都会拒绝继续。取消某一轮不等于撤销整个会话或自动停止其他任务。SSH 到期/撤权规则照常适用，接入工具不会延长授权。每次追问仍是有时限、受项目策略约束的原生执行，也会重新运行注册的验证命令并可能消耗模型额度；不是无限期运行的进程。

规格见 [M2 多轮会话](specs/m2-codex-conversation.md)。离线三轮 MCP/SSH、实际固定 Gateway/SQL 及真实云端模型→家庭 Codex 三轮问答均已通过；两次追问的独立测试与通知通过，第三轮准确回忆上一轮标记，保留同一个原生会话/工作区与原补丁。见 [STATUS](STATUS.md)与[真实收据](verification/codex-conversation-live-2026-10-29.json)。

## 复核真实验收

以下命令会使用模型额度，要求同一 origin 上已有 `verify_secretary.py --mode dispatch` 的成功 demo 状态，及操作员本机独立 Worker/公网 SSH enrollment：

```bash
python scripts/verify_conversation.py --live \
  --url https://YOUR_PUBLIC_IP --account-file PRIVATE_OWNER_JSON \
  --parent-state PRIVATE_DISPATCH_STATE --worker-config PRIVATE_WORKER_TOML \
  --ssh-controller-config PRIVATE_PUBLIC_READER_TOML --ssh-worker home \
  --state-dir .deermate/conversation-acceptance \
  --receipt .deermate/conversation-acceptance/receipt.json
```

脚本只对单一 demo 原对话增加两次追问。每次先把 attempted 保存到完整私密 ledger；响应丢失后重跑相同命令只核对原 run，不发送替代任务。它核对精确转发文本、原生 session/workspace、父证据、独立测试、通知及记忆标记，收据不输出对话 ID、账号、提示词、标记值、路径或密钥。不要把新建 state 目录当作超时重试方式。正常离线测试不运行该脚本。
