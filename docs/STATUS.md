# 当前开发状态与 Agent 接续

最后核对：2026-10-25。历史见 [EVOLUTION.md](EVOLUTION.md)。这是开发 Agent/维护者更新的版本化快照，不是自动监控服务。

## 当前交付

| 项目 | 当前事实 |
| --- | --- |
| 阶段 | M1 Worker、M2.1 MCP、M2.2 注册式直接 SSH 已实现；实际设备部署与完整秘书体验未完成 |
| 分支 | `feat/m2-ssh-worker`，继承此前 Worker、桥接、Gateway 验收与文档 |
| 当前运行代码 | [`f7804ee`](https://github.com/mzydmer/deermate/commit/f7804eee9f45647222ef5a48e8d19d342a161d1b) |
| Gateway 验收工具 | [`14b0d8d`](https://github.com/mzydmer/deermate/commit/14b0d8da17e1978c10a80e7e997aa3f5d962aeb7)，当前 CI 将回归此脚本 |
| 主线/PR | 本次远端核对 `main` 仍为 `e9f228d`，无开放 PR；[比较分支](https://github.com/mzydmer/deermate/compare/main...feat/m2-ssh-worker) |
| 发布 | 源码 alpha `0.1.0a1`；未合并主线、未发布 PyPI 或正式 release |
| 下一步 | 完整 Gateway 经 SSH 的演示/验收与实际受限设备部署；NAT、模型通知/UI 单独推进 |

运行代码哈希不随纯文档提交改变；文档 HEAD 可以继续推进。接续时核对 Git 和远端状态。

## 已实现

- Python API/CLI、SQLite 任务/会话/事件、幂等与策略快照；Codex app-server、中断/同会话继续、表单、独立 worktree、diff 和管理员验证命令；时限、并发、显式恢复和 loopback 鉴权边界。
- 三个 stdio MCP 工具；独立 Worker 不依赖 MCP 进程。真实上游 Gateway/SQLite 本地路径已完成有序进程重启、原始 HTTP 查询/取消和 Worker 失联恢复 fixture 验收。
- 新增 SQLite `instance_id`，稳定于服务重启/备份，旧数据库可添加 metadata；损坏身份拒绝启动。capabilities 是兼容的新增字段。
- `--worker home` 选择管理员注册的 SSH 目标；CLI 原有命令和 MCP 均可使用。目标、端口、信任、专用密钥、token、期限与预期实例来自配置，不能由工具参数指定。
- 显式主机密钥校验，禁用默认 SSH 配置/agent/认证回退；只转发既有 API 到远端 loopback，不执行 shell/SFTP。
- 每个 HTTP 操作重新检查授权、凭据和实例。到期/禁用/移除拒绝访问；凭据内容轮换重新认证；注册字段变化要求重启连接进程。空闲隧道定时过期，默认 60 秒，受正在执行的有限 HTTP 操作约束。
- 远程 MCP 句柄绑定 `instance_id:task_id`。断线可重建传输，但不自动重发修改请求；接纳后丢响应通过相同幂等键显式恢复。撤权不误报已接纳任务停止。

使用：[本地](local-worker.md)、[DeerFlow](deerflow.md)、[SSH](ssh-worker.md)。设计：[基础规格](SPEC.md)、[M2.2](specs/m2-ssh-worker.md)、[ADR 0004](decisions/0004-ssh-loopback-transport.md)。

## 本次验证 · SSH

| 检查 | 实际结果 |
| --- | --- |
| `python -m pytest -q` | 74 passed、3 skipped；跳过两种上游驱动变体及完整 Gateway opt-in 检查；一条已有 Starlette TestClient 弃用提示 |
| `python -m pytest -q tests/test_ssh.py --ssh-receipt <file>` | 22 passed，24.82 秒；[保存的收据](verification/ssh-transport-2026-10-25.json)含源码/fixture/reporter 哈希、版本和有界测试结果 |
| `DEERMATE_DEERFLOW_CHECKOUT=<pinned checkout> python -m pytest -q tests/test_deerflow_compat.py` | 2 passed，8.65 秒；实际固定上游驱动，经真实 MCP 使用 local/SSH 两种绑定 |
| Ruff | `ruff check src tests scripts/live_smoke.py scripts/verify_deerflow_gateway.py` 通过 |
| 包与依赖 | wheel 构建通过；`pip check` 无依赖冲突；包仍为 `0.1.0a1` |
| 本次 CI | 配置为两个常规平台上传 SSH 收据、固定驱动运行两种模式及实际 Gateway 回归；等待远端结果实际核对，不能预先标通过 |

本地环境：macOS/Python 3.12、AsyncSSH 2.24.1、bcrypt 5.0.0、cryptography 48.0.1、MCP 1.30.0。22 项 SSH 用例使用临时生成的密钥、真实协议服务器、HTTP Worker 和离线原生 fixture；没有使用真实 SSH daemon、用户 SSH 密钥、模型或系统配置。

本次源代码与收据哈希已核对。CI 的 SSH artifact 只在成功会话后产生，不包含私密路径、密钥、token、地址、原始日志或数据库。

## 历史证据与范围

- [Gateway 收据](verification/deerflow-gateway-2026-10-25.json)属于此前源码版本：14 项实际应用/SQLite/后台服务检查，使用测试提交入口代替模型选工具。[CI 40201412129](https://github.com/mzydmer/deermate/actions/runs/40201412129) 在 `28d6cc5` 的两个平台、原生驱动和 Gateway 四组均通过，并保留 artifact `12601528420`。该旧收据不追溯验证新增 SSH 源码；当前 CI 会回归 Gateway。
- 早期桥接 [CI 40180093367](https://github.com/mzydmer/deermate/actions/runs/40180093367) 三组通过；运行基线为 `2a941b1`。
- M1 基线 `7dfe34a` 的 [CI 40175946902](https://github.com/mzydmer/deermate/actions/runs/40175946902) 两组通过。既有真实 Codex 验证使用 `0.164.0-alpha.11.1` 和显式 `gpt-6.1-sol`，完成修复、独立一项测试、diff，以及同一原生会话的中断/继续。环境与复现见 [local-worker.md](local-worker.md#verification)；原始临时日志未保留，本轮未重复调用模型。

## 未完成或未证明

| 范围 | 边界 |
| --- | --- |
| 真实双机/OpenSSH 账户 | 未部署验收；当前是真实 SSH 协议的同机网络 fixture，部署模板未修改或认证用户主机 |
| Gateway 通过 SSH 的完整演示 | 当前 Gateway 回归为本地路径，上游驱动另有 SSH 模式；尚未把两者合为同一演示收据 |
| NAT、反向隧道、设备配对、自动密钥注册、中继 | 未实现；先支持直接可达 SSH 端点 |
| 模型通知、聊天/UI | 未验证；空模型 Gateway 中通知 run 会在模型装配阶段失败，不能把 HTTP/SQL 结果验收称为完整秘书体验 |
| 表单/review/recovery 秘书入口 | 三个 MCP 工具不自动回答、审批或恢复；现有 CLI 可在授权内处理 |
| 多岗位路由、Claude/DSH/Qoder、GitHub 维护、调研/邮件/桌面 | 后续阶段 |
| 硬崩溃/孤儿进程、历史数据库升级、生产隔离/脱敏/加密/总配额 | 尚无完整实现或验收，不由有序重启和 fixture 测试推断 |

删除服务端公钥不会自动断开已认证 SSH 会话。立即服务端撤权还需终止对应会话；控制端有期限/配置检查和有限连接寿命。已接纳的排队/执行任务按 Worker 策略继续，管理员需要停止时使用仍有效的本地权限。详见 [SSH 撤权说明](ssh-worker.md)。

此前创建 PR 遇到连接器写权限与浏览器操作限制；当前工作继续保存在 Git 分支，没有声称已创建 PR、合并或发布。工具恢复后先核对已有 PR。

## 下一项工作

1. 在隔离环境把实际 Gateway 验收脚本接到生成密钥的 SSH 服务器，形成 Gateway → MCP → SSH → Worker 的单条演示/收据，继续使用离线原生 fixture。
2. 再在明确注册的真实设备上验收受限 OS/OpenSSH 策略与网络可达性；不要扫描或自动登录未注册主机。NAT/反向连接需要独立规格。
3. 模型通知与浏览器体验需要单独模型/用户环境验收；原有 API 与任务身份边界不扩大。

按 [AGENTS.md](../AGENTS.md) 接续；行为变化更新 spec，有意义结果追加 EVOLUTION，当前状态维护于此，避免把历史证据冒充新检查。
