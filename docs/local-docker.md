# 本地 Docker 运行与验收

这个配置在 Mac 上运行 DeerFlow Gateway、前端和 nginx，复用 ACK 的四个镜像。本机独立 Python Worker 调用已经登录的 Codex；容器经 MCP 和生成密钥的 SSH 开发服务连接 Worker。入口为 **[http://localhost:2026](http://localhost:2026)**，只绑定 `127.0.0.1`。

当前已验证页面、真实浏览器登录、真实 Codex 修复、独立测试和 Gateway 重启后的结果。按本轮用户选择，秘书聊天模型暂不配置；页面中的自然语言派单、模型通知、专职路由还未验收。界面已加入 DeerMate 品牌、秘书首页和只读任务工作台，默认根地址重定向到受保护的 `/workspace`；原对话与认证继续复用 DeerFlow。见 [前端说明](../frontend/README.md)。

## 在这台 Mac 上使用

Docker Desktop 已安装在 `~/Applications/Docker.app`，用户 CLI 在 `~/.docker/bin`；新的登录 shell 可直接运行 `docker`。当前服务已启动，打开上面的本地地址即可。

首个管理员由验收程序创建，邮箱为 `owner@example.com`。**随机密码只保存在 `.deermate/local-docker/admin.json`**（权限 `0600`），在本机打开该文件查看；不要提交或粘贴到公共 issue。首次在其他机器执行 `verify` 也会生成独立密码，不使用公开默认密码。

在仓库目录运行：

```bash
source .venv/bin/activate
python scripts/local_docker.py status
python scripts/local_docker.py down
python scripts/local_docker.py up
```

`down` 仅停止这个 Compose 项目及其拥有的 Worker/SSH 进程，保留本地数据和命名卷。已实际执行完整 `down`/`up`：三个容器重新健康，原账号可登录，SQL 结果、Worker 实例/会话/attempt 保留，新 SSH capabilities 查询通过，没有新模型任务。它不是任务取消命令；原生执行活动期间不要把重启当成安全取消。Worker 运行中断仍按既有显式恢复规则处理。`up` 刷新一天有效的本地 SSH 注册；长期停留后连接到期时重新执行它。

## 从源码搭建

适用：Docker Desktop for Mac、Python **3.12+**、Git、Helm **3.18+ 的 3.x**，以及本机已安装并按官方流程登录的 Codex。当前实测 Intel Mac；Apple Silicon 需要修改生成 `images.yaml` 的 `platform` 为 `linux/arm64` 后重建，尚未验收。这个本地编排脚本暂不支持 Linux/Windows；Worker 本身仍支持 macOS/Linux。

Docker 安装程序来自 [Docker 官方 Mac 安装页](https://docs.docker.com/desktop/setup/install/mac-install/)。遵循其许可与首次启动流程；本仓库不重新分发 Docker Desktop。本次采用用户目录安装；图形首次设置界面因 Mac 锁屏没有操作，后台 daemon 和实际容器已验证可用。

```bash
git clone --branch feat/deermate-workspace https://github.com/mzydmer/deermate.git
cd deermate
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
docker version
codex login status

python scripts/local_docker.py init --model YOUR_AVAILABLE_CODEX_MODEL
python scripts/local_docker.py build
python scripts/local_docker.py up
python scripts/local_docker.py verify --live
```

`--model` 指定你有权限的 Codex 模型；省略则使用原生配置。本次实测 `gpt-6.1-sol`。`init` 会准备固定上游并生成本地配置；`build` 首次下载和编译较多依赖，之后复用 BuildKit 缓存，不需要每次启动重建。没有上传镜像到 ACR。

`verify --live` **会使用 Codex 模型额度**：只在自动生成的 `demo-project` 中修复 `answer.py` 的一行加法错误，由 Worker 独立运行 unittest 并返回 diff。它不接管任意已有项目，也不修改 Codex 全局配置。使用已有主机登录，不将 `.codex` 或用户凭据目录挂进容器。

验收提交前将幂等键和线程保存到私密 `pending-verification.json`；若中途失败，后续验证使用相同请求恢复。成功后删除 pending 文件，下一次显式 `verify --live` 会创建一个新的演示任务。上游只允许每个远程任务有一条跟踪记录；重复提交得到带当前线程身份的 HTTP 409，Worker 任务及 attempt 不变。

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

[2026-10-26 收据](verification/local-docker-2026-10-26.json)保留 Docker/镜像身份、脚本哈希、14 项真实 Gateway/SSH/Codex 检查、独立测试及四项浏览器检查。浏览器在私有 Compose 网络中的隔离 Linux Chromium 上登录；没有访问锁屏 Mac 桌面或个人浏览器资料。[工作区截图](assets/local-workspace-2026-10-26.png)来自该次真实登录。

```bash
python scripts/local_docker.py status
docker compose --env-file .deermate/local-docker/compose.env \
  -f deploy/local/compose.yaml logs --tail 100 gateway frontend nginx
```

主机原生日志为 `.deermate/local-docker/worker.log`、`ssh.log`；日志可能包含任务内容，分享前自行检查。若 `2026/18777/19822` 已被其他服务占用，先确认占用者，不要直接杀进程。Docker Desktop 故障时先查看其状态；这个脚本不会重启整个 Docker 引擎或清理其他项目资源。

本次安装额外处理了下载瞬态故障、非 root 本地用户身份与前端 Corepack 启动问题，改动同步到 ACK 打包，见 [ADR 0005](decisions/0005-ack-control-plane.md)。[ACK 部署](ack-deployment.md)在云端凭据、ACR 及 kubeconfig 准备好后继续；本地验收不需要 AK/SK。
