# Router 校准 harness 的文档影响

涉及 `scripts/verify_router_a.py`、`tests/router_evaluation_model.py`、`tests/fake_codex.py` 和 Go `evaluation_*` 文件及三个窄 hook。当前只实现非正式 A 异步垂直切片与 Linux 测试 tag 的事件/计时入口，尚未证明切片通过，也未开始正式36格。

普通 Go 构建没有测试路由、配置开关或计时表，仍使用已有订阅直通；专用 Linux evaluation tag 和明确 loopback/fixture repository/key 才安装校准入口。A 复用原 FixtureModel、普通后台 MCP、CodingSessionMiddleware、ask_in_chat、Relay 和 Worker，在真实追踪回执后结束协调轮次。Native 仍为原离线 fake_codex，附加时间域与实际文件变更记录只在显式测试配置下启用。没有变更客户功能、真实模型语义或外部权限，产品评估页的“协议已接受、harness待校准、无结果”说明仍成立，因此无需新增客户能力声明。

统计输入将实际 messages（含tool_calls和非string内容）与绑定工具schema序列化后计数/限额；模型日志绑定operation/run/thread/role。Go和Native用Linux monotonic加boot_id，runner用自身时间域。当前Router读取接口只在settled时呈现完整回复，首次可见与完整回复因此是同一个实际服务事件，不代表流式首token。

校准01在镜像准备失败，02在容器执行位失败，均未接纳任务；旧main22ef不支持capabilities的无卷小预检也保留，不算协议失败或正式样本。普通构建无测试入口反例通过，RPC/Worker默认路径25项通过，Linux evaluation-tag已编译；合入#4后需重新构建/预检并完成真实A合同。失败卷/日志保留，不改整个bundle权限。


现已正常合入main9c7ab6d；capabilities来自该已合并基线。新启动前先核对tag与给定不可变ID、从镜像只读取出二进制核对Linux/amd64及evaluation build tag，再以UID1000/networknone运行capabilities，全部通过才建校准卷。COPY只对二进制使用0555，不放宽bundle。尚待重新构建及实际A合同。


校准03的服务内健康通过，但internal-only控制面发布端口在Mac拒绝连接，尚未创建账号或任务。无状态HTTP探针证实internal监听可用、仅internal发布端口不可达；独立最小代理双网入口的第二次无卷探针200且后端始终只有internal。新harness复用既有Nginx镜像和固定上游最小配置，只有代理双网/loopback，Go与Gateway无外网，不改daemon/全局路由；三组共享此执行环境，不改输入或预算。首个代理探针未就绪记录也保留，未当作通过。


B/C检查点新增共享canonical关联函数，C摄取时关联，测试A/B在Router完成后按既有权威订阅确定性附加；普通构建仍C且无测试入口/模式开关。专用context reader沿用原assessmentInputs/assessmentBatch及owner/用户版本/来源/规则/event revision检查；模型收到相同有界批次正文，未以“模型自行路由”宣传。Linux tagged四项顶层合同与失效子组通过，初次Origin和nonce测试fixture错误均保留且不放宽guard。已固定测试项目Git日期以便后续验证相同snapshot；B/C真实链、独立judge及36格仍未运行，不能称研究结果。新增产品技术页/待发布状态仅说明实际检查范围；默认来源回归和完整Go检查另记录。

新增 `scripts/run_router_sample.py`、`tests/router_evaluation_probe.py` 与 `tests/test_router_sample.py`，复用已有A启动/设备配对函数，先校准一个normal B再验证C。原始证据采集只读并剔除nonce/凭据；公开任务handle只从本人已知thread的list/detail发现。完成屏障要求所有层和通知收敛后4秒稳定，Worker单独完成不足；测试覆盖未收敛和替代身份反例。脚本只支持非正式normal，S1/S2尚未实现即提前拒绝，尚无比较结果。全部为显式隔离fixture维护，未修改生产轮询、客户交互、默认路由或授权，因此客户指南和能力声明无需变化；共享fixture的MCP轮询对齐协议1秒。

