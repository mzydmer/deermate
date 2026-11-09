# Workspace v2 样式图

状态：已批准的设计参考，2026-11-09 按最新 main `780173a` 规范重绘。全部数据为示例，非线上截图，不构成已实现或已验收声明。

图示直接读取根目录 `design.md` 的浅深色、字号/行高和主按钮文字色，不再维护冻结配色；`plates.json` 保存规范 SHA-256。PNG 为 2 倍分辨率，SVG 可缩放。图内文字、结构与绘图源一致；字体采用本机中文字体，不宣称加载 Geist。

| 文件 | 场景 |
| --- | --- |
| [01-home.png](01-home.png) / [SVG](01-home.svg) | 熟悉用户首页 |
| [02-first-visit.png](02-first-visit.png) / [SVG](02-first-visit.svg) | 首次进入 |
| [03-conversation.png](03-conversation.png) / [SVG](03-conversation.svg) | 连续对话与记忆反馈 |
| [04-memory.png](04-memory.png) / [SVG](04-memory.svg) | 关于你与记忆来源详情 |
| [05-mobile.png](05-mobile.png) / [SVG](05-mobile.svg) | 两个移动端页面 |
| [06-states.png](06-states.png) / [SVG](06-states.svg) | 六种关键状态 |
| [07-home-dark.png](07-home-dark.png) / [SVG](07-home-dark.svg) | 深色首页 |
| [08-work.png](08-work.png) / [SVG](08-work.svg) | 我的工作与执行证据 |

[生成源](render.cjs) 使用本地 `@napi-rs/canvas`，不访问网络、不调用模型、不运行浏览器。通过环境变量指定已安装的依赖目录和中文字体：

```bash
DEERMATE_NODE_MODULES=/absolute/node_modules \
DEERMATE_CJK_FONT=/absolute/chinese-font.ttf \
DEERMATE_PYTHON=/absolute/python-with-PyYAML \
node docs/prd/assets/workspace-assistant-v2/render.cjs
```

默认路径对应本机已有工作区运行时。Python 复用 `scripts/sync_design_tokens.py` 的严格 YAML 读取与引用解析；只有绘图依赖，不改变产品依赖，没有新增全局安装。

文案依据[页面文案稿](../../workspace-assistant-v2-copy.md)；[修改对照](copy-review.json)保留原文、替换文字和审稿理由。JSON 是本轮审稿记录，当前绘图源中的字符串为最终稿，重新渲染无需再次应用替换。
