# 真实秘书模型与派单验收

`scripts/verify_secretary.py` 使用 Go 登录和正式 DeerFlow run API，验证真实模型对话或模型自行选择 MCP 工具。它不调用本地 `deermate-local/submit` 验收入口，不注入假模型，不把配置存在当作执行成功。需要已配置的模型、已有管理员账户；dispatch 还需要已注册、可达的 Worker 和已有的可写 addition-test 演示项目。

先按 [Docker 指南](local-docker.md)启动服务，在模型设置保存并测试模型，再执行 Worker `doctor`。模型凭据继续保存在运行时加密目录；账号文件是仅包含 `email` / `password` 的 0600 JSON。不要把密钥或密码填到命令参数中。

```bash
# 会使用模型额度；使用实际 /api/models 中的 name，不是厂商模型 ID。
python scripts/verify_secretary.py --live \
  --url http://localhost:2026 \
  --account-file .deermate/local-docker/admin.json \
  --model YOUR_CONFIGURED_MODEL_NAME --mode chat \
  --state-dir .deermate/live-secretary/chat \
  --receipt .deermate/live-secretary/chat-receipt.json

# 会使用聊天模型和本机 Codex 额度，仅用于已注册的 addition-test 演示项目。
python scripts/verify_secretary.py --live \
  --url http://localhost:2026 \
  --account-file .deermate/local-docker/admin.json \
  --model YOUR_CONFIGURED_MODEL_NAME --mode dispatch \
  --worker-config .deermate/local-docker/worker.toml \
  --state-dir .deermate/live-secretary/dispatch \
  --receipt .deermate/live-secretary/dispatch-receipt.json
```

云端检查可改用实际 HTTPS origin 和该实例自己的私密账户文件。HTTP 只允许 loopback，公共 HTTP、URL 内嵌密码、查询参数和路径被拒绝。dispatch 使用操作员本机独立 Worker 的只读 SQLite 映射与鉴权 API 交叉核对，尚不是通用远程设备验收器。

对于已单独授权的[临时云到家庭链路](specs/m2-home-reverse-link.md)，在 dispatch 命令额外加入 `--ssh-controller-config /private/operator-controller.toml --ssh-worker home`。该操作员配置须从公网访问同一云主机的专用 reader 账号，沿用固定 known_hosts、Worker token/实例与授权期限。验收器在任何新模型 run 前做只读 SSH 往返：SSH host 必须是 HTTPS origin 的同一个公网 IP，远端实例必须与独立本机检查一致；失败则拒绝派单。当前此证据模式只支持公网 IP，不支持域名 origin。完整任务/原生证据也通过后，收据才保存 `cloud_to_home_verified: true` 和脱敏 `network_evidence`。单次 API 可达仍不等于任务成功。不要将云容器使用的私有桥接地址配置当成该公网观测路径。

验收脚本适用于 macOS/Linux。每个 state 目录使用独占进程锁，拒绝并发派单；原子写入使用独立临时文件，中断遗留文件不会阻止继续核对。脚本在请求前保存 thread、HTTP idempotency key、Worker key 和 owner；发送 run 前持久化 attempted 标记。重跑相同命令只读取并核对原 run，不重新派单。响应丢失、进程中断、失败 run 或无法唯一匹配时不会自动重放；先检查该 thread 的后台任务，已接纳任务可能继续执行。新建 state 目录意味着一个新的付费尝试，不是“重试”快捷方式。

成功 dispatch 要求模型先调用只读预检，再调用一次提交工具，没有额外工具调用；恰好一个 SQL 跟踪任务；原生实例/请求指纹/会话/attempt 与结果对应，独立测试退出码为 0，补丁只改 `answer.py` 且修复预期行。公开任务接口不暴露 remote handle/请求 key，验收器只读访问操作员本机 Worker 数据库以核对；MCP 桥接仍不直接读库。

模型的图执行步数限制包含 middleware 节点，不等于模型调用次数；本验收使用 128 个图步骤与读取期限，不宣称强制总费用配额。更完整的角色/项目权限、硬成本上限和自动路由仍需后续实现。普通测试不会调用真实模型，必须显式传 `--live`。

2026-10-28 第一轮包含云端聊天和本地模型派单/通知；低图步数失败与后续通过范围保留在[原收据](verification/secretary-live-2026-10-28.json)。随后用户批准临时接入，实际云端模型经受限 OpenSSH→Mac Worker 完成一个真实 Codex 修复，独立测试退出 0、通知 delivered。原工具快照未启用的 run 接纳零任务，保留原记录；激活后用独立有界 intent 完成验收。主动断线后的同 intent 重查没有新增模型或原生任务。见[新收据](verification/home-link-2026-10-28.json)、[STATUS](STATUS.md)和[功能规格](specs/m2-secretary-live-dispatch.md)。浏览器查看了任务结果，输入/流式体验仍需单独验收。
