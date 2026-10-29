# SSH 远程 Worker

状态：M2.2 直接 SSH 传输已实现。CLI、真实 stdio MCP、固定 DeerFlow 原生任务驱动及拒绝/恢复路径已用临时 SSH 服务验证。测试使用生成的密钥、同机 loopback HTTP Worker 和离线 Codex fixture；尚未部署到实际家用设备、配置生产 OpenSSH、打通 NAT 或验证远程聊天/UI。

## 连接方式

```text
DeerFlow / CLI
  → Python MCP / HTTPX
  → 控制端临时 loopback 端口
  → 已校验主机身份的 SSH
  → 远端 127.0.0.1:18777
  → 独立 DeerMate Worker
```

Worker 继续只监听 loopback。SSH 端口和 Worker 端口来自管理员注册配置；工具参数只接收项目、任务和幂等键。控制端不会通过 shell/SFTP 启动 Worker 或读取远端 token。SSH 两端能看到明文，模型提供方仍能读取发给它的上下文。

## 准备 Worker

在执行机器按[本地指南](local-worker.md)安装 Worker、注册可信项目并完成 Codex 登录。服务独立运行：

```bash
deermate --config /absolute/path/to/worker/deermate.toml serve
deermate --config /absolute/path/to/worker/deermate.toml capabilities
```

记下 `instance_id`，并通过已有可信渠道把 Worker 的 `api.token` 放到控制端专用私有文件。不要把 token 放进工具参数、README、Git 或模型会话。`instance_id` 是 SQLite 数据库/任务命名空间的标识，不是秘密；备份应同时保留数据库与身份。旧数据库首次升级会增加 metadata，不改写任务；身份损坏会明确拒绝启动。

## 注册控制端

```bash
python -m pip install -e '.[mcp,ssh]'
cp examples/ssh-controller.toml controller.toml
```

按 [ssh-controller.toml](../examples/ssh-controller.toml) 填写 `workers.home`：主机、SSH 用户/端口、专用 known_hosts、客户端私钥、复制的 API token、Worker 的 `expected_instance_id` 和你批准的 `expires_at`。所有文件引用使用绝对路径；示例有效期会过期，需要自行设定。

使用专用密钥和信任文件。从可信渠道取得并核对服务器公钥/指纹，然后写入 known_hosts。非标准 SSH 端口使用 `[host]:port` 形式。私钥和 token 为仅所有者可读写的普通文件（例如 `0600`）；known_hosts 不可由 group/other 写入。实现拒绝符号链接、空/超大凭据文件，且不读取默认 SSH 配置、agent 或其他身份，也不回退到密码、键盘交互、GSS 或 host-based 认证。

加密私钥可配置 `passphrase_env`，值为环境变量名，秘密值留在进程环境。DeerFlow 启动 MCP 时需要显式传入该变量，例如在服务器配置的 `env` 中使用 `"DEERMATE_HOME_KEY_PASSPHRASE": "$DEERMATE_HOME_KEY_PASSPHRASE"`。不要把口令字面量提交到配置。SSH extra 包含加密 OpenSSH 私钥所需的 bcrypt。

## 限制 SSH 账户

给专用账户配置仅到 Worker 端口的转发权限。OpenSSH 部署模板：

```text
Match User deermate
    AllowTcpForwarding local
    PermitOpen 127.0.0.1:18777
    PermitListen none
    AllowStreamLocalForwarding no
    MaxSessions 0
    AllowAgentForwarding no
    X11Forwarding no
    PermitTunnel no
    PasswordAuthentication no
    KbdInteractiveAuthentication no
```

管理员可在专用 authorized_keys 条目进一步限定：

```text
restrict,port-forwarding,permitopen="127.0.0.1:18777",command="/usr/bin/false" ssh-ed25519 REPLACE_WITH_PUBLIC_KEY
```

