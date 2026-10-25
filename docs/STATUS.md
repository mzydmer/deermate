# 当前开发状态与 Agent 接续

最后核对：2026-10-25。此文件只保留当前状态；历史保留在 [EVOLUTION.md](EVOLUTION.md)。这是手动维护的版本化快照，不是自动监控服务。

## 一眼看懂

| 项目 | 当前事实 |
| --- | --- |
| 产品阶段 | M1 本地 Worker Alpha；完整私人秘书仍在构建中 |
| 实现分支 | `feat/m1-local-worker` |
| 运行代码基线 | [`7dfe34a`](https://github.com/mzydmer/deermate/commit/7dfe34ac610a4f2ecd600ab77d28432786916b6a) |
| 主线基线 | `main` 仍为 `e9f228d`，设计预览；本次核对时 M1 未合并 |
| 发布状态 | 代码已推送开发分支；未发布 PyPI 包或正式 release |
| PR 状态 | 本次核对时没有该分支的开放 PR；[分支比较](https://github.com/mzydmer/deermate/compare/main...feat/m1-local-worker)可直接查看改动 |
| 下一阶段 | M2：先接入 DeerFlow 后台 MCP 任务，再接 SSH 远程 Worker |

文档提交会继续推进分支 HEAD；上面的哈希特指最近验证过的**运行代码基线**，不是对文档最新提交哈希的猜测。每次接续都应核对实际 Git 和远端状态。

## 已实现范围

- Python Worker、FastAPI 本地 API 与 CLI。
- SQLite 任务、会话身份、策略快照与事件游标持久化。
- 注册项目接纳、幂等提交、独立继续键、冲突处理。
- Codex app-server 启动、事件、中断、同会话继续和受支持表单处理。
- 从已提交 HEAD 建立独立 Git worktree，收集补丁和验证命令输出。
- 任务时限、并发限制、权限扩展拒绝、单进程状态目录所有权。
- 本地 token、Host/Origin 检查与请求体限制。
- 重启后的显式恢复：保留身份与工作区，不自动重放运行中的任务。

对应需求与验收见 [SPEC.md](SPEC.md)。运行步骤见 [local-worker.md](local-worker.md)。

## 验证记录

以下是代码基线 `7dfe34a` 的既有验证，不是本次文档变更重新执行的结果。

| 验证 | 已知结果 | 证据/复现入口 |
| --- | --- | --- |
| 离线自动化测试 | 18 项通过；使用协议 fixture 与真实临时 Git 仓库，不调用模型 | `python -m pytest -q`；[tests/](../tests/) |
| 静态检查 | Ruff 通过 | `ruff check src tests scripts/live_smoke.py` |
| 构建 | wheel 构建成功，包版本 `0.1.0a1` | `python -m build --wheel`；[pyproject.toml](../pyproject.toml) |
| GitHub CI | Ubuntu/Python 3.11 与 macOS/Python 3.12 两组均通过 | [运行 40175946902](https://github.com/mzydmer/deermate/actions/runs/40175946902) |
| 真实 Codex 修复 | 临时仓库修复、独立执行一项测试通过，并收集 diff | [live smoke](../scripts/live_smoke.py)、[环境与结果说明](local-worker.md#verification) |
| 真实 Codex 生命周期 | 实际中断并继续同一 thread，三个 attempt 保留 native session ID | `live_smoke.py --live --model YOUR_AVAILABLE_MODEL --lifecycle` 的既有本地运行记录 |
| 待答表单与重启恢复 | 离线协议/进程测试通过 | [test_worker.py](../tests/test_worker.py)、[test_store.py](../tests/test_store.py) |

真实模型验证使用 macOS、Python 3.12、Codex `0.164.0-alpha.11.1` 和显式 `gpt-6.1-sol`。临时测试数据已清理，仓库没有保留原始会话或完整运行日志；现有说明和可复现脚本不等价于持久化原始测试收据。后续有真实兼容性需求时再运行 live 检查，避免无意义地重复消耗额度。

## 尚未实现或未充分验证

| 范围 | 状态与影响 |
| --- | --- |
| DeerFlow MCP 对接 | 未实现；当前不能声称已从 DeerFlow 派工 |
| SSH、NAT、中继和设备配对 | 未实现；M1 API 只能本地使用，没有远程 E2E 通道 |
| Claude、DSH、Qoder 等适配器 | 未实现；不能由上游有接口推断 DeerMate 已支持 |
| 多岗位路由、独立审核与 GitHub 自动维护 | 规划中 |
| 调研 watchlist、邮件、桌面控制、统一仪表盘 | 规划中；视频仍是模拟概念展示 |
| 进程硬崩溃与远程恢复 | 未完成 live 验证；现有重启测试不能替代跨机器容错证明 |
| 生产隔离、秘密脱敏、数据库加密、容量保留 | 尚不具备完整方案或实现；仅适用于可信项目的本地实验 |

## 交付操作与当前限制

M1 推送成功，源代码与 CI 结果可访问。此前创建 PR 时，GitHub 连接器返回写入权限不足，浏览器控制随后不可用，因此没有创建 PR；本次通过远端查询确认仍无开放 PR。

这只影响 PR 发布操作，不阻止继续开发，不应把它误记为运行代码故障。接续时如工具已恢复，应先检查是否已有 PR，避免重复创建。尚无合并或 release 的证据，不将其标成已发布。

## 下一步可直接执行的工作

1. **M2.1 / FR-012：DeerFlow MCP 接入。** 核对并记录兼容的上游版本；用 Python MCP 暴露 submit/status/cancel，将现有任务 ID、状态和结果映射为后台任务契约。先证明本地任务能被该契约跟踪，不同时引入 SSH。
2. **验收目标 AC-M2-01：** 提交快速返回稳定 ID；后续查询不依赖模型记住会话；任务完成、失败、待答与取消不误报；DeerFlow 重启后的句柄处理有明确行为和测试。
3. **M2.2 / FR-013：** 在接入契约成立后设计 SSH 主机身份、密钥生命周期、断线状态与撤权策略，再做远程实现；保持默认 Python 后端。

开始前按 [AGENTS.md](../AGENTS.md) 读取需求和实现，不将上述下一步当作已完成。一次只推进一个可验证的集成边界。

## 接续时更新什么

完成一个有意义的工作项后，更新此页的代码基线、交付状态、验证证据和下一步；在 [EVOLUTION.md](EVOLUTION.md) 追加结果。行为改变同步 spec，验收完成同步 roadmap，关键取舍补 ADR。常规文字修正不需要新增演进事件。
