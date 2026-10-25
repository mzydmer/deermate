# 项目演进记录

按事件追加项目的重要变化，保留当时的背景、选择、结果和证据。当前状态见 [STATUS.md](STATUS.md)，需求见 [SPEC.md](SPEC.md)。日期按项目记录日期，不把未来计划写成已经发生。

若历史记录有误，追加明确的修正及引用；不要悄悄将旧事件改写成当前结论。后续 commit 可以在合并时补上引用，但无需为了填写自身哈希反复提交。

## E-001 · 2026-10-25 · 项目定位与开源设计预览

- **背景：** 希望一个私人秘书能协调本地和云端 Agent，按职责派工，返回进展与产物。
- **结果：** 确定名称 DeerMate，建立公开仓库，提供中英文 README、架构、安全边界、接入契约、M0–M5 路线、贡献模板和概念视频。
- **交付：** [`9eb2079`](https://github.com/mzydmer/deermate/commit/9eb207939c4cabb0788001cf6424a948af3925b8)。此阶段交付文档与原创概念媒体，没有声称运行能力已经实现。
- **验证边界：** 视频使用模拟数据，不是 live 产品录屏；页面和媒体已检查。

## E-002 · 2026-10-25 · 选择 Python 自有后端

- **原因：** Hermesh 符合远程派工方向，但项目维护者希望后端使用 Python。
- **决定：** DeerMate 自有控制服务、Worker 和适配器使用 Python；计划用标准 SSH；Hermesh 保留为可选桥接，不移植或承诺兼容其底层协议。
- **依据：** [ADR 0001](decisions/0001-python-first.md)，随初始设计记录。
- **影响：** 需要独立完成会话、身份、恢复和远程安全设计，不能将 Hermesh 的能力算作默认方案已经具备。

## E-003 · 2026-10-25 · 建立首个实施目标

- **结果：** 创建 [Issue #1](https://github.com/mzydmer/deermate/issues/1)，定义 Python Worker 与 Codex 单任务生命周期的验收标准，并链接到 README 与 roadmap。
- **交付：** [`e9f228d`](https://github.com/mzydmer/deermate/commit/e9f228dbc443422490cb74c7f695bf24d3e9d360)。
- **影响：** 将大范围私人助手愿景拆为先证明本地任务，再扩展远程与秘书入口的顺序。

## E-004 · 2026-10-25 · M1 本地 Worker 与 Codex 适配

- **结果：** 实现 Python API/CLI、SQLite 任务、幂等提交、Codex 原生会话、worktree、补丁与独立验证记录、取消和继续、显式重启恢复，以及本地接纳边界。
- **关键选择：** 保存原生会话身份；不确定任务不自动重放；无验证或能力被拒绝时要求检查，不将模型文字当作验收证据。见 [ADR 0002](decisions/0002-durable-local-tasks.md)。
- **代码基线：** [`7dfe34a`](https://github.com/mzydmer/deermate/commit/7dfe34ac610a4f2ecd600ab77d28432786916b6a)，分支 `feat/m1-local-worker`。
- **验证：** 18 项离线测试、Ruff 与 wheel 构建通过；[GitHub CI](https://github.com/mzydmer/deermate/actions/runs/40175946902) 的 Ubuntu/macOS 两组通过。真实 Codex 完成临时修复、独立测试与 diff；真实中断和继续保留同一原生会话。
- **证据范围：** 本地 live 测试环境和结果记于 [local-worker.md](local-worker.md#verification)；临时原始记录未保存在仓库。远程、硬崩溃恢复、完整秘书和仪表盘不在本次验证范围。
- **交付状态：** 已推送开发分支；未合并主线、未发布包。PR 创建遇到连接器写权限与浏览器操作问题，不影响代码和既有 CI。

## E-005 · 2026-10-25 · 建立 Agent 接续与规格追踪

- **原因：** 已有 roadmap、架构和操作文档，但缺少统一的 Agent 入口、稳定需求编号、当前交付快照和演进记录。
- **结果：** 增加根目录 [AGENTS.md](../AGENTS.md)、[SPEC.md](SPEC.md)、[STATUS.md](STATUS.md)、本演进日志、决策索引、已有 M1 决策记录和[变更规格模板](specs/TEMPLATE.md)。README、贡献指南和 PR 模板提供接续入口。
- **范围：** 只补文档与协作规则；运行代码基线仍为 `7dfe34a`。本次文档提交是该事件的版本化交付记录。
- **验证：** 本次检查本地文档链接、规格编号与测试/源码映射，并核对远端主线和 PR 状态；不将旧测试或 CI 声称为本次重新运行。
- **下一步：** 优先推进 M2.1 的 DeerFlow 后台 MCP 契约，之后再做 SSH 远程边界。
