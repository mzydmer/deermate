# Router 离线对照协议 v1（协议已接受，实验未运行）

- 状态：Accepted protocol（2026-11-16 独立评审）；A异步、正常B/C及S1三组校准通过；S2/独立judge/负例与正式批次未完成。
- 跟踪：[Issue #5](https://github.com/mzydmer/deermate/issues/5)。
- 需求：R-EVAL-01–05；CONT-05/06/08/10/13/15；NFR-004/005/006/010。
- 基线：[router-baseline-v1.json](router-baseline-v1.json)。实际 producer SHA、数据集 SHA 和结果尚为空。
- 代码阅读基线：main `22ef5c548f134dbd28dd4e0e290538a569390c65`；运行时版本只能读取 `deploy/deerflow.lock`。

## 问题和结论边界

第一批检验两件事：长后台执行期间的前台可用性，以及持久接纳后回执丢失时的原操作核对。比较真实 Go、固定 DeerFlow Gateway、MCP、设备 Relay、Worker 和独立验证路径，用脚本化 Provider/Native 进程替代付费供应方及真实设备。不能根据这些等待时间推断模型能力、账单、真人注意力成本或云主机容量。

A/B 是协调结构的整体对照，公开各自实际工具/上下文与排队开销，不把它归因为一个单独因素。B/C 只改变已绑定事件是否经过 Router，才用于订阅直通的归因。相等或 A 更快均为有效结果；不预设 Router 能缩短前台延迟。

## 三种路径和公平基线

| 配置 | 模型和会话路径 | 后台执行 | 已绑定来源事件 |
| --- | --- | --- | --- |
| A 单协调会话 | 一个持久 DeerFlow 协调图；显式请求、前台问题与事件均进入该图 | 使用现有普通 MCP 后台 task 与 `CodingSessionMiddleware` / `ask_in_chat`，拿到持久追踪回执即结束当前协调轮次；Native 继续运行 | 同一协调图读取有界事件，不能触发额外 Native 轮次 |
| B 全事件 Router/Worker | 持久 Router 用 `secretary_route`；Go Native lane 派给独立工作线程 | 现有 `continuous.perform`、MCP task、Relay 与 Worker | 绑定校验后仍经 Router；保留事件合批 |
| C 订阅直通 Router/Worker | 与 B 相同 | 与 B 相同 | 现有 `ingestGitHub` 已绑定 `subscription` 分支直接更新原工作上下文，新增 Router 调用为零；无绑定事件仍走 Router |

A 具备相同后台能力、Worker 并发和查询能力，不调用同步 `wait_until_completed`，不在工具回执之后占住协调图等待 Native。前台问题必须在后台仍执行时真实进入图并得到实际回复；以 Worker 运行区间和模型日志证明，不能只测 HTTP 202。

三组均由真实 Go 持久 admission 接纳协调请求。计划在**测试专用** Gateway contribution 中实现 A 的普通协调图适配，加载同一 owner、操作 ID、用户版本与模型预算，再调用现有普通 MCP 编码路径。A 的 Native 身份由现有 chat journal/MCP/Worker 证明，不伪造 B/C 的 Native operation 行。B 的唯一测试差异是关闭已绑定上下文直通分支，让它继续走现有 `enqueueExternal`；C 复用默认分支。所有适配只随隔离测试启动器安装，生产镜像/公共 API 没有模式开关。

实现前须证明两项基线合同：A 的后台工具回执在 Native 结束前返回，且后续前台模型轮次能够重叠；B/C 的路径差异只有绑定分支，不能连带改变来源校验、优先级、合批、权限或预算。若现有集成无法保持此合同，先修订协议供评审，再运行；不能事后把三份标签相同的模拟器称为三条路径。

以下条件固定相同：

- 相同初始 toy Git 提交、测试命令、补丁目标、合成 owner/设备授权和过期策略；单 Worker、Native 并发 1，每项工作只允许一个根和一个变更轮次。
- Provider 是同一脚本化模型类与应答表，调用延迟 50ms；Native 每次在真实 `turn/start` 接纳后等待 12s，再写实际补丁并运行 Worker 配置中的独立测试。延迟来自实际单调时钟，不能写回人工估计值。
- 每次模型请求最多 1024 output tokens，最大输入 12,000 UTF-8 bytes，同一工作卡和同一批来源正文。上下文构造和实际输入字节均记录；历史如何保存属于结构差异，超预算必须拒绝并计失败，不截断关键证据来配平。
- 每组协调模型预算 20、研判预算 4、Native 预算 1，MCP poll interval 1s，Go 队列保持现有 3s tick；批量上限 20 件/16,000 bytes，固定事件采用同一个 Thread，避免只对 B 取消合批。
- 执行环境用最小固定上游HTTP代理提供loopback入口，只有代理同时连接ingress与内部网络；Go和Gateway仅接internal网络、无外网，Native/Worker仍在同一Linux fixture。Mac runner仅提供客户端计时与调度；服务/Native延迟仍按前述Linux同域计算。三组使用同一代理配置，不改变任务、预算或故障屏障。
- 三组使用同一Go源码与持续账本事务策略：读取前取得writer intent，原数据库回调执行一次，锁等待沿用5s busy timeout及请求context；没有仅对B/C加等待或重试外部动作。早期SQLite BUSY/503校准失败保留，修正后须重新校准并冻结新版本，不混入正式批次。
- 每个样本新建 fixture owner、home 和工作目录；已下载镜像与官方 tokenizer 缓存预热，不复用上一样本的 DB/事件/模型缓存。启动和健康检查单独记时，均不进入前台响应指标。
- 相同机器上串行运行，保留 CPU/内存限制和实际版本；不调整全局 Docker 网络或既有实例。无 Provider/真实 Native 凭据，网络只连本批 fixture。

## 数据集、锚点和两个场景

公开数据集仅含合成消息、事件、预期归属和可验证 toy 修改。每个事件带逻辑 ID、Thread key、owner、revision、到达偏移、预期 work ID 和允许动作；运行时随机 UUID 另外保存映射，不能用 UUID 是否相同判断三组配对。

每个时间戳显式带 clock_domain，Mac runner 与 Linux 容器的 monotonic 不直接相减。调度原点 `t0` 定义为 runner 观察器**收到真实 `turn/start` 入站事件**的本域时间；该事件另保留 Native 本域时间。观察器按固定20ms读取周期记录观测区间/实际调度漂移；负载导致超出周期的实际观测延迟仍保留，不能声称20ms硬界。没有锚点的30s样本输出 `anchor_timeout`，不能删除或更换 seed。服务 admission→首次内容、排队与 Native 执行耗时各自用同一 Linux 计时域，client发出→first/complete用 runner 本域；跨域重叠需通过同域事件或观测区间证明，不能拼接时间戳。

| 场景 | 固定输入与故障 | 事先定义的检查 |
| --- | --- | --- |
| S1 `background-foreground` | 本人明确修复 toy 加法；t0+0.10/0.20/0.30/0.40/0.50/0.60s 投递六条同 Thread 的已绑定更新，+0.25s 提交一个独立前台问题；+0.70s 一个无绑定只读事件，+0.80s 一个外 owner 事件 | 实际前台回复时刻相对 Native 完成；一个原根/轮次、补丁和独立测试通过；绑定更新归原工作，越 owner 不接纳，无绑定事件不获执行权；记录所有角色调用和合批结果 |
| S2 `lost-admission-ack` | 同样的一次变更；在 Gateway 已持久保存相同 operation 的 run、MCP tracking 与 chat journal 后，fixture HTTP 故障代理丢弃第一次 Go→Gateway admission 的成功回执并断连；+0.25s 同一前台问题，+0.50s 再投递相同逻辑输入 | 三组均穿过相同“持久追踪已存在、Go 未收到回执”屏障；只查原操作，不重放 mutation；原 run/task/root 可核对，或明确保留 unknown；恢复后独立测试和副作用计数验证 |

S2 丢失的是三组的初始 Router/coordinator admission ACK；B/C另等该原Router的 `_tool_result` 所关联Native operation的MCP/chat journal持久化，不称Worker admission ACK丢失。固定代理仅转发到同Gateway的loopback:8001，在Go的20s预算内最多等待18s，不先发任何响应字节，持久化齐备后真实关闭socket一次。若屏障未达、上游非200或observer错误，不能计成功注入或成功恢复；第二次响应不再丢弃。故障证明只在公开恢复驱动结束后采集。

S2 代理以已保存的 operation 对应 tracking 为触发条件，不能在 A 尚未接纳、B/C 已接纳的不同阶段丢包。代理可以观察只读持久状态以确认屏障，但恢复驱动只能使用原请求已知的 operation/thread 和正常本人查询接口；不能把观察器私下发现的 Worker handle 注入恢复流程。如果缺少可用的原结果核对接口，就记 `outcome_unknown`，不创建新根；此样本安全不重放可以通过，但**验证完成率仍计未完成**。

每个样本总上限 90s；单次前台回复观察 30s。明确终态、失败、超时、unknown 均结束采样并落盘。外层预算 36×90s 加实际启动时间，超外层预算时尚未运行的格子保留 `not_started_budget`，不能只汇总已成功格子。

## 实际模型输入与完成屏障

A/B对已绑定事件的最终附加是测试适配中的“已有权威订阅确定性附加”，不声称模型自行决定工作归属。B必须先经过真实Router完成，之前不能成为context；C在摄取时直接附加且绑定事件零新增Router。A/B模型真实接收相同批次的有界事件原文，使用原assessmentInputs/assessmentBatch复核owner、来源、规则及event/rule revision；完成后的附加再次复核，失效则不附加。Native授权撤销阻止新增执行，不额外阻止仍合法的只读context。普通构建保留默认C合同，专用测试适配不得扩大公开功能。

模型输入计数/上限包含实际序列化messages（含tool_calls和非string内容）与绑定工具schema；按operation/run/thread/role关联日志，事件批次另记完整有界正文、引用与context哈希。当前Router API在settled时才返回非空整段回复，不称为流式首token。

计时仅对已声明的前台输入建立admission记录；Go写出包含原回复的实际JSON并成功Flush后才采同域时钟，随后持久化一次，失败Flush保留null。主服务指标命名为 **service admission → reply flush**；旧列名first_visible_ns/complete_ns表示这同一整段回复的服务传输观测点，不能宣传为浏览器精确可见时间。客户端另记请求发送→完整JSON实际读到原前台marker的真实值，两域不相减。normal预试旧字段是响应前投影快照，仅诊断，不混入本指标。后续轮询只读，初始安排和后台回执不建立前台时钟，三组规则一致。测试perform/query异常栈只私存并原样抛出，不重试动作；初期存储竞争及计时干扰的校准失败保留，修正后冻结新版本。

S1每个固定offset独立发送并持有独立客户端，前台观察器独立运行；先前HTTP响应不会阻塞后续输入发送。所有计划项预先保留，finally记录实际send/status/error/drift，HTTP失败、timeout和未发送项不删除。外owner项使用第二个真实创建、已认证的合成admin，无Worker授权，携带其本人正确ExpectedID；其读取原工作和事件接纳均应403。仅伪造原owner的ExpectedID属于另列Go反例，不充作外owner事件。合成GitHub只读token仅供静态fixture transport，三组共用，不接触真实GitHub或凭据。

三组通知统一使用测试适配 `owned-admission-v1`：以当前runtime已知run复核owner、thread与持久origin_kind=mcp_notification，只读取该run原始接纳的单个完整HumanMessage（含原通知说明和已框定的不可信事件）；配固定短System提示、空tools，保留原通知全文序列化SHA。普通会话历史、重试错误历史和通用工具说明不注入这一步，不截通知正文，也不增加12,000 bytes/1024 output上限；非本人、非通知、thread不匹配、多消息或非Human输入拒绝。超预算拒绝另记实际bytes/hash与身份。此为所有组共同的离线测试输入适配，不能据此声称默认生产通知已经在该预算内验证。

正式样本只有在Worker独立验证及终态、MCP本人公开tracking终态、应有Go原operation/inbox终态、关联runs终态及通知投递全部核对后才进入完成屏障；之后再观察4s（超过Go tick与MCP poll）确保没有迟到模型/执行调用。调用数覆盖该屏障，A与B/C采用相同完成标准；任何层未收敛保留unknown/timeout，不能只靠Workercompleted结束。A用原请求已知的coordinator thread和正常本人MCP list/detail接口发现原tracking，B/C用原work的公开执行thread；禁止从私有观察器注入task句柄或重放。

## 配对、顺序和失败保留

每个场景用同样六个配对 seed：1101–1106，每 seed 依次运行 A/B/C，顺序按下表轮换。共 2×6×3=36 个计划样本，各场景各配置六次，不少于五次。相同 seed 的公开输入和延迟完全相同；seed 只决定已声明的 toy ID/内容变体，不改变延迟来偏向某配置。

| seed | 三组顺序 |
| --- | --- |
| 1101 | A B C |
| 1102 | B C A |
| 1103 | C A B |
| 1104 | A C B |
| 1105 | C B A |
| 1106 | B A C |

先完整运行 S1，再完整运行 S2，场景间停止本批 fixture。修正代码、依赖、数据或阈值后必须是新批次和新版本；旧的失败/预热/诊断尝试仍保留。不得看到结果后删 seed、延长单组 deadline、只重跑较慢一组，或把预试样本混入已冻结批次。

## 独立判定和重复副作用反例

判定器是单独 CLI，输入公开脱敏 raw records 与证据文件，输出每样本 verdict。它不读模型自然语言中的成功声明，不信任 runner 的 `passed` 字段，也不靠单一状态枚举判成功。

完成需要同时具备：Worker 保存的 operation/task/parent 与同一原生 root/turn/workspace；实际 Native trace 的入站轮次；实际 Git diff/文件哈希符合任务允许范围；独立测试命令真实退出 0；只在 Native fixture 受理一次变更时追加的副作用 journal 恰好一条，并且其 logical operation 与原请求相同。task.finished、证据、退出与时间须互相一致；未知字段保留 null。

判定器必须先拒绝一份**刻意注入两次同逻辑变更副作用**的完整负例：即使文件最终内容相同、测试为 0、模型和 Worker 状态声称 completed，也要因 journal/trace 中第二次 effect 判失败。负例通过真实 fixture 入口产生两次记录，不只改 runner 的计数列。此负例单列校准样本，不计入 36 个对照样本。

另校准错误 root 关联、无独立测试、超范围/外 owner 接纳与缺失证据；缺失证据须失败或 unknown，不能补成零。原始私有日志/凭据不发布，公开的合成证据仍须足以让该 CLI 重新判定。

## 记录和统计

每个样本保存 batch/run/scenario/mode/seed/order、原逻辑操作和全部实际身份映射、带时间域的分阶段时钟、真实持久接纳/排队/首条可见内容/完整回复/调用/验证事件、输入字节、角色调用数、副作用 journal 和独立判定。HTTP200/202或空SSE帧不算真实回复；首次内容需能关联原前台输入。真实供应方 tokens、账单或人工介入在本批不可测，保留 null，不用脚本响应的字符数冒充。

| 指标 | 分母和算法 |
| --- | --- |
| 验证完成率 | 独立判定完成数 / 每场景每组计划 6；超时/unknown/未启动留分母，另列状态计数 |
| 前台响应主指标 | 同一服务计时域内，原前台请求持久 admission→完整JSON回复成功flush（服务传输点）；报告逐次值与 nearest-rank p50/p95/max，取排序第 ceil(q×n) 项；列实际观测分母、删失和排队耗时 |
| 客户端/完整回复 | runner同域的请求发出→实际完整JSON读到原前台回复；服务同域的admission→reply flush分列，不称精确浏览器显示；同样列分母/删失，不把HTTP接纳当回复 |
| 前台可重叠率 | 服务reply flush在Native独立验证完成前结束的数（不冒称浏览器显示） / 6；没有可用回复计未达到，不填 0ms |
| 完成/排队/恢复延迟 | 各阶段实际事件差；未完成记 null + censor/status，不混入延迟分位数 |
| 重复副作用/根 | 同逻辑 operation 的额外实际 effect/root 数；另报受影响逻辑操作数 / 6；查询重试不计 mutation |
| 原操作恢复核对率 | 原已接纳结果被正常查询接口确认且独立证据一致数 / 注入故障样本 6；unknown 单列 |
| Router/Assessor/协调模型与上下文 | 按实际调用日志逐角色计数，实际请求 UTF-8 bytes 求和；A 的协调调用不能填作“零模型成本” |

在六个配对 seed 上另报告 B−A、C−B 的逐对差；只对双方均有真实观测的延迟给出差值，并列出其余缺失配对。样本小，不做显著性或总体性能推广。统计脚本必须从 raw records 计算，不能读手写汇总；重复运行应得到相同离散计数、分母和采样值汇总，重新执行系统的墙钟值仅作新批次。

## 实施、冻结和交付门槛

1. 协议与基线已获独立评审接受；先实现专用 Provider/Native、A/B/C 适配、runner、独立 judge 和 aggregator，补齐上述首次可见响应与时间域口径。
2. A非对照合同已通过并获独立评审接受（[收据](../verification/router-a-calibration-2026-11-16.json)）；继续B/C最小差异合同和判定器负例，保留日志。通过后提交全部 harness、数据集和配置，要求工作区干净，记录完整 producer SHA、上游锁、数据集/配置/harness 哈希、Python/Go/Docker/机器和镜像不可变 ID。
3. 第一个正式样本启动前写一次不可覆盖的 batch manifest；其 producer SHA 必须含本次实际运行的 harness 和数据。结果文件记录 producer 和 dataset SHA，不能使用整理时 HEAD 反推生产身份。
4. 按固定 36 格运行并保留全部结果，单条计划命令从 raw 聚合和独立复判。公开协议、数据、脱敏原始样本、negative control、聚合代码/输出与失败边界；原私密材料留本地。
5. 更新研究页面/STATUS/EVOLUTION/roadmap 和引用记录；只标记本批实际覆盖的 R-EVAL 子集。引用召回消融、合批消融、其他故障点与真实模型/用户研究另立协议，不勾选整个 R-EVAL-01–05。

计划命令为 `scripts/run_router_evaluation.py`、`scripts/judge_router_evaluation.py` 和 `scripts/aggregate_router_evaluation.py`；这些文件当前尚不存在，不能当作已可运行说明。最终命令和参数须随 harness 提交后替换本段。

正式批次后，以同一冻结harness/数据/配置单独复跑seed1101的两个场景×A/B/C六格，核对离散mutation/root计数与终态；复跑manifest和结果单列，不能混入主36格。差异和失败同样保留，不以重复取代主批次失败。
