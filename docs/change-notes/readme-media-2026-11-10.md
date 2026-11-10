# 文档影响检查：README 与真实界面演示

结论：无需更新客户文档。

理由：本次重写仓库中英文 README，删除过时的 Python-first、概念预览与中间验收堆叠，以当前已发布的工作台说明替代；替换仓库展示图片和视频，提供操作录屏的复现说明。没有改变应用中的文案、用户操作、权限、记忆策略、执行协议或线上运行版本。现有客户指南描述同一行为，把仓库材料整理记录成新的产品功能发布会产生误导。

涉及文件：README.md、README.zh-CN.md、docs/media.md、docs/assets/readme/、scripts/capture_readme.cjs、scripts/render_readme.py 与 requirements-media.txt 的用途注释；STATUS/EVOLUTION/验证索引记录素材范围。SPEC 中 FR-034 的旧 S0/S1 状态仅按既有发布收据纠正，需求不变。

保留 Router/Worker 的研究价值、现有能力与规划的区别、执行授权和加密端点边界。历史素材仍在原路径供旧链接使用，移出 README 首屏。

验证使用全新无模型、无设备授权的独立本地实例和专用合成管理员，真实保存记忆与更正，创建空临时对话，结束后停用该账号。浏览器脚本错误与模型投递均为零。FFmpeg 检查 MP4/GIF 可解码并记录文件哈希；截图、视频抽帧和 Markdown 展示另行目视核对。常规应用测试、真实模型和 Native 套件没有为文档重跑；相关历史证据仍以原收据为准。
