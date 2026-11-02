# 个人记忆 · M4.4a / M4.4b

状态：基础阶段已本地验收；明确记忆指令采集已实现并本地验收，2026-11-02。尚未升级既有本地实例或云端。完整目标见 [M4.4 spec](specs/m4-personal-memory-briefing.md)；本页描述个人事实存取、明确指令采集与召回，不代表语义提取、关注主题或今日简报已经完成。

## 使用流程

1. 登录后，在工作台打开“个人设置与记忆”。设置称呼和 IANA 时区，可直接使用设备时区。
2. 勾选“开启个人记忆”并保存。既有账号默认关闭，不自动导入聊天历史。
3. 在“告诉我需要记住什么”中保存简短偏好、目标或背景。当前保存到本人个人范围，可用于本人的其他对话。
4. 新对话的模型请求会带上预算内的相关事实；最多五条近期明确偏好优先选入，不要求问题出现相同关键词。文字块形式的聊天消息也支持召回。
5. 在列表中搜索、纠正或忘记。关闭记忆后停止个性化注入，已有事实仍可管理；添加新事实需先开启。

### 在对话里直接交代记忆

在同一区域另行勾选“从对话保存明确记忆”并保存，之后在普通对话发送：

> 请记住：我偏好简洁的中文回答。

这条偏好会自动出现在记忆列表，附“查看原对话”入口。也支持 `Remember: I prefer concise answers.`、明确的长期目标与学习背景。新开关默认关闭，关闭后已有记忆继续保留；关闭“个人记忆”同时停止采集和使用。

仅接纳“请记住：/记住：/Remember:/Remember that”开头、有 ID 的单条纯文本个人陈述。普通提问、引用/附件、带来源标签的建议、回放、项目约束、个人姓名/时区及含糊的更正不自动保存。修改既有偏好使用“纠正”，不让规则猜测要覆盖哪条事实。该路径不调用提取模型、也不扫描历史。

来源被删除、改写或变成不再支持的范围后，事实立即退出后续召回；一旦观察到失效便保留单向标记，删除编辑记录不会恢复旧偏好。管理页显示“来源已不可用”，可以“忘记并清理”。手动纠正后的事实由本人直接维护，不再依赖原对话。原模型已收到的内容不能追溯撤回。

本阶段不会让模型自行把一次提问或助手建议记成长期偏好。记忆不会改变 Go 角色、项目/Worker 授权，也不修改一个对话对应一个原生执行器会话的约束。

## 数据与边界

| 数据 | 主源 |
| --- | --- |
| 称呼、时区、记忆策略与版本 | Go 的 `deermate_personal_profiles` |
| 来源、范围、正文哈希、事实版本与状态 | Go 的 `deermate_memory_refs` |
| 确定性投递、短期正文信封、租约及回执 | Go 的 `deermate_memory_operations`；完成/失效后清除正文信封 |
| 采集来源与单向失效 | `deermate_memory_sources`：原对话/run/消息 ID、正文哈希、incarnation、策略/遗忘版本、观察/接纳/失效时间；不复制原消息正文 |
| 遗忘屏障 | Go 的 `deermate_memory_barriers`；保留 ID/版本，不保留已忘正文 |
| 记忆正文 | Gateway home 下 `personal-memory/users/<user>/agents/deermate-personal/facts/<shard>/<id>.md`，使用固定 DeerMem 文件事务 |
| 可重建检索索引 | 同一私有根下的 SQLite FTS5；复用 provider 的索引更新/重建机制 |

仅支持当前单实例、共享本地磁盘 SQLite 的 Go/Gateway 配置；Go、Gateway wheel 与前端需要按同一提交升级，不支持混合版本运行或带自动事实直接降级。使用真实用户身份，不接受浏览器选择 owner；管理入口也不提供读取其他账号记忆的参数。仅支持 `personal` 范围，未识别的项目范围拒绝写入并排除召回，不能退回全局桶。

内部 Python 适配器在短暂 SQLite 写入保留期间复核账号、策略和目标事实屏障，再提交 provider 文件事务；期间不调用模型。显式单事实投递只处理固定对象，另一个事实的遗忘不取消这个合法保存。明确指令采集另在实际运行接纳后核对规范消息、owner、普通 interactive origin、当前 incarnation 和项目范围；待提交候选还检查全局遗忘版本。未来的多事实语义提取仍需模型作业与批次契约。

相同操作 ID 返回原结果；投递回执丢失时根据确定事实 ID 和 provider 中的操作标记核对。Go 队列在重启后继续处理确定性存储投递，不重放模型、Native 命令或工具调用。关闭记忆会停止旧保存并清除其待投递正文；中断的记录可以“忘记并清理”。

纠正时暂时撤下旧事实；遗忘先建立读屏障，随即停止后续检索/注入，再清理 provider。列表读取校验正文哈希、来源标记和 revision；直接编辑 Markdown 不会被当成已授权的旧事实继续使用。请通过管理 API 修改，而不是手改事实文件。

