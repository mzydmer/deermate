# Router 校准 harness 的文档影响

涉及 `scripts/verify_router_a.py`、`tests/router_evaluation_model.py`、`tests/fake_codex.py` 和 Go `evaluation_*` 文件及三个窄 hook。当前只实现非正式 A 异步垂直切片与 Linux 测试 tag 的事件/计时入口，尚未证明切片通过，也未开始正式36格。

普通 Go 构建没有测试路由、配置开关或计时表，仍使用已有订阅直通；专用 Linux evaluation tag 和明确 loopback/fixture repository/key 才安装校准入口。A 复用原 FixtureModel、普通后台 MCP、CodingSessionMiddleware、ask_in_chat、Relay 和 Worker，在真实追踪回执后结束协调轮次。Native 仍为原离线 fake_codex，附加时间域与实际文件变更记录只在显式测试配置下启用。没有变更客户功能、真实模型语义或外部权限，产品评估页的“协议已接受、harness待校准、无结果”说明仍成立，因此无需新增客户能力声明。

统计输入将实际 messages（含tool_calls和非string内容）与绑定工具schema序列化后计数/限额；模型日志绑定operation/run/thread/role。Go和Native用Linux monotonic加boot_id，runner用自身时间域。当前Router读取接口只在settled时呈现完整回复，首次可见与完整回复因此是同一个实际服务事件，不代表流式首token。

校准01在镜像准备失败，02在容器执行位失败，均未接纳任务；旧main22ef不支持capabilities的无卷小预检也保留，不算协议失败或正式样本。普通构建无测试入口反例通过，RPC/Worker默认路径25项通过，Linux evaluation-tag已编译；合入#4后需重新构建/预检并完成真实A合同。失败卷/日志保留，不改整个bundle权限。
