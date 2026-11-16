# 共享工作账本的写意图与校准失败

涉及 `backend/internal/controlplane/continuous_store.go`、`continuous_runtime.go` 与新增并发测试，遵循 CONT-08/10/13 和 NFR-004/005。此为已有账本接纳/幂等合同的修正，不增加权限、接纳动作、自动恢复或外部派发。

normal B01/04/05均真实返回SQLite BUSY/503、无MCP/Worker/Native；原WAL卷的操作接纳/完成标记均未写入。原始Go日志没有逐SQL栈或竞争写方身份，不能事后指定某个Gateway写作业为原因。完整原ToolMessage从各自原checkpoint提取，仅私存；公开材料只记抽象错误类别与证据哈希。B02/03另为通知超预算至dead_letter，所有旧卷/日志保留，尚无正式样本。

独立连接持有真实写锁时，原deferred事务的canonical读取可以成功，首次操作UPDATE稳定返回同一SQLITE_BUSY(5)，回滚后原记录逐字段、操作键和Native计数不变。新增两个期望先取得写锁的测试在修正前失败，保留红日志。有限修正只在workTransaction调用回调前执行零匹配写语句取得writer intent，沿用已有5s busy_timeout与request context；零行改变，不重试回调，也不重放外部副作用。加入固定阶段错误上下文便于后续私有诊断，公开503正文仍为抽象错误。

已核对22处生产调用与两处evaluation-tag调用：回调仅使用传入事务读写数据库及构造本地记录；模型/能力检查、GitHub请求、runtime HTTP在事务外。没有在持锁回调等待另一进程的runtime I/O，不改全局SQLite连接模式，也不改其他Store事务。

五项聚焦测试通过：旧deferred写锁竞争及完整回滚、写锁释放后回调恰一次、锁等待耗尽前回调零次、真实HTTP工具路由503后原记录全等且0 runtime派发、显式原token请求返回同一完整操作对象与单action、取消前回调零次。HTTP测试仅准备数据库操作，没有实际Native执行；不能替代B/C完整链。首轮HTTP断言误按JSON键序比字节，修正为完整结构对象相等，身份/单操作/零派发要求保持，日志保留。

技术协作页、持续工作指南、待发布日志与目录同步说明锁忙时核对原操作；执行/恢复图的发送屏障、原身份和未知分支不变。候选方案已获独立评审方向接受，须完成普通Go必要检查并在三组同一新源码下重新校准B/C；旧B失败不覆盖，未运行正式36格或付费模型/Native。
