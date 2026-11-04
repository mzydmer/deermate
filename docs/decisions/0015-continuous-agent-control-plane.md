# ADR 0015 · Router/Worker 双层与 Go 持续工作控制

Date: 2026-11-03. **Status: Accepted，2026-11-03 用户批准按 spec/plan 开发；实现进行中。**

## Context

私人秘书需要持续接收项目变化、关联历史工作、安排执行并在需要时提醒用户。现有实现已有 Go 公开入口、个人关注/简报、原生会话 journal、Worker ordinary driver，以及用户管理的设备授权和主动 HTTPS relay。将外部事件直接交给一个通用聊天会话，不能表达事件去重、权限依据、积压、恢复和跨任务归属。

本设计基于 [M4.5 spec](../specs/m4-continuous-agent.md) 和[实施 plan](../specs/m4-continuous-agent-plan.md)，借鉴 DSH 的事件/工单/执行分层及观察模式，保留 DeerMate 的语言、权限和会话约束。

## Decision

1. Go 唯一拥有 SourceEvent、RouterInbox、Decision、WorkOrder、Subscription、投递 effect 和预算接纳，复用现有本地 SQLite；一个控制实例。
2. 固定 DeerFlow 承载每 owner 一个持久 Router Session，负责接待、全局上下文、工作路由和统一回复。Router 的工具集由 host 限制，没有 shell/Native 执行原语；需要规则研判时异步启动无工具 Assessor，结果以事件回到 Router。新的内部窄适配器执行规范 operation，不另造 Python scheduler，不把开发验证器变成生产入口。
3. 原 Native journal、ordinary driver、授权 relay 和 Worker 继续拥有其权威状态。Go 只记录引用、投递阶段和产品投影，不把模型报告当执行证据。
4. 原生执行维持一执行对话 incarnation 一个固定会话；总秘书可聚合多件工作，新项目/执行器创建新的执行对话。
5. 来源默认未启用，规则默认 observe；auto 需要显式范围和额度。外部事件是输入，不能授予设备或外部发布权限。
6. 召回从本人范围的明确引用和有界分页开始，关键词搜索作为入口；个人事实正文继续由 DeerMem 管理。没有新的向量库、图数据库、消息集群或常驻模型监督服务。
7. 先落库再投递；可能已发送的副作用只核对原 operation，不因重启、断线或模型推断而重放。
8. 已关联 Thread 的范围内消息经 Go 检查后直通原任务 Worker；越范围时结构化 handoff 给 Router。Worker 是实际 Codex 原生会话，Python Worker 是设备执行管理服务。Router 派发后不等待或轮询，独立处理后续消息；V1 Native 并发 1 不使主会话与执行串行绑定。

## Alternatives

| 方案 | 取舍 |
| --- | --- |
| 直接替换为 DSH TypeScript 插件 | 与 Go 控制端及已有 DeerFlow/Worker 状态不一致，增加第二套权限/会话主源 |
| 所有事项共享一条巨型对话 | 上下文和原生绑定互相污染，执行与交互容易争用 |
| 新增独立 Python 编排服务 | 形成第二个工作账本/调度所有者，故障时难以确定实际任务身份 |
| 第一阶段引入 Kafka/Redis/向量库 | 超出单 owner、低成本单机的当前需要；索引与有界事务先满足 V1 |
| 一开始自动修复并创建/合并 PR | 将第三方写权限和模型质量评估混在首轮迁移中，难以审计范围和回退 |

## Consequences

需要新增 Go 工作/事件状态和明确的运行时版本契约；内部查询必须能核对原接纳结果。多个状态主源通过稳定 ID 关联，不能靠跨数据库事务假装实现 exactly-once。外部服务的未知结果仍可能需要人工核对。

原普通聊天、首页动作和历史任务兼容；M4.4 的语义提取、其他执行器、外部写入及多租户不因本 ADR 获得实现状态。ADR 0007、0012–0014 保持有效，本提案不取代或扩大原授权。

用户已批准本设计。实施、验收和发布状态分别记录，不以设计接受等同上线。

## 2026-11-04 · 实现细化

Go 使用版本化 envelope 和独立唯一键/预算表实现账本，Python 只做窄适配。关键词召回按最近索引顺序返回最多 20 个 MATCH，避免高频词对全历史评分；合成 11,000 记录下曾测得评分搜索 p95 505 ms，调整后约 85 ms。该结果仅为本地容器 API 测量，不代表 Router 对照实验或真实 2 GiB 云主机性能。
