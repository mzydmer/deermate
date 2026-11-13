# 文档影响检查：流式 HTTP 观测计时

结论：无需更新客户文档。

理由：修复的是运维调用链中 Go 出站 HTTP Span 提前结束的问题，使实现恢复标准请求耗时口径；不新增或修改聊天、工具、记忆、权限、执行结果与产品界面的用户操作。客户技术文章已有的标准 OpenTelemetry、隐私与尽力导出说明仍成立，分层和业务数据流不变。生命周期及升级前后判读写入运维指南与观测规格，不将部署细节加入客户指南或为此重建前端。

涉及文件：backend/internal/observability/http.go 与 telemetry.go 的 HTTP Transport；http_test.go 增加真实 SSE 和响应生命周期回归。仅更新 Go 控制面，Python 运行时、MCP、Worker 和设备授权不随此修复变更。

验证：旧实现被实际 SSE 回归稳定检出；修复后的 Go mod verify、vet、全包 race 通过。正常 EOF、读取/关闭失败、取消、并发结束、空响应、HTTP 错误、双向响应与关闭观测已覆盖。实际云端发布与 ARMS 验证结果另写 STATUS 和验收收据，不能用本地测试替代。
