# DeerMate README v3：以架构叙事建立技术品牌

状态：视觉方案与设计稿阶段，2026-11-10。基线 main `9ed993a`。用户明确要求突出科技感、架构特点与技术理念，保留原来概念片的叙事方式，并由专门的 UI 设计子 Agent 完成视觉设计。

## 1. 设计目标

第一次打开仓库，要先感受到「这是一个把 Agent 连成系统的技术项目」，再理解它怎么使用。主线改为 **意图进入 → 受控路由 → 持续执行 → 记忆关联 → 证据返回**。UI 操作录屏作为二级资料，不再担任主视觉或主视频。

英文主定位：**The control plane for your personal agents.**

中文主定位：**把 Agent 连成系统，把控制权留在你手里。**

辅助文案：**One conversation. Persistent sessions. Work you can verify.**

主视觉同时表现四件事：Router 正在协调；Go 在接纳边界检查；Worker 在自己的设备上持续工作；记忆与证据让前后轮次连起来。不要用一个普通后台截图来承担整个项目的技术定位。

## 2. 必须被看见的技术特点

| 特点 | 对外表达 | 图像语言 | 可核对依据 |
| --- | --- | --- | --- |
| Router / Worker 分工 | 秘书持续响应，长任务由独立会话执行 | 两条并行流：沟通主线与执行分支，完成后回到同一事件账本 | [持续 Agent spec](../specs/m4-continuous-agent.md) |
| Go 控制面 | 路由提议经过身份、范围、预算和操作身份接纳 | 控制核心与边界环，明确标注 admission / scope / budget / op-id | [Go 架构](../architecture.md)、[安全](../security.md) |
| 跨设备执行 | 云端协调，自己的设备执行；原生凭据留在执行端 | Cloud control 与 Your machine 两个空间，经授权 HTTPS/SSH 链路相连 | [设备授权](../agent-authorizations.md) |
| 原生会话连续性 | 同一话题保持同一原生根，断线后核对原操作 | 一条贯穿多轮的 session ribbon，断线时保留标记，恢复时接回原根 | [会话绑定](../specs/m2-chat-session-binding.md) |
| 来源约束的记忆 | 私人事实可追溯、有范围、可纠正和遗忘 | Source → Fact → Context 的有向图，删除与策略屏障切断后续读取 | [记忆方案](../product/technical/memory.md) |
| 可验证的工作 | 执行、独立验证与不确定结果分别记录 | diff / validation receipt / source 形成独立证据包，不以模型成功文案替代 | [结果指南](../product/guide/conversations.md) |

研究价值体现在机制、系统不变量和可复现实验入口；不把尚未完成的对照研究写成性能或质量优势。明确承认 DSH Super-agent 对 Router/Worker 思路的启发，突出 DeerMate 在个人设备、Go 接纳、会话连续性与证据边界上的具体实现。

## 3. 推荐视觉方向

**深色控制空间 + 发光信号路径 + 有层次的架构核心。**

- 黑色/深灰作为空间，白色大标题，蓝青表示请求与传输，紫色表示上下文与记忆。使用 design.md 的品牌色与渐变；不要回到旧版绿色配色。
- 主画面是一个有空间层次的系统拓扑：中央 Router/Go 接纳核心、侧向设备与 Worker、底部会话/记忆/证据轨道。允许透视、细网格、受控光晕和材质层次，但每条线都应服务于技术含义。
- 不采用大面积普通后台卡片，也不依靠机器人头像、脑形图标、随机代码雨或无意义数字制造科技感。
- DeerMate 现有单色鹿标保留。大标题使用营销配方；等宽字体用于组件、身份和协议标签。字体从本地栈回退，不外链加载或声称已经加载 Geist。
- README 媒体属于营销图像；产品工作台继续沿用现有紧凑中性界面，两者不能混为一套页面设计。
- 大图按 2× 导出，GitHub 约 900px 内容宽度下检查主要标签。文字说明必须在 Markdown 中保留，不能全部埋进图片。

## 4. README 的内容顺序

| 顺序 | 模块 | 表达方式 |
| --- | --- | --- |
| 1 | 品牌 Hero | DeerMate 标志、主定位、系统拓扑主视觉、MIT / Alpha / Self-hosted 三个简洁标识 |
| 2 | 架构概念片 | 16:9 封面与短 GIF；主视频讲技术叙事，标题建议 **From intent to evidence** |
| 3 | 四个设计原则 | Persistent routing / Native continuity / Scoped authority / Traceable memory，短文案配同语言的小图 |
| 4 | 系统架构 | 完整控制面、运行时、设备、Worker、记忆与证据流；解释 Router 与 Go 的职责差别 |
| 5 | 为什么值得研究 | 问题 → 机制 → 评估入口，三行即可；链接 spec / plan / receipts |
| 6 | 接入与当前范围 | 当前可用与规划扩展分开呈现，避免生态 Logo 墙暗示已经全部接入 |
| 7 | Quick start / Docs / Contribute | 保留能运行的短入口，详细安装、历史状态和验收数字放到专门文档 |

不恢复过时的 M0–M5 流水、Python-only 叙述或大量中间测试数字。保留原版「概念展示项目方向」的方式，用当前架构与更成熟的视觉重新制作。

## 5. 架构图的语义合同

主链应看见：

```text
User intent → Go admission ↔ DeerFlow Router
                      ↓ admitted work through runtime/relay
              authorized device → Python Worker → Codex native session
                      ↑ events, results, independent evidence

Go owns policy / identity / budgets / durable records
DeerMem owns personal fact files and FTS5 through the internal runtime
```

