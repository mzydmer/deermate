# 文档更新约束

本文件适用于本仓库的所有后续 Agent 与贡献者。用户的新指示优先；本规则不增加单独审批步骤。每次变更都必须完成文档影响检查。

## 唯一内容来源

客户使用指南、技术方案与变更日志位于 [product/](product/guide/overview.md)。[目录](product/catalog.json)决定网页顺序、摘要、更新时间、状态及内部依据；正文 Markdown 是唯一内容源。运行生成器更新网页数据，禁止手工编辑 `product-docs.generated.json`。

产品文档不发布接口参考、部署指南、私人凭据或本地日志。内部工程文档保留原职责，不自动进入网页导航。参考点金文档中心的读者分流方式，内容必须依据 DeerMate 自身实现编写。

## 每次变更必须走的流程

1. 开始前读 AGENTS、STATUS 与本文件，识别受影响的需求、用户操作和技术不变量。
2. 修改功能、文案、权限、状态、限制或恢复行为时，同一变更更新对应使用指南；架构、数据流、可靠性、模型或评估变化还要更新技术方案。
3. 客户可见变化记入 `docs/product/changelog.md` 的「待发布」部分；实际发布后才补发布事实，不能用代码完成时间替代。
4. 更新目录中的日期、状态与 `sources`，核对源文件和证据。功能默认关闭、仅本地验收或实验未开展时必须明确写出。
5. 若仅内部重构、测试或构建维护且无需客户文档变化，在 `docs/change-notes/` 新建有理由的判定记录；不能省略影响检查，不能用空白、更新时间或自动生成文件充数。
6. 重新生成并检查，按变更范围验证页面，更新现有 SPEC / STATUS / EVOLUTION / roadmap；交付时说明文档更新和实际验证结果。

## 影响映射

| 变化 | 必查文档 |
| --- | --- |
| 对话、执行、状态、停止、恢复 | quickstart / conversations / faq；orchestration |
| 今日关注、首页动作 | focus；memory |
| 记忆、来源失效、上下文 | memory；technical/memory |
| 工具或设备授权 | tools / authorization / faq；architecture |
| 持续秘书、来源、规则和额度 | continuous；orchestration / evaluation |
| 架构与研究口径 | 对应 technical 页面；overview 与 changelog 中的能力声明 |
| 任意客户可见改动 | 对应指南与待发布变更日志 |

上表的短名均位于 `docs/product/guide/` 或 `docs/product/technical/`。文档应提供具体操作、可观察结果、异常处理和当前限制；不能只写“功能已更新”。

## 执行命令与 CI

```bash
python scripts/product_docs.py --write
python scripts/product_docs.py --base HEAD
python scripts/sync_design_tokens.py --check
```

本地 `--base HEAD` 覆盖暂存、未暂存和未跟踪文件。检查已提交分支时用任务起点提交替换 HEAD。CI 使用 PR 的 base 或 push 前的 SHA，验证目录、来源、链接、生成一致性与代码变更的文档影响记录。

实现代码发生变化却既没有产品 Markdown 与变更日志更新、也没有合格的无需更新记录时，CI 失败。删除文档不能替代更新。无需更新记录必须说明涉及文件与至少二十字的理由，审阅者仍须检查理由和实际代码是否一致。

自动门禁只能检查记录与内容一致性，无法证明说明已穷尽全部语义变化。Agent 必须阅读实际差异，并完成上述流程；仓库维护者需把 `product-docs` 配置为受保护分支的必需检查，才会在合并时强制阻止失败检查。

## 架构与流程图维护

架构、执行顺序、恢复、授权或记忆生命周期变化时，必须核对对应图示。布局与文字源为 `docs/diagrams/product/diagrams.json`，运行 `python scripts/product_doc_diagrams.py --write` 生成 SVG，随后运行无参数检查生成一致性。正文仅允许本地、带说明的安全 SVG 图示，禁止外链图像和可执行 SVG；CI 同时检查引用、文件与生成源。
