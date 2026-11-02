# 个人记忆基础 · M4.4a

状态：基础阶段已实现并通过本地验收，2026-11-02；尚未升级现有本地实例或云端。完整产品目标见 [M4.4 spec](specs/m4-personal-memory-briefing.md)；本页只描述显式个人事实的存取与召回，不代表自动提取、关注主题或今日简报已经完成。

## 使用流程

1. 登录后，在工作台打开“个人设置与记忆”。设置称呼和 IANA 时区，可直接使用设备时区。
2. 勾选“开启个人记忆”并保存。既有账号默认关闭，不自动导入聊天历史。
3. 在“告诉我需要记住什么”中保存简短偏好、目标或背景。当前保存到本人个人范围，可用于本人的其他对话。
4. 新对话的模型请求会带上预算内的相关事实；最多五条近期明确偏好优先选入，不要求问题出现相同关键词。文字块形式的聊天消息也支持召回。
5. 在列表中搜索、纠正或忘记。关闭记忆后停止个性化注入，已有事实仍可管理；添加新事实需先开启。

本阶段不会让模型自行把一次提问或助手建议记成长期偏好。记忆不会改变 Go 角色、项目/Worker 授权，也不修改一个对话对应一个原生执行器会话的约束。

## 数据与边界

| 数据 | 主源 |
| --- | --- |
| 称呼、时区、记忆策略与版本 | Go 的 `deermate_personal_profiles` |
| 来源、范围、正文哈希、事实版本与状态 | Go 的 `deermate_memory_refs` |
| 确定性投递、短期正文信封、租约及回执 | Go 的 `deermate_memory_operations`；完成/失效后清除正文信封 |
| 遗忘屏障 | Go 的 `deermate_memory_barriers`；保留 ID/版本，不保留已忘正文 |
| 记忆正文 | Gateway home 下 `personal-memory/users/<user>/agents/deermate-personal/facts/<shard>/<id>.md`，使用固定 DeerMem 文件事务 |
| 可重建检索索引 | 同一私有根下的 SQLite FTS5；复用 provider 的索引更新/重建机制 |

仅支持当前单实例、共享本地磁盘 SQLite 的 Go/Gateway 配置。使用真实用户身份，不接受浏览器选择 owner；管理入口也不提供读取其他账号记忆的参数。仅支持 `personal` 范围，未识别的项目范围拒绝写入并排除召回，不能退回全局桶。

内部 Python 适配器在短暂 SQLite 写入保留期间复核账号、策略和目标事实屏障，再提交 provider 文件事务；期间不调用模型。显式单事实投递只处理固定对象，另一个事实的遗忘不取消这个合法保存。未来的多事实自动提取还需要完整来源/删除版本契约。

相同操作 ID 返回原结果；投递回执丢失时根据确定事实 ID 和 provider 中的操作标记核对。Go 队列在重启后继续处理确定性存储投递，不重放模型、Native 命令或工具调用。关闭记忆会停止旧保存并清除其待投递正文；中断的记录可以“忘记并清理”。

纠正时暂时撤下旧事实；遗忘先建立读屏障，随即停止后续检索/注入，再清理 provider。列表读取校验正文哈希、来源标记和 revision；直接编辑 Markdown 不会被当成已授权的旧事实继续使用。请通过管理 API 修改，而不是手改事实文件。

共享用户摘要没有完整来源谱系前不参与注入。原始聊天、正在进行的上下文、Native 会话和备份分别管理；这里的遗忘不承诺清除它们或第三方模型已接收的数据。

## 检索与资源控制

- 最多 2,000 条未清理事实/用户；列表每页 50 条，搜索最多返回 10 条。
- 仅对已授权的事实 ID 做排名，复用 SQLite FTS5/BM25；中文使用同一上游 tokenizer，缺少可选 jieba 时采用其双字词法兜底。
- 索引更新是增量的；首次/失效后可重建。索引故障会明确失败，不回退扫描全部 Markdown。
- 显式偏好和命中事实合并后，用 DeerMem 格式化器按约 1,500 tokens 的网络无关估算选择；估算不代表模型实际 token 或账单。
- 单实例一次投递一个存储操作；存取和队列不发起额外模型请求。普通聊天仍使用已有模型配置及计费。
- 浏览器按 owner 隔离查询，离开页面清除未使用的记忆查询缓存；变更身份的请求被拒绝。搜索正文放在 POST 请求体中。

没有向量数据库、外部记忆服务、额外服务器或自动模型整理作业。当前不是语义 embedding 检索，不保证同义改写或单字中文的召回。2 GiB 主机压测与全量 M4.4 性能目标仍待验收。

