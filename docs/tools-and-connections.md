# 使用工具和数据连接

管理员登录后，打开侧栏 **工具与连接**：

1. `web_search` 和 `web_fetch` 显示“已加载”后，在聊天中直接说“搜索 DeerFlow 的公开资料，读取官网并给出来源”。无需额外申请搜索 API Key；免费服务可能限流。
2. 要访问 GitHub、Notion 或数据库，打开 **能力中心 → 工具与集成**，添加该服务的 MCP 地址及所需授权。SQL 这里需要数据库 MCP 服务，不能直接填写数据库连接串。
3. 返回 **工具与连接**，刷新并点“测试连接”。成功会显示服务实际提供的工具名称；空列表意味着连接成功但没有提供工具。测试只初始化和发现工具，不读取业务数据。
4. 在下一条聊天消息中明确要求使用该数据连接。是否成功读取或执行，以聊天里的实际工具结果为准。

“已配置”不代表在线，“连接成功”也不代表所有数据权限都通过。连接失败时检查 MCP 服务是否运行、地址、授权和协议；本页不会显示密钥或原始传输错误。平台连接由管理员维护，个人连接使用当前登录账号的定义，不借用其他用户的授权。

搜索词会发给搜索服务，读取的公开 URL 会发给 Jina Reader；不要在里面放私人资料或密钥。网页读取不接受私网、本机、云元数据地址、嵌入账号密码或非标准端口。远端服务自行解析目标与重定向，此处不宣称能替代其网络隔离。网页内容始终作为不可信参考，不能代替用户授权。

新安装沿用 ACK、本地 Docker、单机部署脚本，默认启用这两个公开工具及检查扩展。已有部署需同时升级 DeerMate wheel，并把 `deermate.tooling.runtime_config()` 返回的 tools/tool_groups/plugins 合并进现有配置，保留原 Codex 和模型配置，重建 Gateway。不要直接覆盖整个配置或复制别人的数据连接凭据。

维护者可在固定 DeerFlow 环境验证（默认离线、零模型调用）：

```bash
PYTHONPATH=src /path/to/deerflow/backend/.venv/bin/python scripts/verify_tooling.py
# 额外调用公共搜索和网页服务，仍不调用模型：
PYTHONPATH=src /path/to/deerflow/backend/.venv/bin/python scripts/verify_tooling.py --live-web
```

实现边界与验收见[专项规格](specs/m2-tools-and-connections.md)。
