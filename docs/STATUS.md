# 当前开发状态与 Agent 接续

最后核对：2026-10-25。历史见 [EVOLUTION.md](EVOLUTION.md)。这是开发 Agent/维护者更新的版本化快照，不是自动监控服务。

## 当前交付

| 项目 | 当前事实 |
| --- | --- |
| 阶段 | M1 Worker、M2.1 MCP、M2.2 注册式直接 SSH、M2.3 完整 Gateway/SSH fixture 演示已实现；真实设备与秘书体验待完成 |
| 分支 | `feat/gateway-ssh-demo`，继承此前 Worker、桥接、Gateway 和 SSH 实现 |
| 产品运行代码 | 仍为 [`f7804ee`](https://github.com/mzydmer/deermate/commit/f7804eee9f45647222ef5a48e8d19d342a161d1b)；本次扩展验收工具、CI 和文档 |
| Gateway 验收工具 | [`728deb7`](https://github.com/mzydmer/deermate/commit/728deb7df1553f10c2d016b91607a615961d2b10) 新增 `--transport ssh`、`--replay`；收据脚本哈希 `aaa2934058d0…` |
| 主线/PR | 远端核对 `main` 仍为 `e9f228d`，无开放 PR；[比较分支](https://github.com/mzydmer/deermate/compare/main...feat/gateway-ssh-demo) |
| 发布 | 源码 alpha `0.1.0a1`；未合并主线、未发布 PyPI 或正式 release |
| 下一步 | 已注册真实设备上的受限账户/OpenSSH 部署验收；模型通知与聊天/UI 单独推进 |

运行代码与验收工具哈希不随纯文档提交改变；文档 HEAD 可以继续推进。接续时核对 Git 和远端状态。

## 已实现

- Python API/CLI、SQLite 持久任务/会话/事件、幂等与策略快照；Codex app-server、中断/同会话继续、表单、独立 worktree、diff 和管理员验证命令；时限、并发、显式恢复和 loopback 鉴权边界。
- 三个 stdio MCP 工具，Worker 独立运行。真实上游 Gateway/SQLite、原始 HTTP 查询/取消、后台轮询可通过本地 HTTP 或 SSH 使用同一 Worker。
- 管理员 SSH 注册包含显式 known_hosts、专用密钥/token、期限、预期实例及唯一 loopback 目的地。禁用默认配置/agent/认证回退，不执行 shell/SFTP。
- 每个 HTTP 操作重新检查授权、凭据和实例；到期/禁用/移除拒绝访问。凭据内容轮换重新认证，注册字段变化要求新进程；空闲隧道默认 60 秒过期，受正在执行的有限 HTTP 操作约束。
- 持久 Worker `instance_id`；远程 MCP 句柄为 `instance_id:task_id`。断线重建传输不自动重发修改请求；丢响应由相同幂等键显式恢复。撤权不代表已接纳的任务停止。
- M2.3 一条命令启动真实 Gateway → MCP → SSH → Worker，同一收据证明修复/验证失败、Gateway 重启、SSH-only 失联/重连、撤权/取消与 Worker 恢复；生成可离线回放的单文件 HTML。

使用：[本地](local-worker.md)、[DeerFlow](deerflow.md)、[SSH](ssh-worker.md)、[组合演示](demo.md)。设计：[SPEC](SPEC.md)、[M2.3](specs/m2-gateway-ssh-demo.md)、[ADR 0004](decisions/0004-ssh-loopback-transport.md)。

## 本次验证 · Gateway/SSH 组合

| 检查 | 实际结果 |
| --- | --- |
| 常规 `python -m pytest -q` | 74 passed、4 skipped，49.84 秒；跳过两种上游驱动及两种 Gateway opt-in 用例；一条已有 Starlette 弃用提示 |
| 实际 Gateway pytest | 2 passed，92.59 秒；完整固定上游后端，local/SSH 两种模式分别通过 14/21 项检查 |
| 保留证据 | [SSH 组合收据](verification/gateway-ssh-2026-10-25.json)、[回放 HTML](assets/gateway-ssh-demo.html)；最后一项检查 +44.779 秒，含源码/fixture/renderer 哈希、依赖、实例/任务/会话 ID 与 SSH 计数 |
| 回放页面 | 浏览器检查单步、10×播放和全部 21 项事件；无控制台警告/错误；已查看窄屏布局 |
| Ruff | `AGENTS.md` 所列检查通过，包含新增两个演示脚本 |
| wheel | `python -m build --wheel` 通过，仍为 `0.1.0a1` |
| 当前 CI | [40255200451](https://github.com/mzydmer/deermate/actions/runs/40255200451) 在 `728deb7` 完成并 success；两平台常规检查、实际上游驱动、local/SSH Gateway 共五个 job 均通过 |

环境：macOS/Python 3.12.14；控制端 AsyncSSH 2.24.1、cryptography 48.0.1；固定上游 `a1b89d0` 使用原始 lock，Gateway 环境 cryptography 50.0.0。凭据均临时生成，无真实模型、用户密钥、真实 SSH daemon 或系统配置修改。提交测试入口仅替代模型选工具；成功/失败验证经 Gateway 返回，原始 diff 由只读 Worker 观察连接取得。

收据与当前源码哈希已核对，HTML 嵌入同一收据。保留文件没有私密路径、密钥、token、原始日志或数据库。CI 仅上传有界 JSON/HTML。

已核对本次 artifact：`deerflow-gateway-local`（`12622301410`）、`deerflow-gateway-ssh`（`12621728883`）、`ssh-receipt-ubuntu-latest-py3.11`（`12621993322`）、`ssh-receipt-macos-latest-py3.12`（`12621764111`）。Gateway 两包各包含该模式的 JSON/HTML；artifact 元数据与上传步骤已核对。

## 历史证据与范围

- M2.2 [SSH 协议收据](verification/ssh-transport-2026-10-25.json)保留 22 项用例：身份、凭据、期限、撤权、轮换、丢响应和显式幂等恢复。固定上游驱动 local/SSH 两变体已通过。此前 [CI 40206131865](https://github.com/mzydmer/deermate/actions/runs/40206131865) 在 `96ca52b` 四组均 success，核对过两平台 SSH 和本地 Gateway 三个 artifact；不把旧 CI 扩展为本次新增验收工具证据。
- [旧 Gateway 收据](verification/deerflow-gateway-2026-10-25.json)属于原本地路径及旧源码，14 项检查；[CI 40201412129](https://github.com/mzydmer/deermate/actions/runs/40201412129) 四组通过。
- M1 `7dfe34a` 的 [CI 40175946902](https://github.com/mzydmer/deermate/actions/runs/40175946902) 两组通过。既有真实 Codex 验证使用 `0.164.0-alpha.11.1` / `gpt-6.1-sol`，完成修复、独立测试、diff 和同原生会话中断/继续。方法见 [local-worker.md](local-worker.md#verification)；原始临时日志未保留，本轮未重复调用模型。

## 未完成或未证明

| 范围 | 边界 |
| --- | --- |
| 真实双机/OpenSSH 账户 | 未部署验收；当前是同机真实 SSH 协议 fixture，未修改用户主机或账户 |
| NAT、反向隧道、设备配对、自动密钥注册、中继 | 未实现；现有传输要求直接可达 SSH 端点 |
| 模型通知、产品聊天/UI | 未验证；空模型 Gateway 的通知 run 在模型装配阶段失败，HTTP/SQL 验收与事件回放不证明完整秘书体验 |
| 表单/review/recovery 秘书入口 | 三个 MCP 工具不自动回答、审批或恢复；现有 CLI 可在授权内处理 |
| 多岗位路由、Claude/DSH/Qoder、GitHub 维护、调研/邮件/桌面 | 后续阶段 |
| 硬崩溃/孤儿进程、历史库升级、生产隔离/脱敏/加密/总配额 | 尚无完整实现或验收，不由有序重启和 fixture 推断 |

删除服务端公钥不会自动断开已认证会话；立即撤权还需终止对应会话。已接纳任务按 Worker 策略继续，需要停止时使用仍有效的本地权限。见 [SSH 撤权说明](ssh-worker.md)。

此前 PR 创建遇到连接器写权限与浏览器限制；当前没有开放 PR，代码保存在开发分支，未声称合并或发布。

## 下一项工作

1. 对明确注册的真实设备验收受限 OS/OpenSSH 策略、网络可达性与服务重启；不扫描或登录未注册主机。
2. 配置模型后单独验证通知和聊天入口；保留任务身份、取消确认和外部输入权限边界。
3. NAT/反向连接独立设计，再扩展专职 Agent 路由与工作台。

按 [AGENTS.md](../AGENTS.md) 接续；行为变化更新 spec，有意义结果追加 EVOLUTION，当前状态维护于此。