## Go API

所有浏览器变更需要既有 Go 会话、绑定的 CSRF cookie/header，以及 `X-Expected-User-Id`。读取携带该身份预期头时也检查是否匹配，避免账号切换时缓存错归属。

| 接口 | 功能 |
| --- | --- |
| `GET/PATCH /api/me/personal-profile` | 称呼、时区和个人记忆设置；PATCH 携带 `expected_revision` |
| `GET /api/me/memories?offset=0` | 本人列表、引用及总数 |
| `POST /api/me/memories/search` | 请求体 `{query, offset}`，不把搜索正文放到 URL |
| `POST /api/me/memories` | `{operation_id, content, category, expected_revision: 0}` |
| `PATCH /api/me/memories/{id}` | 同上，使用列表返回的 revision |
| `DELETE /api/me/memories/{id}` | `{operation_id, expected_revision}`；先抑制后清理 |
| `GET /api/me/memory-operations/{id}` | 查看原操作的 pending/processing/uncertain/completed/invalidated 状态 |

`operation_id` 由客户端生成并在网络重试时复用；不能复用同一 ID 发送另一份正文。写入返回 HTTP 202 和原操作引用，是否完成以状态为准。类别为 `preference`、`goal`、`context`；API 正文上限 4,000 UTF-8 字节，界面限制为 1,000 个输入字符。已知认证材料格式被拒绝，不保证识别任意文本中的秘密。

`proactive_enabled` 尚无生成器，尝试开启会返回 501；不会保存一个看似已经开始工作的开关。旧 `/api/memory` 及原始插件动作不能绕过 Go 的个人入口。本阶段不增加执行能力，普通账号仍不能调用原有 Native 执行接口。

## 验证方式

常规 Go 检查按 [AGENTS](../AGENTS.md) 执行。完整存储契约使用固定上游解释器，复用开发环境的 pytest，不修改其冻结依赖：

```bash
mkdir -p .deermate/verification
go -C backend build -o ../.deermate/verification/memory-control ./cmd/deermate
python scripts/verify_personal_memory.py \
  --checkout .deermate/verification/deer-flow \
  --gateway-python .deermate/verification/deer-flow/backend/.venv/bin/python \
  --control-binary .deermate/verification/memory-control \
  --work-dir .deermate/verification/memory-http-new \
  --receipt .deermate/verification/personal-memory.json
```

先按 [DeerFlow 指南](deerflow.md)准备固定 checkout/冻结环境，安装本项目 `.[dev]`，并使用当前源码重新构建 Go binary。工作目录必须是新目录；失败后保留原目录用于核对，不用同一验收目录重放。收据绑定 Go binary 与源文件哈希，测试只使用合成资料。

验证器运行真实 Go 登录/API → 固定 Gateway 插件 → DeerMem，并检查纠正、跨用户、关闭、双进程重启及遗忘。Provider/实际 LangChain 图的离线契约一并运行；Fake 模型不代表真实供应方验收。Gateway 禁止外部连接，未配置云模型和 Worker。

本轮[脱敏收据](verification/personal-memory-2026-11-02.json)记录：15 项固定 Provider/真实 LangChain 图契约、21 项实际 Go→Gateway 存储检查、9 项真实浏览器检查通过。常规 Python 244 passed / 8 skipped；Go mod/vet/race/无 CGO 构建、Ruff/wheel、前端 TypeScript/生产构建、24 项固定 Chart/Compose/单机/HTTPS 契约通过。浏览器检查涵盖完整样式变量、手机/深色、关闭后管理和账号切换；独立四服务在 1472 MiB 合计容器限额下健康，不代表真实 2 GiB 主机负载能力。本轮没有云模型或 Native 调用。

浏览器复现使用 [`verify_memory_frontend.cjs`](../scripts/verify_memory_frontend.cjs)，环境变量与[前端指南](../frontend/README.md)一致；只能指向新建的独立本地合成验收环境。它会创建测试账号与个人记忆，不能指向已有私人实例。先按标准 overlay 构建完整前端；若复用相同 package/lock 的依赖缓存，也必须应用全部 `patches.json` 集成点，不能只覆盖新增组件。

## 尚待实施

自动提取与合并、项目级来源/权限、可选历史导入、关注主题、任务证据投影、今日简报、首页动作 intent/只读跟进/原任务续接，以及真实模型和 2 GiB 性能验收仍遵循完整 spec。本阶段不能标记 MEM-01–MEM-21 的全量验收完成。