normal B01保留真实Go SQLITE_BUSY/503且无Native，B02完成实际任务后因通知输入超预算未达到完整屏障。测试model统一将三组通知工具设为空，完整保留通知messages，不增预算/不截关键正文；拒绝调用前记录实际输入bytes/hash和身份。生产middleware、SQLite和通知实现未改，因此无需客户文档能力变更；需新样本校准后才能记通过。镜像预检附加现有producer label，与harness当前提交分别记录，避免复用控制镜像时混淆生产身份。

B03移除工具后仍首次12,544 bytes超预算，失败保留。经评审接受，增加显式owned-admission-v1通知测试适配：只读复核当前已知run的owner/thread/mcp_notification origin，完整保留原接纳单HumanMessage与哈希，固定短System且无tools；普通历史和重试错误不带入。三个Gateway运行时合同覆盖三组输入哈希一致、错owner/thread/origin、多消息和非Human拒绝，已通过；预算未扩大，未修改生产路径。协议/基线配置、产品技术评估与待发布说明同步限定该证据范围；B04真实通知投递与完整屏障仍待校准。

干净4abb692的B06完整正常链通过并经独立复核：一个Worker/MCP/root/turn/effect、独立测试0、公开MCP完成且通知delivered、Go四操作settled，4.15172秒稳定尾部，通知完整admission哈希与1947bytes模型输入可关联。普通Go mod/vet/full race（36.600s）/无CGO与Linux-tag构建及实际Linux九项顶层合同通过；这是normal校准，不是S1或正式比较。

同源C01 Native/Worker及通知已完成，前台perform/query的OperationalError使原操作uncertain并超时，失败保留；原日志未捕获完整栈，尚不能指定竞争写方。发现测试计时在每次GET中对已可见项执行零匹配UPDATE，两个受控Linux合同先失败后通过：现仅前台接纳建时钟记录，只有首次实际可见时写一次，后续在其他连接持写锁时仍只读且原时钟不变。普通构建仍无测试路由/计时，三组统一新测试策略；这不是取消实际共库竞争或改变生产派单。`continuous_fixture_model.py` 对evaluation配置下的原perform/query异常增加0600私有栈记录并原样抛出，调用一次且不加等待/重试。新版本需要重新检查并校准；原C失败不覆盖，不预称根因全部排除。

bb7同源B07/C02均达到完整正常屏障，已获独立复核接受，见router-normal-calibration收据；旧投影计时仅诊断。S1新代码独立调度九个固定项，前台reader独立，各项finally落盘且未发送保留；新增测试用阻塞前台HTTP验证后续仍发送，并保留真实503和全部未发送项。另以现有Go管理API创建第二个合成已认证admin，正确ExpectedID、无Worker授权，验证原工作读取403及事件接纳403；旧header错配仅独立反例。模型保留实际有界事件正文与哈希，operator fixture事件回执返回原事件ID/状态/归属便于核对，未扩生产API。

服务计时hook移到实际JSON写出后，成功Flush才取时刻，随后存DB；失败Flush不记数，追加真实HTTP writer顺序/失败合同。指标改名service admission→reply flush，客户端另报真实complete-read值，服务点不能宣传浏览器精确可见。普通hook仍no-op，只有tag fixture Flush。合成只读token0600置于新home，由静态GitHub transport读取，防止>60s校准因缺fixture token而失效，不调用外部GitHub。当前S1仅代码/合同通过，实际S1、S2代理、judge/负例和正式批次尚待完成；所有模式共享实现、权限和预算。


S1实际三组已通过并经独立评审接受，公开收据保留df8 producer及B01配对回滚失败。S2新增 tests/router_evaluation_proxy.py、tests/router_evaluation_proxy_contract.py 并接入 scripts/run_router_sample.py 与 verify_router_a.py；固定loopback上游、只读持久屏障、零字节真实socket关闭一次，18s小于原Go20s预算。公开恢复结束后才采集proof，不向驱动传私有句柄；缺屏障/上游失败/observer错误不得成功。真实TCP三项及runner九项合同通过，实际S2尚待校准。仅显式Linux隔离fixture，未改产品路由/授权/恢复，技术评估和待发布状态已同步，不增加客户能力声明；生产架构图不变。
