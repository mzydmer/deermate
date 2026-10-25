# 当前开发状态与 Agent 接续

最后核对：2026-10-25。历史见 [EVOLUTION.md](EVOLUTION.md)。这是由开发 Agent/维护者更新的版本化快照，不是自动监控服务。

## 当前交付

| 项目 | 当前事实 |
| --- | --- |
| 产品阶段 | M1 本地 Worker 与 M2.1 MCP 桥接已实现；实际 Gateway/SQLite 后端进程验收通过 |
| 开发分支 | `feat/m2-gateway-verification`，继承此前 M1、桥接与接续文档 |
| Worker/MCP 运行基线 | [`2a941b1`](https://github.com/mzydmer/deermate/commit/2a941b140348727b6298009dcdf04a3397691caf)，本轮未修改产品运行代码 |
| Gateway 验收工具基线 | [`14b0d8d`](https://github.com/mzydmer/deermate/commit/14b0d8da17e1978c10a80e7e997aa3f5d962aeb7) |
| 主线基线 | 本次远端核对 `main` 仍为 `e9f228d`；M1/M2 尚未合并 |
| 发布状态 | 开发分支交付；包仍为源码 alpha `0.1.0a1`，没有正式 release 或 PyPI 发布 |
| PR | 本次远端核对无开放 PR；[比较开发分支](https://github.com/mzydmer/deermate/compare/main...feat/m2-gateway-verification) |
| 下一步 | M2.2 SSH 主机身份、密钥与远程 Worker；模型通知/UI 另行验证 |

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
- 实际上游 Gateway 应用和 lifespan、SQLite repository/service、MCP 工具发现/提交包装、后台 poller 及原始 HTTP 查询/取消路由，已在独立进程中完成有序重启与 Worker 失联恢复验收。
- 已保存[有限 JSON 收据](verification/deerflow-gateway-2026-10-25.json)，记录固定源码/lock/脚本哈希、依赖版本、fixture ID 和 14 个检查结果；没有提交原始日志、数据库或 token。

运行：[本地 Worker](local-worker.md)、[DeerFlow 配置](deerflow.md)。设计与范围：[基础规格](SPEC.md)、[M2.1 规格](specs/m2-deerflow-task-bridge.md)、[Gateway 验收规格](specs/m2-gateway-verification.md)、[ADR 0003](decisions/0003-independent-mcp-bridge.md)。

## 本次实际验证 · Gateway/SQLite

| 检查 | 结果与边界 |
| --- | --- |
| `python -m pytest -q` | 51 passed、2 skipped；跳过的是显式 opt-in 驱动和 Gateway 检查；一条上游 Starlette TestClient 弃用提示 |
| `python scripts/verify_deerflow_gateway.py --checkout <pinned checkout> --gateway-python <frozen backend python> --receipt <file>` | 实际 Gateway/SQLite 独立进程验收，14 个检查通过，收据已保留 |
| `DEERMATE_DEERFLOW_CHECKOUT=<checkout> DEERMATE_GATEWAY_PYTHON=<backend python> python -m pytest -q tests/test_deerflow_gateway.py` | 1 passed，37.72 秒；验证独立 pytest 入口及收据边界 |
| `ruff check src tests scripts/live_smoke.py scripts/verify_deerflow_gateway.py` | 通过 |
| `python -m build --wheel` | 通过；`deermate-0.1.0a1-py3-none-any.whl` |
| 本次 CI | 已新增 `deerflow-gateway` 独立 job，使用固定源码、frozen 环境并上传 fixture 收据；远端结果需实际核对后记录 |

本次为 macOS/Python 3.12.14；上游环境使用 `uv sync --frozen --no-default-groups`，保留 cryptography 50.0.0、MCP 1.30.0 等锁定依赖。为此 Intel 运行时在忽略目录构建了 OpenSSL 3.5.9，通过安装进程的 `OPENSSL_DIR` / `OPENSSL_STATIC=1` 链接，没有降级上游依赖、修改系统安装或正常用户配置。完整版本与哈希在收据中。

验收使用空模型配置、临时 dotenv/home/数据库、过滤后的子进程环境、loopback 监听和 verifier-only 提交入口，未请求真实模型。模型通知 run 因没有模型而装配失败属于明确边界；原始 HTTP/SQL 的任务结果与取消均已验证。新数据库创建/版本 stamp 已通过，不代表历史数据库迁移升级或生产审计。

## 既有验证 · 桥接

原始桥接变更的 34 项显式上游驱动/HTTP/MCP 检查、token 调整后的 28 项相关检查均通过。[CI 40180093367](https://github.com/mzydmer/deermate/actions/runs/40180093367) 在 `6f0a51f` 的 Ubuntu/Python 3.11、macOS/Python 3.12 和 `deerflow-contract` 三组通过；它不覆盖本次新增的 Gateway verifier。Worker/MCP 产品运行基线未变。

## 既有验证 · M1，非本次重跑模型

运行代码基线 [`7dfe34a`](https://github.com/mzydmer/deermate/commit/7dfe34ac610a4f2ecd600ab77d28432786916b6a) 的 18 项离线测试、Ruff、wheel 构建通过；[CI 40175946902](https://github.com/mzydmer/deermate/actions/runs/40175946902) 的 Ubuntu/Python 3.11 与 macOS/Python 3.12 两组通过。此次 51 项常规检查包含这些离线测试。

既有真实 Codex 验证使用 macOS/Python 3.12、Codex `0.164.0-alpha.11.1` 和显式 `gpt-6.1-sol`：临时仓库修复、独立执行一项测试通过并收集 diff；真实中断与继续在三个 attempt 保留同一 thread。环境和复现入口见 [local-worker.md](local-worker.md#verification) 与 [live_smoke.py](../scripts/live_smoke.py)。临时原始日志未保留；说明和脚本不等于持久化原始测试收据。本次未重复调用模型。

## 尚未完成

| 范围 | 状态与影响 |
| --- | --- |
| 聊天模型通知、网页与真实使用流程 | 尚未验证；AC-M2-01 已覆盖本地 Gateway/SQLite 后端 fixture 范围，不能据此声称完整模型驱动的秘书体验 |
| SSH、设备配对、NAT、中继 | 未实现；当前同主机、同网络命名空间、单一所有者，无远程 E2E 通道 |
| 表单回答与恢复的秘书操作入口 | MCP 仅有三个生命周期工具；回答、review 和显式恢复仍走本地 CLI |
| Claude、DSH、Qoder、专职路由、GitHub 自动维护 | 未实现 |
| 调研、邮件、桌面控制、统一仪表盘 | 规划中；视频为概念模拟 |
| 进程硬崩溃、孤儿进程、远程恢复及历史数据库升级 | 未完成验证；本次新数据库/有序进程重启不证明这些能力 |
| 生产隔离、秘密脱敏、数据库加密与容量保留 | 未具备完整实现；仅供可信项目本地实验 |

此前创建 PR 遇到连接器写权限不足，浏览器控制随后不可用；工作已保存在 Git 开发分支。本次没有将旧失败重新当作授权问题，也没有声称 PR、合并或 release 已完成。工具恢复后先核对已有 PR，避免重复创建。

## 下一项验收

1. **M2.2 / FR-013：** 形成 SSH 主机身份、密钥生命周期、最小执行账户、断线状态与撤权规格，再实现一个可验证的远程路径。当前不把云端 DeerFlow 连接到家中 Worker 视为已支持。
2. **后续体验验收：** 在单独提供的模型配置中验证秘书选工具与任务通知，再做浏览器 UI walkthrough；保留来源与收据。不得将本次测试提交入口加入产品 API。

按 [AGENTS.md](../AGENTS.md) 接续。每次有意义的工作同步当前证据和下一步，行为变化更新 spec，历史结果追加 EVOLUTION；常规文字修正不新增演进事件。
