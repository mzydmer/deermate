# 本地 Docker 运行与验收

这个配置在 Mac 上运行 Go 控制端、内部 DeerFlow Gateway、前端和 nginx，复用 ACK 的五个镜像（含初始化工具）。本机独立 Python Worker 调用已经登录的 Codex；容器经 MCP 和生成密钥的 SSH 开发服务连接 Worker。入口为 **[http://localhost:2026](http://localhost:2026)**，只绑定 `127.0.0.1`。

当前已验证页面、真实浏览器登录、真实 Codex 修复、独立测试和 Gateway 重启后的结果。2026-10-28 已用实际千问模型通过正式聊天 API 自行检查 Worker、提交 MCP 后台任务，真实 Codex 修复后独立测试通过，通知 delivered；该次模型入口为 HTTP，未另做浏览器输入派单验收。界面已加入 DeerMate 品牌、秘书首页和只读任务工作台，默认根地址重定向到受保护的 `/workspace`；原对话继续复用 DeerFlow，用户/登录与前端 API 由 Go 统一提供；管理页面为 `/admin`。见 [前端说明](../frontend/README.md)。

## 主机预检

适用：Docker Desktop for Mac、Python **3.12+**、Git、Helm **3.18+ 的 3.x**，以及 **PATH 中可用的 Codex CLI**。首次 `init` 用 `shutil.which("codex")` 查找 CLI；`up` 还会启动本机 Worker 与生成密钥的 SSH 开发连接。工作台启动不要求 Codex 已登录，实际执行前再单独核对认证。

当前实测 Intel Mac；Apple Silicon 需要修改生成 `images.yaml` 的 `platform` 为 `linux/arm64` 后重建，尚未验收。这个本地编排脚本暂不支持 Linux/Windows；Worker 本身仍支持 macOS/Linux。

先按 [Docker 官方 Mac 安装页](https://docs.docker.com/desktop/setup/install/mac-install/)安装并启动 Docker Desktop，遵循其许可与首次设置流程。缺少 Codex 时，按 [OpenAI 官方 CLI 安装说明](https://learn.chatgpt.com/docs/codex/cli#install-codex)安装；macOS 官方命令如下。安装后打开新终端，确认 CLI 在 PATH 中。

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

在源码目录准备独立 Python 环境：

```bash
git clone --branch main https://github.com/mzydmer/deermate.git
cd deermate
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' 'cryptography==48.0.1'
```

`cryptography==48.0.1` 满足当前 SSH 依赖，并有公开的 macOS universal2 wheel。它避免 Intel Mac 自动选择当前需要源码构建的更新版本；源码构建另需 OpenSSL 头文件/库和 Rust 工具链。该约束只用于此本地环境；升级时重新核对所选版本的平台 wheel。

运行主机预检。括号内任一命令失败都会非零退出，不会继续后面的检查：

```bash
(
  set -e
  command -v codex || { echo "缺少 Codex CLI，请先安装再执行 init。" >&2; exit 1; }
  docker info --format '{{.OSType}}/{{.Architecture}}'
  helm version --short
)
```

| 主机状态 | 预期结果与下一步 |
| --- | --- |
| PATH 中没有 Codex CLI | `command -v codex` 失败并显示安装提示；先安装。跳过预检运行首次 `init` 也退出 1，显示缺失及安装提示，不生成 profile 或镜像配置。 |
| CLI 可用，尚未登录 | 路径检查通过，可以运行 `init → build → up` 并初始化管理员；实际执行前检查登录。 |
| CLI 可用，已登录 | 可以启动；登录不代表模型权限或剩余额度已验证。可选真实验收仍需主动运行。 |

`command -v codex` 只核对路径。`codex login status` 单独核对认证；[官方命令说明](https://learn.chatgpt.com/docs/developer-commands?surface=cli#codex-login)中，其退出码为 0 表示存在登录凭据。它不提交模型任务。

## 首次启动工作台

预检通过后，在已激活的环境中运行：

```bash
(
  set -e
  python scripts/local_docker.py init
  python scripts/local_docker.py build
  python scripts/local_docker.py up
)
```

打开 **http://localhost:2026**。新 profile 显示首个管理员初始化页即通过启动检查；创建自己的管理员后完成安装。已有数据卷会显示登录页，不能据此认定是全新安装。需要聊天时再配置聊天模型。以上步骤不提交模型请求或 Native 轮次，**安装完成不要求运行 `verify --live`**。

`init` 可选 `--model YOUR_AVAILABLE_CODEX_MODEL` 指定有权限的 Codex 模型；省略则沿用原生配置。它不是聊天模型配置。`init` 按 [deploy/deerflow.lock](../deploy/deerflow.lock) 准备固定上游并生成本地配置，`upstream.json` 记录实际 SHA；已有 checkout 不匹配时停止并保留原目录。`build` 首次下载和编译较多依赖，之后复用 BuildKit 缓存，不需要每次启动重建。镜像仅载入本机 Docker，不上传 ACR。版本更换按[版本锁规范](deerflow-version.md)进行。

`up` 注册的本机 Worker 只允许自动生成的 `demo` 项目，并刷新一天有效的 SSH 注册；注册和连接检查不等于提交 Codex 任务。使用主机登录，不将 `.codex` 或用户凭据目录挂进容器。

## 可选真实执行验收

**本节会使用已登录 Codex 账号的模型额度，与首次启动分开。** 先检查认证；未登录时按 `codex login` 的官方流程登录，再重新检查：

```bash
codex login status
```

验收器读取私密 `.deermate/local-docker/admin.json`（JSON 键为 `email`、`password`）。尚未初始化管理员时，它会生成 `owner@example.com` 和独立随机密码并创建账号；如果已在网页创建管理员，先在本机编辑器中将可用的管理员邮箱/密码保存到该文件，并设权限 `0600`。它不会重置已有账号，也不使用公开默认密码。不要提交或粘贴该文件内容。

确认登录、管理员凭据及额度使用后，再单独执行：

```bash
python scripts/local_docker.py verify --live
```

该命令只在自动生成的 `.deermate/local-docker/demo-project` 中修复 `answer.py` 的一行加法错误：diff 应从 `return a - b` 改为 `return a + b`，Worker 独立运行 `python -m unittest discover -s tests -v`，退出码应为 0，并保留验证及 diff。它还检查重复请求不重复执行及 Gateway 重启后结果保留；私密收据保存在 `.deermate/local-docker/verification.json`。它不接管任意已有项目，也不修改 Codex 全局配置。聊天模型选工具的验收另行开展。

验收提交前将幂等键和线程保存到私密 `pending-verification.json`；若中途失败，后续验证使用相同请求恢复。成功后删除 pending 文件，下一次显式 `verify --live` 会创建一个新的演示任务。上游只允许每个远程任务有一条跟踪记录；重复提交得到带当前线程身份的 HTTP 409，Worker 任务及 attempt 不变。

## 日常启停与 Go 迁移

在已激活的仓库环境中，用 `python scripts/local_docker.py status` 查看状态、`python scripts/local_docker.py down` 停止、`python scripts/local_docker.py up` 再启动。`down` 仅停止这个 Compose 项目及其拥有的 Worker/SSH 进程，保留本地数据和命名卷。它不是任务取消命令；原生执行活动期间不要把重启当成安全取消，Worker 中断仍按显式恢复规则处理。端口已被其他实例占用时先确认占用者，不直接停止它。

主服务、登录、管理与前端 API 已切到 Go，内部运行时和 Worker/MCP/SSH 保留 Python。旧 profile 第一次 `up` 在原 home 卷生成 `data/backups/before-go-control.db` 在线备份，保留原账号密码、ID、任务归属和偏好；需要重新登录。管理页面为 [http://localhost:2026/admin](http://localhost:2026/admin)。四个常驻应用容器中，Go 与 Gateway 共享数据卷，Go 只接收 JWT bridge secret。

旧 profile 更新 Go 后，可单独运行 `python scripts/verify_go_control.py --restart`：它复用历史任务，不提交模型工作，验证账号、权限、会话撤销与重启持久化；临时验收账号最后停用以保留审计记录。它依赖历史数据，不是首次安装步骤。接口和限制见 [Go 后端说明](../backend/README.md)。

## 权限和数据

| 内容 | 位置与边界 |
| --- | --- |
| 本地配置、owner 密码、内部密钥、日志、有界收据 | `.deermate/local-docker/`，Git 忽略；密码/密钥文件 `0600` |
| 演示 Git 仓库、Worker 数据库/worktree | 同一私密目录内；Worker 只注册 `demo` 项目 |
| Gateway 数据库与会话、前端/nginx 缓存 | `deermate-local_*` 命名卷，`down` 保留 |
| 容器输入 | 显式允许的配置/本地适配脚本/专用 SSH 凭据经 Docker API 复制到 staging 卷；无宿主目录共享 |
| SSH 凭据 | init 将专用凭据复制为 UID 1000 的私密普通文件，Gateway 只读挂载 |
| 网络 | nginx 唯一宿主映射 `127.0.0.1:2026`；Worker `127.0.0.1:18777`；SSH 开发服务 `127.0.0.1:19822` |

运行服务均非 root、drop ALL capabilities、无 Docker socket。一次性 init 无网络，只有初始化这些命名卷所需的三项文件权限 capability。Compose CLI 在主机读取私密 env；前端只取得自己的会话 secret，没有 Worker token 或本地验收 key。

本地 extensions 配置由 init 从 staging 种子复制到 home 卷的普通私密文件，允许上游只读 API 创建同目录锁文件。每次 `up` 都重新应用宿主生成的种子；MCP 策略的持久修改应编辑 `.deermate/local-docker/config/extensions_config.json`，不要依赖网页中对这个受管理文件的修改。

`local_gateway.py` 仅在本地 profile 中加载；它的提交入口要求真实管理员登录、CSRF 和独立本地验收 key，且固定项目为 `demo`。它调用实际上游 MCP 后台包装器/SQL 服务，只替代模型选工具，不安装到 ACK 镜像。不要把此 profile 改成公网服务。

本机 Codex 对模型服务的调用依然遵循其账号和权限；worktree 不是操作系统沙箱。生成的 SSH 开发服务只支持指定 loopback 转发，不修改系统 sshd 或使用用户 SSH 私钥。真实家庭账户/OpenSSH、双机、NAT 和 ACK 需要后续独立验收。

## 实际证据与排障

[2026-11-16 首次启动收据](verification/local-onboarding-2026-11-16.json)记录公开无缓存依赖安装、缺 CLI 真实退出、五镜像构建和隔离初始化页。该次只做启动验收，新增模型请求与 Native 轮次均为 0；为保留已占用的个人端口，宿主映射为 22063，在本次 nginx 的隔离网络内验证 `localhost:2026`。这不替代下面的历史真实执行证据，也没有运行新的 `verify --live`。

[2026-10-26 收据](verification/local-docker-2026-10-26.json)保留 Docker/镜像身份、脚本哈希、14 项真实 Gateway/SSH/Codex 检查、独立测试及四项浏览器检查。浏览器在私有 Compose 网络中的隔离 Linux Chromium 上登录；没有访问锁屏 Mac 桌面或个人浏览器资料。[工作区截图](assets/local-workspace-2026-10-26.png)来自该次真实登录。

```bash
python scripts/local_docker.py status
docker compose --env-file .deermate/local-docker/compose.env \
  -f deploy/local/compose.yaml logs --tail 100 gateway frontend nginx
```

主机原生日志为 `.deermate/local-docker/worker.log`、`ssh.log`；日志可能包含任务内容，分享前自行检查。若 `2026/18777/19822` 已被其他服务占用，先确认占用者，不要直接杀进程。Docker Desktop 故障时先查看其状态；这个脚本不会重启整个 Docker 引擎或清理其他项目资源。

本次安装额外处理了下载瞬态故障、非 root 本地用户身份与前端 Corepack 启动问题，改动同步到 ACK 打包，见 [ADR 0005](decisions/0005-ack-control-plane.md)。[ACK 部署](ack-deployment.md)在云端凭据、ACR 及 kubeconfig 准备好后继续；本地验收不需要 AK/SK。
