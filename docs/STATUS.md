# 当前开发状态与 Agent 接续

最后核对：2026-10-25。历史见 [EVOLUTION.md](EVOLUTION.md)。这是由开发 Agent/维护者更新的版本化快照，不是自动监控服务。

## 当前交付

| 项目 | 当前事实 |
| --- | --- |
| 产品阶段 | M1 本地 Worker 已实现；M2.1 本地 Python MCP 桥接与上游驱动兼容检查已实现 |
| 开发分支 | `feat/m2-deerflow-bridge`，包含此前 M1 与接续文档 |
| 运行代码基线 | [`2a941b1`](https://github.com/mzydmer/deermate/commit/2a941b140348727b6298009dcdf04a3397691caf) |
| 主线基线 | 本次远端核对 `main` 仍为 `e9f228d`；M1/M2 尚未合并 |
| 发布状态 | 开发分支交付；包仍为源码 alpha `0.1.0a1`，没有正式 release 或 PyPI 发布 |
| PR | 本次远端核对无开放 PR；[比较开发分支](https://github.com/mzydmer/deermate/compare/main...feat/m2-deerflow-bridge) |
| 下一步 | 完整 DeerFlow Gateway/SQL 任务跟踪与重启验收，然后 M2.2 SSH 远程 Worker |

上面的哈希是运行代码提交；后续文档提交可继续推进 HEAD，不需要为填写自身哈希反复提交。接续时核对 Git 和远端状态。

## 已实现能力

M1 保留 Python API/CLI、SQLite 任务/会话/事件、幂等提交、Codex app-server、独立 Git worktree、补丁与管理员验证命令、取消与同会话继续、表单处理、时限与并发、本地鉴权和显式重启恢复。

M2.1 新增：

- `deermate mcp` 通过 stdio 暴露 `submit_task`、`get_task_status`、`cancel_task`，使用真实 MCP SDK 和严格参数 schema。
- 桥接只连接独立 Worker 的固定 loopback API；读取已有私有 token，禁用环境代理和重定向，不创建执行进程或直接访问数据库。
- MCP 连接重建仍能使用原 ID；重复提交复用任务，不创建第二个原生会话。
- 取消在 8 秒预算内等待确认；不确定时返回工具错误。完成竞争保留实际终态。
- 表单、review、recovery 保留为需要处理的状态；不自动批准、回答或重放。
- 有长度限制的摘要、验证记录节选及本地 diff 查询提示；不把完整 prompt、配置和补丁复制到上游。
- 固定 DeerFlow `a1b89d0432de4e45adc59f512cb25bb386ea1e51` 的实际 `OrdinaryMcpTaskDriver` 经真实 MCP 的兼容检查；新增 CI 专项 job。

运行：[本地 Worker](local-worker.md)、[DeerFlow 配置](deerflow.md)。设计与范围：[基础规格](SPEC.md)、[M2.1 规格](specs/m2-deerflow-task-bridge.md)、[ADR 0003](decisions/0003-independent-mcp-bridge.md)。

## 本次实际验证 · M2.1

| 检查 | 结果与边界 |
| --- | --- |
| `python -m pytest -q` | 51 passed、1 skipped；跳过的是需显式 upstream checkout 的兼容检查；一条上游 Starlette TestClient 弃用提示 |
| `DEERMATE_DEERFLOW_CHECKOUT=<pinned checkout> python -m pytest -q tests/test_deerflow_compat.py tests/test_bridge.py tests/test_mcp.py` | 34 passed；包含固定版本的真实 DeerFlow 驱动、真实 MCP stdio 子进程、HTTP Worker 与临时 Git 仓库 |
| token 读取边界调整后 `python -m pytest -q tests/test_bridge.py` | 28 passed；验证私有文件、缺失/符号链接、HTTP 错误、恢复、状态与证据边界 |
| `ruff check src tests scripts/live_smoke.py` | 通过 |
| `python -m build --wheel` | 通过；`deermate-0.1.0a1-py3-none-any.whl` |
| CI | 已配置 Ubuntu/Python 3.11、macOS/Python 3.12 常规检查和固定上游驱动 job；本页未预先声明本次远端运行通过，查看 [Actions](https://github.com/mzydmer/deermate/actions) |

本次环境为 macOS/Python 3.12、MCP SDK 1.30.0。此运行时安装 SDK 时，cryptography 最新源码构建缺少 OpenSSL；使用 `pip install --only-binary=cryptography 'mcp==1.30.0'` 选用兼容 wheel 后完成安装。没有修改系统 Python 或全局 Codex 配置。所有新增验证均使用明确标识的离线 Codex fixture，没有请求真实模型。

## 既有验证 · M1，非本次重跑模型

运行代码基线 [`7dfe34a`](https://github.com/mzydmer/deermate/commit/7dfe34ac610a4f2ecd600ab77d28432786916b6a) 的 18 项离线测试、Ruff、wheel 构建通过；[CI 40175946902](https://github.com/mzydmer/deermate/actions/runs/40175946902) 的 Ubuntu/Python 3.11 与 macOS/Python 3.12 两组通过。此次 51 项常规检查包含这些离线测试。

既有真实 Codex 验证使用 macOS/Python 3.12、Codex `0.164.0-alpha.11.1` 和显式 `gpt-6.1-sol`：临时仓库修复、独立执行一项测试通过并收集 diff；真实中断与继续在三个 attempt 保留同一 thread。环境和复现入口见 [local-worker.md](local-worker.md#verification) 与 [live_smoke.py](../scripts/live_smoke.py)。临时原始日志未保留；说明和脚本不等于持久化原始测试收据。本次未重复调用模型。

## 尚未完成

| 范围 | 状态与影响 |
| --- | --- |
| 完整 DeerFlow Gateway、SQL tracker、网页 | 未部署实测；驱动/SDK 检查不等于 Gateway 重启或产品 UI 验收，AC-M2-01 部分验证 |
| SSH、设备配对、NAT、中继 | 未实现；当前同主机、同网络命名空间、单一所有者，无远程 E2E 通道 |
| 表单回答与恢复的秘书操作入口 | MCP 仅有三个生命周期工具；回答、review 和显式恢复仍走本地 CLI |
| Claude、DSH、Qoder、专职路由、GitHub 自动维护 | 未实现 |
| 调研、邮件、桌面控制、统一仪表盘 | 规划中；视频为概念模拟 |
| 进程硬崩溃、孤儿进程及远程恢复 | 未完成 live 验证；现有有序重启测试不证明跨机器容错 |
| 生产隔离、秘密脱敏、数据库加密与容量保留 | 未具备完整实现；仅供可信项目本地实验 |

此前创建 PR 遇到连接器写权限不足，浏览器控制随后不可用；工作已保存在 Git 开发分支。本次没有将旧失败重新当作授权问题，也没有声称 PR、合并或 release 已完成。工具恢复后先核对已有 PR，避免重复创建。

## 下一项验收

1. **M2.1 / AC-M2-01 补全：** 在独立、固定上游提交的 DeerFlow 环境开启 SQL 和 `mcp_tasks`，通过 Gateway 提交任务，保留 SQL tracker ID 与 Worker ID；重启 Gateway 后继续查询、取消与接收结果。保留可复核的脱敏收据，区分模型会话和后台服务验收。
2. **M2.2 / FR-013：** 形成 SSH 主机身份、密钥生命周期、最小执行账户、断线状态与撤权规格，再实现远程路径。当前不把云端 DeerFlow 连接到家中 Worker 视为已支持。

按 [AGENTS.md](../AGENTS.md) 接续。每次有意义的工作同步当前证据和下一步，行为变化更新 spec，历史结果追加 EVOLUTION；常规文字修正不新增演进事件。
