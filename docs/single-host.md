# 最低成本单机部署

个人试运行可把同一套 Go 主服务、Python DeerFlow、前端、nginx 放到一台 Linux 服务器，用 Docker Compose 启动。原生 Codex 仍在家中机器上，云端先不注册 Worker。无需 ACK、NAT 网关、负载均衡、ACR 或托管数据库；复用服务器套餐自带的系统盘和网络。既有 [ACK 包](ack-deployment.md)仍可选。

本轮基础页面/API 已验收规格：**2 vCPU / 2 GiB 内存 / 40 GiB 系统盘，amd64 Ubuntu 24.04**。预编译镜像在本地构建后搬运；小服务器只运行容器，不编译 Next.js。四个常驻容器上限合计 1472 MiB；实际轻量云主机已完成基础验收，内核可见总内存 1613 MiB；这不代表模型负载已验收。单人、低并发起步，完整 Agent 工作量需另测。磁盘应保留升级和 SQLite/WAL/附件空间，不把 40 GiB 都分配给数据。

## 在构建机准备

先具备本仓库 deploy 依赖、Docker、Helm 3.18+（3.x）与固定上游 checkout。可以复用与当前源码一致的已有四镜像，或用现有 `scripts/ack_deploy.py build` 构建它们；`deermate-tools` 只在构建流程中使用，单机运行不需要它。

已运行本地 profile 时：

```bash
python scripts/single_host.py \
  --images-config .deermate/local-docker/images.yaml \
  --output .deermate/single-host/bundle
```

`--images-config` 只用于选镜像及固定上游，原来的模型/Worker 凭据和运行数据不会复制。生成空模型/MCP 配置、新的内部密钥和可搬运的 Compose 包；已有输出目录会拒绝覆盖。可用 `--project`、`--port` 指定隔离实例，默认 `deermate-single` / `2027`，与现有本地 2026 入口分开。

镜像必须与服务器架构一致；当前最低成本候选是 amd64。将 bundle.json 中列出的四个镜像用 `docker save --output images.tar IMAGE1 IMAGE2 IMAGE3 IMAGE4` 导出，传到服务器后 `docker load --input images.tar`。可压缩后传输、再解压导入；准备足够临时磁盘空间。通过已核对主机身份的 SSH/SCP 搬运，不关闭主机公钥校验。传输的是镜像和新生成的应用配置，**不要打包整个 `.deermate`、`.codex`、用户 SSH 目录或原运行数据库**。

## 在服务器启动

云资源购买、服务条款、SSH 访问设置在准备包之外完成。在 Ubuntu 24.04 上没有 Docker 时，可从系统软件源安装 `docker.io` 与 `docker-compose-v2`；确认 Docker daemon 和 Compose 插件可用。按服务器实际权限执行，勿直接给公共用户 Docker 管理权限。

将生成的 bundle 放入仅部署管理员可读的目录，保留 `.env`、`*.env` 的 0600 权限。加载四个镜像后进入该目录：

```bash
./start.sh
```

脚本通过 Docker API 将允许的静态配置复制到专用命名卷，然后启动服务。不挂载宿主目录或 Docker socket；常驻服务非 root、drop ALL、no-new-privileges，日志按大小轮转。init 只初始化卷权限及缺失的 MCP seed，不重置已有账户或扩展配置。Go 只收到自己的 JWT bridge secret。

初次从个人电脑访问，使用已建立的服务器 SSH 账户：

```bash
ssh -N -L 2027:127.0.0.1:2027 YOUR_SSH_TARGET
```

打开 `http://localhost:2027`，创建首个管理员，然后在模型设置页添加实际 endpoint/model/key。端口 2027 只绑定服务器 loopback；无需放行公网 Web 端口。浏览器本地 HTTP 经 SSH 加密传输到服务器，服务器管理员与应用仍可读应用数据；此配置不宣称端到端加密或多租户隔离。公网域名/TLS 属于单独配置，必须同时调整 Go Host/Origin allowlist，不能只开放端口。

同时使用原 localhost:2026 实例时，使用独立浏览器 profile 访问云端转发入口（本轮使用 Codex 内置浏览器，与原 Chrome 分开）：Cookie 不按端口隔离，两套 localhost 应用可能互相覆盖登录 Cookie。固定上游 nginx 会把 127.0.0.1 重定向到 localhost，因此换一种 loopback 写法也不能隔离登录 Cookie。账户和数据卷仍分别保存，不会因此合并。

## 运维与边界

```bash
docker compose ps
docker compose logs --tail=100 gateway control
docker compose stop
docker compose start
```

应用账户、SQLite 与 managed-model 密钥保存在 `home` 命名卷，保留该卷和 bundle 的内部密钥。升级先做可恢复的 SQLite 在线备份/一致性备份；不要在运行中只拷贝一个 db 文件，也不要用 `down --volumes` 日常升级。当前 bundle 不自动备份、不自动更新镜像，也不自动连接家中 Worker。

模型调用单独计费。首次购买活动/优惠券不等于同价续费；确认首年价格、续费价格、券是否可分次使用和自动续费状态。单机停机或容器停止未必停止套餐计费。真实云主机、网络、磁盘余量、模型调用与家庭链路需在目标服务器分别验收；[当前状态](STATUS.md)记录实际证据范围。

## 实际云端验收 · 2026-10-27

北京轻量 2 核/2 GiB/40 GiB、Ubuntu 24.04，Docker 29.1.3 / Compose 2.40.3，四个固定镜像已加载并健康运行。18 项初始接口检查（含 40 次、并发上限 4 的只读请求）和 10 项受控整机重启后检查通过；浏览器实际登录工作台和 Go 管理页，原会话/owner 在重启后保留。请求后与重启后主机 available 约 695/831 MiB，磁盘剩余约 26.9 GiB，没有观察到 OOM。

此范围不含模型调用、家庭 Worker、完整自动路由或公网域名/TLS。初始模型/MCP 仍为空；新 owner、内部密钥和访问资料留在私人目录。临时 SSH 新登录权限为 24 小时；到期不自动终止已经认证的会话，结束访问时应关闭对应隧道。不要为了继续部署而直接延长权限或关闭主机身份校验。详见[验收收据](verification/single-host-cloud-2026-10-27.json)。