- Router 提出类型化路由，不绕开 Go 直接获得机器权限。
- 已关联事件可经 Go 校验后直通原 Worker，不把所有事件都画成必须再次询问 Router。
- 个人记忆和工作证据分开；不是所有任务结果都会自动成为长期个人事实。
- 「一个话题 → 一个原生根」不要画成全系统只有一个 Native 会话。
- HTTPS / SSH 代表传输链路，不代表云端无法解密的端到端加密。
- 当前主要执行器是 Codex。Claude / ACP、DeepSeek Harness、Hermesh 等扩展只能在规划区域使用虚线及文字标注。

## 6. 主视频方案：36 秒架构概念片

| 时间 | 画面与运动 | 主文案 | 技术含义 |
| --- | --- | --- | --- |
| 00–04s | 深色空间中信号汇聚为鹿标与控制核心，标题从结构线中出现 | **DeerMate. One system for your agents.** | 建立项目品牌 |
| 04–10s | 单个意图进入 Router，经 Go 的范围/预算/操作身份边界 | **Route intent. Keep authority explicit.** | 提议与接纳分离 |
| 10–16s | 画面分为两条同时运动的轨道：Router 接待新请求，Worker 推进已有任务 | **The secretary stays present. Workers keep going.** | 协调与执行异步分工 |
| 16–22s | 信号跨过云端与本机边界，落入带 session ribbon 的 Codex 执行空间；中断后接回同一标记 | **Same topic. Same native root.** | 跨设备与会话连续性 |
| 22–28s | 来源节点进入记忆图，经范围边界进入上下文；纠正/遗忘让旧路径退出 | **Context with a source. Memory with control.** | 来源、范围和删除屏障 |
| 28–34s | diff、独立验证记录与引用汇合为证据包，执行与验证两条状态保持独立 | **Bring back evidence.** | 结果可检查，未知被保留 |
| 34–36s | 收束为鹿标、仓库地址和简洁技术栈 | **Your agents. Your machines. Your control.** | 收束品牌与行动入口 |

这是架构演绎，不是假装执行过一次任务；片中仅使用示意身份与协议对象。小字标注 **Architecture concept · Illustrative flow**。不编造测试通过数、实时运行日志、性能收益或已完成的规划接入。

动效应有因果：路由用信号分叉，权限用穿越边界，会话用持续轨道，记忆用图的变化，证据用对象汇合。不要用一套淡入淡出覆盖所有内容。GitHub 缩略动效控制为 5–8 秒，不抢正文阅读；主片默认静音，完整版本可暂停和重播。

## 7. 本轮 UI 设计师交付

由专门的 UI 设计子 Agent 完成：

1. 可打开的视觉方案页 `readme-tech-v3-review.html`，包括完整首屏、架构模块、视觉原则与视频分镜。
2. 主视觉、架构图与分镜的代码原稿，保存在 `assets/readme-tech-v3/`；优先 SVG/HTML，便于准确维护技术结构。
3. 可供导出的 Hero / Architecture / Storyboard 三张视觉稿；主 Agent 负责浏览器导出、目视复核和技术语义检查。
4. 若制作动态小样，必须有播放/暂停及减少动态支持，并提供静态帧；不以未实现的交互替代 GitHub 能力。

本轮已形成方案、高保真视觉稿和可播放的 36 秒概念片小样，另附 GitHub 可用的 6 秒 GIF。主 README 尚未替换；后续正式接入时，操作录屏移到补充材料。

## 8. 可交付与检查标准

- 能在五秒内看出「受控的 Agent 协作系统」，而非普通聊天机器人或后台模板。
- 一眼区分 Router、Go 控制边界和 Native Worker；读者能沿信号线理解一条请求与一条结果。
- 当前能力与规划扩展有文字区分；不新增 E2E、通用无人值守或研究收益声明。
- 1440px 方案页、390px 手机方案页均可读；图中文字在 README 宽度下不依赖放大才能理解主结构。
- 静态 PNG/SVG 与 GIF/MP4 是 GitHub 可用的最终载体。预览页的 CSS/JS 不被当作 README 的运行能力。
- 无外链字体、无私人数据与密钥、无新增模型/Native 调用；不修改产品运行代码或部署。

## 9. 本轮交付入口

| 交付 | 入口 |
| --- | --- |
| 完整高保真方案页、可交互概念片和六格分镜 | [打开设计预览](readme-tech-v3-review.html) |
| 正式 README 的内容层级与文案骨架 | [README v3 骨架](readme-tech-v3-outline.md) |
| 架构品牌主视觉 | [PNG](assets/readme-tech-v3/hero.png) / [SVG](assets/readme-tech-v3/hero.svg) |
| 当前系统职责与链路 | [架构图](assets/readme-tech-v3/architecture.png) |
| 六格视频分镜 | [分镜稿](assets/readme-tech-v3/storyboard.png) |
| 36 秒架构概念片小样 | [MP4](assets/readme-tech-v3/concept-film.mp4) / [6 秒 GIF](assets/readme-tech-v3/concept-preview.gif) |
| 画板、来源和导出合同 | [素材说明](assets/readme-tech-v3/README.md) |
| 实际本地验证范围 | [设计验收记录](readme-tech-v3-validation.json) |

视觉稿由专门的 UI 设计子 Agent 制作，主 Agent 负责技术语义、浏览器复核和媒体导出。方案保存在独立分支 `design/readme-tech-20261110`，未发布为 main 或线上产品的新版本。
