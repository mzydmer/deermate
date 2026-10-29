# 对话与执行器会话

1. 点击“新对话”，发送第一条消息。系统据此自动生成名称；在对话的“更多”菜单里可以重命名，后续消息会保留手动名称。
2. 第一次让 Codex 处理一个已注册项目时，这个对话建立固定关联。后续继续提问、解释或改代码，都沿用同一原生会话和工作区，每轮仍有独立任务与验证记录。
3. 对话工具栏或侧栏菜单中的 **会话关联 → 查看执行器会话** 显示执行器、轮次、原生会话 ID 和当前状态。第一次任务尚未建立原生会话时会明确提示等待确认。
4. 切换项目或执行器时，新建一个对话。任务仍在执行、等待输入或结果未确认时，先查看该任务；系统不会自动新开另一个会话来代替它。

一个对话仍然可以搜索、读取网页和使用已授权的数据工具。限制针对已注册的代码执行器连接。当前实际支持 Codex；Claude 的执行适配器尚未实现，不显示为可用能力。

旧对话只有一个确定的原生会话时，可以通过“继续解释/继续修改”沿用它。旧记录没有保存项目 ID 时，不会从新请求猜测项目，需使用继续工具。存在多个会话、正在执行或历史不完整时，会要求检查原记录或新建对话，不自动挑选其中一个。

维护者：新部署的 ACK、本地 Docker、单机配置包含
`extensions.middlewares: [deermate.session_middleware:CodingSessionMiddleware]`。
已有部署需升级 Gateway wheel、保留现有 `extensions` 配置并合并此项，再重建
Gateway。日记位于应用 home 的 `data/deermate-chat-sessions.sqlite3`，应随应用
home 一起备份；不能通过删日记重试不确定的任务。更改注册的执行器连接需显式维护
中间件 `profiles`，不能把任意 MCP 服务自动当成已验证的执行器。

固定 DeerFlow 环境下的离线图验证（零模型和原生调用）：

```bash
PYTHONPATH=src /path/to/deerflow/backend/.venv/bin/python scripts/verify_chat_sessions.py
```

设计与验收见[专项规格](specs/m2-chat-session-binding.md)和
[ADR 0012](decisions/0012-one-chat-one-coding-session.md)。
