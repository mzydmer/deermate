# Alpha 候选规范地址探测修复

结论：无需更新客户文档。

理由：仅修正内部发布候选 smoke 使用的 loopback 主机名，使其与现有本地部署配置一致。用户安装方式、对外地址、权限、初始化行为、运行结果与部署架构均未改变。

涉及文件：`scripts/verify_release_workspace.py` 将探测基址改为 `http://localhost:22077`。Linux 候选 run 43985613436 的容器已全部 Healthy，但原 `127.0.0.1` 地址返回 HTTP 301 到 `localhost`，严格状态检查因此失败。仍要求真实 readiness、setup HTML、未初始化管理员及零 users/runs/MCP tasks；不把重定向当作就绪。

验证：修改后 Ruff 与 diff 检查通过。实际 Linux 全栈结果由修复后 exact-head 候选 CI 复验，不沿用失败 run 的成功结论。