共享用户摘要没有完整来源谱系前不参与注入。原始聊天、正在进行的上下文、Native 会话和备份分别管理；这里的遗忘不承诺清除它们或第三方模型已接收的数据。

## 检索与资源控制

- 最多 2,000 条未清理事实/用户；列表每页 50 条，搜索最多返回 10 条。
- 仅对已授权的事实 ID 做排名，复用 SQLite FTS5/BM25；中文使用同一上游 tokenizer，缺少可选 jieba 时采用其双字词法兜底。
- 索引更新是增量的；首次/失效后可重建。索引故障会明确失败，不回退扫描全部 Markdown。
- 显式偏好和命中事实合并后，用 DeerMem 格式化器按约 1,500 tokens 的网络无关估算选择；估算不代表模型实际 token 或账单。
- 明确指令采集每用户每天最多 50 条、实例每天最多 500 条（UTC 日）；达到上限不影响原聊天，不自动重发。来源和事实引用在同一事务中接纳，失败不留半条记录。
- 单实例一次投递一个存储操作；存取、明确指令采集和队列不发起额外模型请求。普通聊天仍使用已有模型配置及计费。
- 手动纠正也推进旧采集的版本屏障；不影响无关的显式单事实投递。
- 浏览器按 owner 隔离查询，离开页面清除未使用的记忆查询缓存；变更身份的请求被拒绝。搜索正文放在 POST 请求体中。

没有向量数据库、外部记忆服务、额外服务器或自动模型整理作业。当前不是语义 embedding 检索，不保证同义改写或单字中文的召回。2 GiB 主机压测与全量 M4.4 性能目标仍待验收。

## Go API

所有浏览器变更需要既有 Go 会话、绑定的 CSRF cookie/header，以及 `X-Expected-User-Id`。读取携带该身份预期头时也检查是否匹配，避免账号切换时缓存错归属。

| 接口 | 功能 |
| --- | --- |
| `GET/PATCH /api/me/personal-profile` | 称呼、时区、`memory_enabled` / `auto_capture_enabled`；PATCH 携带 `expected_revision` |
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

验证器运行真实 Go 登录/API → 固定 Gateway 插件 → DeerMem，并检查纠正、跨用户、关闭、双进程重启及遗忘。新增正常 run 接纳/来源用进程内 Fake 模型完成合成对话；Provider/实际 LangChain 图契约一并运行。Gateway 禁止外部连接，未配置真实供应方或 Worker；Fake 模型不代表真实供应方验收。

M4.4a 历史[基础收据](verification/personal-memory-2026-11-02.json)记录：15 项固定 Provider/真实 LangChain 图契约、21 项实际 Go→Gateway 存储检查、9 项真实浏览器检查通过。常规 Python 244 passed / 8 skipped；Go mod/vet/race/无 CGO 构建、Ruff/wheel、前端 TypeScript/生产构建、24 项固定 Chart/Compose/单机/HTTPS 契约通过。浏览器检查涵盖完整样式变量、手机/深色、关闭后管理和账号切换；独立四服务在 1472 MiB 合计容器限额下健康，不代表真实 2 GiB 主机负载能力。本轮没有云模型或 Native 调用。

浏览器复现使用 [`verify_memory_frontend.cjs`](../scripts/verify_memory_frontend.cjs)，环境变量与[前端指南](../frontend/README.md)一致；只能指向新建的独立本地合成验收环境。它会创建测试账号与个人记忆，不能指向已有私人实例。先按标准 overlay 构建完整前端；若复用相同 package/lock 的依赖缓存，也必须应用全部 `patches.json` 集成点，不能只覆盖新增组件。

M4.4b 的[采集收据](verification/explicit-memory-capture-2026-11-02.json)记录 **25 项固定存储/图/来源契约、33 项实际 Go→Gateway API、14 项真实浏览器检查通过**；普通 Python 244 passed / 8 skipped，Go mod/vet/race/无 CGO 构建、Ruff/wheel、TypeScript/生产构建与 24 项固定部署子集通过。新增验收覆盖旧 schema 升级、用户/实例配额、来源编辑/删除/换代、单向失效、手动纠正脱离旧来源、开关和原对话跳转。

完整浏览器复现需独立的合成 Fake 模型环境，并设置 `DEERMATE_CAPTURE_FIXTURE=1`；脚本先检查其模型名，不向真实供应方发送测试请求。另有 [`verify_memory_sdk.cjs`](../scripts/verify_memory_sdk.cjs)，沿用同样环境变量、要求既有合成账号开启明确采集，实际从输入框发送两轮消息；检查普通问答不入库、第二轮明确指令入库、流式成功与合成来源清理接纳。本轮两轮均通过。生产镜像没有加入 Fake 模型。容器限额检查与真实 2 GiB 主机压测仍分别记录，云端未升级。

## 尚待实施

语义提取与合并、项目级来源/权限、可选历史导入、关注主题、任务证据投影、今日简报、首页动作 intent/只读跟进/原任务续接，以及真实模型和 2 GiB 性能验收仍遵循完整 spec。本阶段不能标记 MEM-01–MEM-21 的全量验收完成。
