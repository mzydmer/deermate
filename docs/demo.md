# Gateway → MCP → SSH → Worker 演示

本演示启动固定版本的真实 DeerFlow Gateway、SQLite 跟踪服务、MCP 子进程、SSH 服务和独立 Worker。任务提交、后台查询、取消与结果都经过同一条链路。原生执行端使用离线 Codex 协议 fixture，不消耗模型额度。

[已捕获事件回放](assets/gateway-ssh-demo.html)是可离线打开的单文件 HTML，支持播放、暂停、单步和速度选择；GitHub 源码页需下载后用浏览器打开。它展示实际验收事件、修复 diff 和独立测试结果，不是产品仪表盘。[JSON 收据](verification/gateway-ssh-2026-10-25.json)可用于核对源代码和运行版本。

## 准备

支持 macOS/Linux。DeerMate 使用 Python 3.11+；完整上游 Gateway 使用独立 Python 3.12+ 环境。以下命令从 DeerMate 仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' 'uv==0.13.5'
git clone https://github.com/bytedance/deer-flow.git .deermate/verification/deer-flow
git -C .deermate/verification/deer-flow checkout a1b89d0432de4e45adc59f512cb25bb386ea1e51
uv sync --project .deermate/verification/deer-flow/backend --frozen --no-default-groups --python 3.12
```

已有该 checkout/环境时直接复用，不需要重复创建。脚本要求固定提交且上游 `backend` 未修改。macOS Intel 的固定 cryptography 依赖可能需要 OpenSSL 开发库，见 [Gateway 环境说明](deerflow.md#gateway-与-sql-验收)。

## 一条命令运行

```bash
python scripts/verify_deerflow_gateway.py \
  --checkout .deermate/verification/deer-flow \
  --gateway-python .deermate/verification/deer-flow/backend/.venv/bin/python \
  --transport ssh \
  --receipt .deermate/verification/gateway-ssh.json \
  --replay .deermate/verification/gateway-ssh.html
```

通过时输出 21 条 `PASS`，并生成收据与回放。用浏览器打开生成的 HTML 即可回看。默认临时状态在结束后删除，自己启动的进程会关闭。可加 `--work-dir /new/empty/path` 保留排错日志，目录必须尚不存在；该目录含临时密钥、token、数据库和原始日志，不要提交或上传。

`--transport local` 保留原有 HTTP 路径，输出 14 项检查。CI 分别运行两种模式，仅上传生成的 JSON/HTML，不上传原始状态。

## 演示过程

1. 创建临时项目、Worker 数据库、SSH 主机/客户端密钥和 known_hosts；注册真实 Worker 实例 ID。监听均为 `127.0.0.1`，不修改用户 SSH 或系统服务。
2. 从实际 Gateway 发现的提交工具创建任务，SQL 保留 `instance_id:task_id`，SSH 端记录认证和获准端口转发。
3. 更换 Gateway 进程，接续同一任务/原生会话；通过上游原始 HTTP 取消接口获得 Worker 确认。
4. 修复 `add(a, b)` 的减法错误并取得通过的独立验证；另一次错误修复仍返回失败。验证结果经 Gateway 返回，原始 diff 由脚本的只读 Worker 观察连接取得；既有 MCP 工具只返回有界证据和 diff 可用性。
5. 只停止 SSH：Gateway 跟踪降级、Worker 继续。恢复同一 SSH 身份后接续原任务；禁用注册时取消失败，恢复注册后完成此前明确请求的取消。
6. 停止并重启 Worker：任务进入显式恢复状态，原生身份保留；核对没有多建原生会话或执行轮次。

## 证据边界

只有“聊天模型选工具”由带单次密钥的测试提交入口替代；应用、lifespan、SQL 服务、后台轮询、MCP 调用、SSH 协议及 Worker 均实际执行。测试入口只存在于验收子进程。

这是同机真实协议演示，没有连接真实 OpenSSH 账户、另一台设备、NAT 或中继。未配置聊天模型，所以上游通知 run 在模型装配阶段失败；本次验收对象是任务 HTTP/SQL 结果。回放不是产品聊天 UI，也不证明真实模型、硬崩溃或历史数据库升级。下一步是已注册设备上的受限账户部署验收。

规格见 [M2.3](specs/m2-gateway-ssh-demo.md)，实际设备配置见 [SSH 指南](ssh-worker.md)，当前交付和 CI 见 [STATUS](STATUS.md)。