上面的 daemon 策略限制转发方向和目标，`MaxSessions 0` 禁用 shell/exec/subsystem。仅靠客户端选择不用 shell，不能限制被盗密钥在服务器上的权限。这是依据 [sshd_config](https://man.openbsd.org/sshd_config) 与 [authorized_keys](https://man.openbsd.org/sshd.8#AUTHORIZED_KEYS_FILE_FORMAT) 的部署模板；本次没有修改或验收真实主机的 OpenSSH 配置。按部署环境验证有效配置、账户隔离及服务启动方式。

## 使用 CLI 和 DeerFlow

```bash
deermate --config controller.toml --worker home doctor
deermate --config controller.toml --worker home capabilities
deermate --config controller.toml --worker home submit --project demo --key fix-001 --prompt 'Fix the failing test.'
deermate --config controller.toml --worker home status TASK_ID
deermate --config controller.toml --worker home events TASK_ID
deermate --config controller.toml --worker home diff TASK_ID
deermate --config controller.toml --worker home cancel TASK_ID
```

既有 `resume`、`answer` 也可通过已注册目标使用，恢复仍需显式确认。`--port` 仅用于本地 API；远程两个端口来自 controller 配置。capabilities 的 `remote: false` 描述 Worker 自身仍是 loopback API，CLI 附加 `connection.type: ssh` 描述这条连接。

DeerFlow 使用 [deerflow.ssh.extensions.json](../examples/deerflow.ssh.extensions.json)，将条目合并到已有 `extensions_config.json`，替换控制端 Python/配置/cwd 路径；继续启用[SQL 与 mcp_tasks](deerflow.md)。三个后台任务 raw tool 名保持不变：`submit_task`、`get_task_status`、`cancel_task`。另有无参数的只读工具 `check_worker_connection`；升级控制端包并重启 MCP 发现后可用，不加入 `task_toolsets`。

远程 MCP 返回 `instance_id:task_id` 绑定句柄，查询/取消必须原样使用；CLI 可以使用该句柄，或在显式 `--worker home` 下使用原生任务 ID。更换 Worker 数据库后，旧句柄不会被当作新实例的任务。上游固定驱动已验证这一格式。Worker HTTP API 和本地 MCP 的 32 字符 ID 保持不变。

## 连接预检

`doctor` 和 `check_worker_connection` 只读取经过鉴权的 `/capabilities`，不调用 Codex、不提交任务、不修改注册内容。检查请求期限 15 秒，随后 SSH 清理最多 2 秒；SSH 沿用专用密钥、固定 known_hosts 和 expected_instance_id，且每次操作前都验证协议。响应上限 32 KiB，仅返回已知字段；主机、用户名、凭据和配置路径不会进入报告。

成功报告包含 `status: reachable`、UTC `checked_at`、`connection.type: ssh`、`identity.ssh_host_key: verified`、`identity.worker_instance: pinned` 和协议能力。失败报告为 `status: blocked` 及 `error.code` / 固定错误说明。CLI 对应退出码 0 / 1；MCP 的 blocked 是正常结构化检查结果，参数错误才是工具错误。

常见错误码：`configuration_invalid`、`not_enrolled`、`grant_disabled`、`grant_expired`、`enrollment_changed`、`credential_unavailable`、`credential_invalid`、`host_key_rejected`、`authentication_rejected`、`worker_identity_mismatch`、`unsupported_protocol`、`unsupported_adapter`、`invalid_response`、`timeout`、`unavailable`。修正原因后显式重查；变更 enrollment 字段需重启原 MCP 进程。

两个结果始终保留 `execution_readiness: not_checked` 和 `task_outcome: not_checked`。本地连接只观察应用实例 ID，不宣称远端身份固定。连接成功是时间点上的观测，不代表 Codex 登录、容量、项目授权或下一次请求必定成功；受阻也不代表已接纳任务停止。实际云到家庭受限链路与模型派单已有单独验收；其他主机/网络仍需各自验证。[规格与测试范围](specs/m2-worker-preflight.md)。

## 断线、撤权和轮换

- 每个 HTTP 操作前重新读取注册权限和凭据，调用 Worker capabilities 核对实例身份、协议和必要操作。不兼容时在修改请求前拒绝。禁用、删除或到期的注册拒绝新操作并关闭缓存隧道。配置字段变化需要新 CLI/MCP 进程；工具不能修改注册内容。
- SSH 连接默认存活 60 秒，达到期限或注册到期会关闭；正在执行的受限 HTTP 操作先结束。凭据/known_hosts 内容变化会要求新认证。控制端重连只恢复传输，不重发 HTTP 修改请求。
- 服务端删除 authorized key 不会主动断开已有认证连接；立即撤权还需终止对应 SSH 会话。可先禁用控制端注册，再撤销/轮换服务端公钥和 token，最后更新控制端私有文件并重新启用。token 轮换需配合 Worker 重启，因为其 API 在启动时加载 token。
- 撤权不代表任务已停止：已接纳任务（包括排队任务）仍按 Worker 策略执行。要停止它们，使用仍有权限的本地管理员控制；权限过期后远程查询、取消也会被拒绝。
- 响应丢失时结果未知。显式重试提交必须沿用同一幂等键；状态查询、中断和继续沿用原任务。连接失败与未确认取消不映射为任务失败或停止。

## 验证与剩余范围

```bash
python -m pip install -e '.[dev]'
python -m pytest -q tests/test_ssh.py --ssh-receipt .deermate/verification/ssh.json
DEERMATE_DEERFLOW_CHECKOUT=/path/to/pinned/deer-flow python -m pytest -q tests/test_deerflow_compat.py
```

SSH 测试使用真实 SSH/HTTP/MCP 协议，生成专用临时密钥，限定转发目的地并拒绝 session。覆盖正确路径、错误主机密钥/客户端密钥/token/实例、密钥轮换、加密私钥、文件权限、注册撤销/到期、空闲连接过期、断线重连、接纳后丢响应及实例绑定。固定上游驱动检查同时运行本地与 SSH 两种绑定。

收据仅在所选测试会话通过后写入，记录有界测试结果、依赖版本和源码哈希，不含密钥、token、地址、私密路径或原始 trace。上述协议收据不证明实际设备部署。后续[临时家庭链路收据](verification/home-link-2026-10-28.json)另行验证云端 OpenSSH 限制、Mac 出站连接、真实模型派单/通知及结果 UI；通用 NAT/配对、硬崩溃和实际到期观察仍待完成。规格见 [M2.2](specs/m2-ssh-worker.md)，取舍见 [ADR 0004](decisions/0004-ssh-loopback-transport.md)。

## 可选临时出站接入

当家庭 Worker 不可从云端直连时，可按 [ADR 0010](decisions/0010-temporary-home-reverse-link.md)单独配置出站链路：Mac → 云端 reverse-only 账号/loopback 18778 ← 云端 MCP reader-only 账号 → Mac Worker loopback 18777。两组独立密钥、固定主机/Worker 身份和最多 24 小时租期；无 shell/sudo/PTY/Agent/X11，Mac 系统 sshd 不变。服务器 timer 到期移除密钥/云端凭据并终止专用会话；已接纳任务仍按 Worker 策略执行。

已批准的一个部署通过实际权限限制、连接恢复和真实模型/Codex/独立测试/通知验收。固定租期内的 connector 仅重建传输，认证/信任失败即停，不重放任务。脚本与凭据是操作员私人部署文件；目前没有通用一键配对或重启守护。两条 SSH 均在可信云主机终止，云端应用/管理员可读取内容。见[实际范围与剩余工作](specs/m2-home-reverse-link.md)。
