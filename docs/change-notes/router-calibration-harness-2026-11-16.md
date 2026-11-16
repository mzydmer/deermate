# Router 校准 harness 的文档影响

涉及 `scripts/verify_router_a.py`、`tests/router_evaluation_model.py`、`tests/fake_codex.py` 和 Go `evaluation_*` 文件及三个窄 hook。当前只实现非正式 A 异步垂直切片与 Linux 测试 tag 的事件/计时入口，尚未证明切片通过，也未开始正式36格。

普通 Go 构建没有测试路由、配置开关或计时表，仍使用已有订阅直通；专用 Linux evaluation tag 和明确 loopback/fixture repository/key 才安装校准入口。A 复用原 FixtureModel、普通后台 MCP、CodingSessionMiddleware、ask_in_chat、Relay 和 Worker，在真实追踪回执后结束协调轮次。Native 仍为原离线 fake_codex，附加时间域与实际文件变更记录只在显式测试配置下启用。没有变更客户功能、真实模型语义或外部权限，产品评估页的“协议已接受、harness待校准、无结果”说明仍成立，因此无需新增客户能力声明。

统计输入将实际 messages（含tool_calls和非string内容）与绑定工具schema序列化后计数/限额；模型日志绑定operation/run/thread/role。Go和Native用Linux monotonic加boot_id，runner用自身时间域。当前Router读取接口只在settled时呈现完整回复，首次可见与完整回复因此是同一个实际服务事件，不代表流式首token。

校准01在镜像准备失败，02在容器执行位失败，均未接纳任务；旧main22ef不支持capabilities的无卷小预检也保留，不算协议失败或正式样本。普通构建无测试入口反例通过，RPC/Worker默认路径25项通过，Linux evaluation-tag已编译；合入#4后需重新构建/预检并完成真实A合同。失败卷/日志保留，不改整个bundle权限。


现已正常合入main9c7ab6d；capabilities来自该已合并基线。新启动前先核对tag与给定不可变ID、从镜像只读取出二进制核对Linux/amd64及evaluation build tag，再以UID1000/networknone运行capabilities，全部通过才建校准卷。COPY只对二进制使用0555，不放宽bundle。尚待重新构建及实际A合同。


校准03的服务内健康通过，但internal-only控制面发布端口在Mac拒绝连接，尚未创建账号或任务。无状态HTTP探针证实internal监听可用、仅internal发布端口不可达；独立最小代理双网入口的第二次无卷探针200且后端始终只有internal。新harness复用既有Nginx镜像和固定上游最小配置，只有代理双网/loopback，Go与Gateway无外网，不改daemon/全局路由；三组共享此执行环境，不改输入或预算。首个代理探针未就绪记录也保留，未当作通过。
