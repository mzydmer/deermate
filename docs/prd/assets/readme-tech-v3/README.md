# DeerMate 技术品牌视觉稿

本目录是 [README v3 方案](../../readme-tech-v3.md) 的视觉源与本地导出，不是当前产品的运行录像。UI 设计子 Agent 根据仓库既有鹿标和 design.md 制作原创矢量场景；主 Agent 导出 PNG、GIF 和 MP4，并核对技术职责。素材不含真实账号、私人任务、第三方品牌图片或模型生成的运行结果。

## 交付文件

| 文件 | 用途与规格 |
| --- | --- |
| `hero.svg` / `hero.png` | 品牌与技术主视觉；PNG 1600×960 |
| `architecture.svg` / `architecture.png` | Go、Router、设备、会话、记忆与证据职责；PNG 1600×1216 |
| `storyboard.svg` / `storyboard.png` | 六段架构叙事；PNG 1800×1195 |
| `film-cover.svg` / `film-cover.png` | 概念片首帧；PNG 1280×720 |
| `concept-film.mp4` | 36 秒、1280×720、24fps、H.264/yuv420p、静音；架构概念小样 |
| `concept-preview.gif` | 主片 10–16 秒的协调/执行并行片段；960×540、10fps、循环 |
| `visuals.js` | 确定性的 SVG 场景、分镜、播放与导出 API |
| `review.css` | 方案页的响应式排版；颜色来自共享 tokens |

独立 SVG 使用原稿 viewBox；PNG 使用下表的展示尺寸，不要求两者的内部坐标数值相同。主视觉固定画板内的坐标、字号和光晕属于可缩放插画几何；产品工作台没有使用这些布局。

## 本地预览与导出

直接在浏览器打开 [方案页](../../readme-tech-v3-review.html)。页面只读取本地 CSS/JS，包括仓库生成的 design tokens；不需要启动应用、模型或 Worker。字体从本机系统栈回退，不加载外链 Geist。

| 查询参数 | 浏览器 viewport / 截图尺寸 |
| --- | --- |
| `?export=hero` | 1600×960 |
| `?export=architecture` | 1600×1216 |
| `?export=storyboard` | 1800×1195 |
| `?export=film` | 1280×720 |

等待 `window.deermateDesign.ready === true` 与 `document.fonts.ready`；按 `window.deermateDesign.modes[mode]` 设置 viewport，等待两次 animation frame 后截图。使用 viewport 截图，避免 full-page 自动调整画板导致滤镜分块。`window.assetSvg("hero" | "architecture" | "storyboard" | "film")` 返回独立 SVG。

概念片使用 `window.renderFrame(t, { reduced: false })`，时间为 0–36 秒，无随机数或服务端依赖。本轮按 `t = frame / 24` 导出 864 帧，再交给 FFmpeg 编码；没有用实时录屏假装实际 Agent 执行。编码参数为 `-framerate 24 -c:v libx264 -crf 21 -pix_fmt yuv420p -movflags +faststart`。GIF 来自主片 10–16 秒，使用 `fps=10,scale=960:-1`、128 色调色板和 Bayer 抖动。

播放页默认暂停，支持键盘播放/暂停、时间轴、分镜跳转及减少动态。`window.setReducedMotion(true)` 固定每镜信号位置；静态 SVG/PNG 可作为 GitHub 的静态替代。GitHub README 本身不执行此页面的 CSS/JS。

## 技术语义

蓝青表示意图、工作和事件；紫色表示私人记忆。Go 拥有接纳、范围、预算与操作身份，Router 负责协调，Python Worker 连接设备上的原生 Codex 会话。记忆和工作证据分开；中断后先核对原操作。Claude / ACP、DeepSeek Harness、Hermesh 仅在明确标注的规划区展示。HTTPS/SSH 图示不构成云端不可读的 E2E 加密声明。

验证范围见 [设计验收记录](../../readme-tech-v3-validation.json)。没有在本轮执行模型、Native 任务或生产部署。
