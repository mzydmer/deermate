# 单机冷备与空卷恢复

适用于标准 single-host bundle 与 Docker 命名 home 卷。快照覆盖 Go/DeerFlow SQLite、WAL/检查点、DeerMem/FTS5、运行时与原生关联 journal、managed model 文件和 bundle 配置。仅排除 `.cache/uv`、`deermate/.cache/uv` 这两处可重建包缓存，不跟随外部链接。前端/nginx 缓存可重建；外部 Worker、设备原生进程与仓库、TLS 卷和 bundle 之外的凭据需单独清点。

归档包含私人资料、密码哈希和服务密钥，使用 0600 文件与 0700 目录，另行采用加密存储和离机副本。不要提交或公开快照。只恢复自己信任的归档：SHA-256 能发现损坏，不能认证来源。

## 导出与校验

先安排维护窗口，在工作台暂停来源/自动处理，核对执行中、待确认和未知工作，清点外部 env/bind/TLS/设备配置。然后在已安装部署依赖的可信主机运行：

```bash
python scripts/single_host_backup.py backup \
  --bundle /path/to/bundle --output /private-backups/deermate.tar.gz
python scripts/single_host_backup.py verify \
  --snapshot /private-backups/deermate.tar.gz
```

工具先关闭 nginx/edge，再停止 Go、Gateway 和前端写入方，检查没有其他容器写入同一 home。清单记录停写后的共同恢复点、snapshot ID、镜像 ID、上游 SHA、文件哈希与未完成身份。发现未确认操作时拒绝发布；只有已清点外部状态、接受核对责任后才使用 `--acknowledge-inflight`。这不是取消或重试命令。

成功或失败后默认恢复原先运行的服务；`--keep-stopped` 可保持维护状态。原卷不删除，失败的临时归档不发布；错误详情只写入输出目录中的 0600 私有诊断日志。输出必须位于原 home 卷和 bundle 之外；同盘副本仍不能防物理磁盘丢失。

## 恢复到新卷

先加载快照中不可变 ID 对应的四个镜像，使用匹配的工具/上游版本。控制面必须提供 `restore-quarantine-v1`；不假定旧镜像具备保护能力。目标 bundle 与 `${project}-restored-home` 必须不存在。

```bash
python scripts/single_host_backup.py restore \
  --snapshot /private-backups/deermate.tar.gz \
  --output /private-restores/deermate-review \
  --project deermate-recovery-review --port 2028
cd /private-restores/deermate-review
./start.sh
```

缺件、校验和错误、重复/越界文件、链接、非法格式或超限归档在目标卷写入前失败。不覆盖原卷；拷贝失败的部分目标保留供检查，工具不会启动它。恢复使用独立 loopback 入口，不恢复公网 edge。

默认 `DEERMATE_RESTORE_QUARANTINE=true`：可登录并查看原 owner、话题、任务、来源、有效记忆与未知身份；新聊天、执行、设备 poll/results、创建/修改事实与批准/扩展授权返回 `restore_quarantine`。仅另行允许本人遗忘与管理员撤销本人 Agent 授权，用来安全重施快照之后的删除/撤权；原认证、CSRF、owner 和 expected_revision/expected_version 检查保留。四种 Go 后台队列不启动，来源不自动同步，MCP profile 与遥测关闭，应用网络隔离。原记录和旧凭据的存在不等于当前允许派发。

`restore-receipt.json` 区分归档恢复点与校验/建卷/复制耗时；到服务就绪的时间单独记录，不能把复制时间当作完整恢复时间。

## 保持隔离时重施遗忘与撤权

恢复后先核对 `/health/ready` 的 `X-DeerMate-Restore-Quarantine: true`，保持所有自动队列与外部派发关闭。使用原 owner 登录，带原会话的 CSRF 和 `X-Expected-User-Id`，从快照后的私人删除/撤权记录找到事实与授权 ID，并读取恢复实例中的当前版本。只调用以下既有受限动作：

```text
DELETE /api/me/memories/FACT_ID
{"operation_id":"SAME_SAVED_FORGET_OPERATION","expected_revision":1}

POST /api/agent-authorizations/GRANT_ID/revocations
{"expected_version":1}
```

事实删除必须得到 completed 记录，再通过本人记忆搜索及来源查询确认不可召回。它同步执行内网确定性存储删除，模型 Provider/Native 仍不投递。响应丢失时保留相同 operation_id，查询 `/api/me/memory-operations/OPERATION_ID`；若显示 uncertain，修复存储连接、待该删除租期到期后按相同请求核对，不换 ID。撤权后读取授权清单确认 revoked；云端撤销不等于离线设备已停，仍需核对原设备。原 UI 的忘记/撤销入口使用这些相同动作，不能借此编辑、增加记忆或接纳执行。

删除/撤权未完成、旧来源撤销/密码轮换等其他快照后变更尚未核对时保持隔离。其他需要写状态的修复应另行设计受控维护步骤，不能先关闭隔离以启动后台队列。这里只开放两种限定安全动作；没有提供通用数据库编辑、来源恢复或自动重新授权。

## 重新开放前

- 核对账号、话题/任务/Native 根及未知 operation ID。外部进程不在备份中，先通过原设备确认执行是否还在继续，再核对原结果；不要创建替代任务。
- 对照快照之后的遗忘、来源撤销、密码/权限及设备变更。旧快照可能保存后来遗忘的内容；在隔离实例重新落实删除与撤销，并处理旧备份的保留期，再开放模型、聊天或采集。
- 另行恢复或重新登记外部密钥/设备，复核当前项目、期限和额度。确认原控制面不会同时派单。最后由操作者调整保护与接入配置；开关本身不是验证或新授权。
- 验收失败时停止新实例，保留原卷和快照；恢复后接纳了新工作，不能用旧数据库覆盖。

## 可复现演练

```bash
python scripts/verify_single_host_restore.py \
  --images-config .deermate/ack/config.yaml \
  --gateway-test-image YOUR_TEST_ONLY_GATEWAY_WITH_GIT \
  --work-dir .deermate/verification/restore-new \
  --receipt .deermate/verification/restore.json
```

测试镜像由 `deploy/testing/Dockerfile.restore` 在固定 Gateway 上添加 Git，并预置经官方SHA-256校验的tiktoken 0.12.0/cl100k_base缓存，再以network=none实际加载校验；仅供嵌入的 toy Worker；正式 Worker 仍在原设备。演练只创建带 fixture 名称的独立项目和合成账号，使用离线 Provider/Native 协议；覆盖实际 driver/Worker 两轮同根、冷备/未知身份、记忆遗忘、实际六种坏归档无目标写入、空卷 API 和零恢复派发。还会在快照后实际遗忘一个事实并撤销一个合成 status-only 授权，再于冻结中的恢复实例重施、核对计数。结束停止自身容器，保留源/目标卷及私人归档。实际结果见 STATUS，不将小型本地数据的测量当作云端容量或灾难恢复保证。
