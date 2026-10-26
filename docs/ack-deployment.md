# 在阿里云 ACK 快速部署 DeerMate

默认拓扑：**ACK 上的页面 → Go 主服务/登录/管理 API → 内部 DeerFlow → Python MCP → SSH → 家中 Worker / Codex**。先安装云端界面，再启用 Worker 注册。复用固定上游 `a1b89d0` 的官方 Helm Chart、前端和后端 Dockerfile；Go 镜像独立构建；DeerFlow 与 Worker/MCP/SSH 保留 Python。

本包提供可执行脚本与验证，不代表已经部署到你的 ACK。没有创建集群、连接私人设备或调用真实模型。

## Go 控制端拓扑

同一 Gateway Pod 内运行 Go 控制端（8080）和 Python Agent 运行时（仅 `127.0.0.1:8001`）；原 ClusterIP Service 的 targetPort 改为 Go。页面 SSR 和 nginx API 请求都先到 Go，`/admin` 提供用户/角色管理。共用原 20 GiB RWO home 的相同 subPath，保持单副本/Recreate；Go 只引用已有 auth Secret 的 `AUTH_JWT_SECRET`，不继承模型/Worker 密钥。

首次在已有 ACK 数据卷升级前，先创建云盘/PVC 快照或 SQLite 在线备份并验证可恢复；本地 profile 的自动备份不等同于 ACK 云盘备份。原用户 UUID/密码/任务记录保持兼容，浏览器需重新登录。快速配置仍只面向 localhost port-forward；自定义 TLS/域名需显式调整 Go origin/host allowlist。见 [Go 后端说明](../backend/README.md)。

## 前置条件

- 已有 ACK 托管集群，使用普通 Linux ECS 节点；本快速配置不覆盖 ACK Serverless/ECI/ACS 虚拟节点。
- 本机或构建机有 Python 3.12+、Git、Docker/Buildx、**Helm 3.18+ 的 3.x 版本**和 kubectl。Worker 自身仍支持 Python 3.11+；Helm 4 不在本包验证范围。
- kubeconfig 已配置；用 `kubectl config get-contexts` 找到明确的 ACK context。脚本每次操作都传入该 context。
- 具备目标 namespace 的部署权限及首次创建 namespace 的权限；每个 namespace 部署一套该 Chart，其内部 Service 名固定。
- ACR 实例/命名空间及构建推送、集群拉取权限。建立五个仓库：`deermate-control`、`deermate-gateway`、`deermate-frontend`、`deermate-nginx`、`deermate-tools`；允许自动建仓时可由首次推送创建。
- ACK CSI 云盘 StorageClass，例如 `alicloud-disk-topology-alltype`。脚本验证 provisioner 为 `diskplugin.csi.alibabacloud.com`，申请 20 GiB RWO 云盘；不把 SQLite 放在 NAS。资源按阿里云账户规则计费。
- 一个从 ACK 可访问、支持工具调用的 OpenAI-compatible 模型 endpoint/model ID 和 API key；使用你实际开通的模型，不在脚本中假设某个商业模型已可用。

镜像和模型服务均需要相应网络可达性。构建时需要访问上游 GitHub、镜像源和依赖源；运行时使用你推送到 ACR 的五个镜像。

## 第一次部署

从主线安装：

```bash
git clone --branch main https://github.com/mzydmer/deermate.git
cd deermate
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[deploy]'

python scripts/ack_deploy.py init \
  --registry registry.cn-hangzhou.aliyuncs.com/YOUR_NAMESPACE \
  --context YOUR_ACK_CONTEXT
```

`registry` 应填你实际 ACR 的完整仓库前缀；企业版可使用实例域名。构建与集群拉取必须能访问这个地址。修改生成的 **`.deermate/ack/config.yaml`**，至少填写：

```yaml
model:
  model: YOUR_TOOL_CALLING_MODEL_ID
  base_url: https://YOUR_PROVIDER_ENDPOINT/v1
```

保留 `worker.enabled: false` 可先完成云端安装。配置、生成文件与凭据都位于 Git 忽略目录；模板见 [config.example.yaml](../deploy/ack/config.example.yaml)。模型 key 使用交互输入，不要写入 YAML：

```bash
python scripts/ack_deploy.py model-key
docker login registry.cn-hangzhou.aliyuncs.com
python scripts/ack_deploy.py build --push
python scripts/ack_deploy.py registry-secret --username YOUR_ACR_USERNAME
python scripts/ack_deploy.py deploy
python scripts/ack_deploy.py open
```

两个提示分别输入模型 API key 和 ACR 拉取密码。`docker login` 使用 ACR 实际登录用户名/密码。`build --push` 首次下载、编译固定上游和前端，耗时取决于网络和构建机；它只需在镜像版本变更时运行。默认构建 `linux/amd64`，ARM 节点需将 `platform` 改为 `linux/arm64` 并重新构建。

打开 **[http://localhost:2026](http://localhost:2026)**，按 DeerFlow 引导创建首个管理员并登录。port-forward 只绑定本机，按 Ctrl-C 停止；没有自动创建公网负载均衡或开放 Worker API。

配置与镜像就绪后，再次安装/更新只需：

```bash
python scripts/ack_deploy.py deploy
```

## 接入家里的 Worker

先按 [Worker 指南](local-worker.md)在家中机器安装、登录真实 Codex、注册项目并启动 Worker，再按 [SSH 指南](ssh-worker.md)建立受限 SSH 账户，核对主机指纹。**当前需要 ACK 能直接连接的 SSH 地址或你已有的可信网络连接；本包没有 NAT 穿透、反向隧道或自动路由器配置。**

在本地 `.deermate/ack/credentials/` 放入从可信渠道取得的三份文件：

| 文件 | 内容 |
| --- | --- |
| `client.key` | 专用 SSH 私钥 |
| `known_hosts` | 核对过的主机公钥；非标准端口使用 `[host]:port` |
| `api.token` | 该 Worker 的 API token |

这三份文件设置为 `chmod 600`；不要复制整个用户凭据目录。修改配置：

```yaml
worker:
  enabled: true
  host: YOUR_REACHABLE_SSH_HOST
  port: 22
  username: deermate
  worker_port: 18777
  expected_instance_id: YOUR_ACTUAL_32_HEX_INSTANCE_ID
  expires_at: YOUR_APPROVED_UTC_EXPIRY
  passphrase_env: null
```

`expires_at` 使用带时区的实际到期时间，例如 ISO 8601 的 `...+00:00`。加密私钥的口令另存为仅所有者可读的 `credentials/passphrase`，设置 `passphrase_env: DEERMATE_SSH_KEY_PASSPHRASE`。

```bash
python scripts/ack_deploy.py deploy
python scripts/ack_deploy.py probe-worker
```

`probe-worker` 从 Gateway Pod 调用现有 SSH CLI 只读查询 capabilities，核对实例与项目，再在页面发起一个已授权项目的任务。它不能代替真实模型选工具、任务结果和通知的后续验收；本次开发没有你的设备信息，未执行此步骤。

## 部署内容与运维

- 三个应用 Deployment：Gateway（含嵌入式运行服务和 DeerMate MCP）、Next.js 前端、nginx；全部非 root，无自动挂载的 Kubernetes API token。
- 一个 20 GiB 云盘 PVC：持久化 SQLite、会话检查点和 DeerFlow home。Gateway 固定单副本、`Recreate` 更新，会有短暂停机；不要手动扩容或加 HPA。
- 保留 upstream setup/login；不设置 `DEER_FLOW_AUTH_DISABLED`。默认不创建 provisioner、执行 Pod/RBAC、PostgreSQL、Redis 或 Ingress；秘书没有配置云端本地 bash/文件工具。
- 模型、ACR 与 Worker 凭据用 Kubernetes Secret；SSH 私钥/token 经非 root init container 复制成内存卷中的 0600 普通文件。每次 `deploy` 重启 Gateway，使 Secret 轮换生效。
- MCP/skills 扩展配置以 Helm 为准，每次启动重新复制配置 seed；控制台手改这些配置会被后续部署覆盖。
- Helm `--atomic --wait` 检查安装/升级结果，但不回滚脚本单独更新的 Secret，也不保证外部 Worker 任务已停止。

查看状态和日志：

```bash
python scripts/ack_deploy.py status
kubectl --context YOUR_ACK_CONTEXT -n deermate logs deployment/deermate-deer-flow-gateway -c gateway --tail=100
```

排错：`ImagePullBackOff` 检查 ACR 地址/拉取 Secret；PVC Pending 检查 CSI、节点可用区、云盘配额与调度；SSH 失败检查已核对的主机密钥、网络、注册期限、专用密钥和实例 ID。MCP 工具没有发现时，确认已启用 Worker、重新 deploy，并在正确的项目范围调用。

公网域名属于可选独立步骤：[Ingress 示例](../deploy/ack/ingress.example.yaml)要求已有 ALB IngressClass 和同 namespace 的 TLS Secret；完成私人首个管理员设置后，按自己的 ACK ALB/TLS 配置调整并显式应用。部署脚本不会替你创建 ALB。

卸载应用：

```bash
helm --kube-context YOUR_ACK_CONTEXT -n deermate uninstall deermate
```

本包为 home PVC 和应用密钥 Secret 设置 `helm.sh/resource-policy: keep`；外部 provider/Worker/ACR Secret 也不属于 Helm 删除范围。备份需同时保留持久数据和密钥。不要以删除 namespace 作为日常卸载；删除 PVC 时，云盘是否保留取决于 StorageClass/PV 的回收策略。

## 验证与来源

当前实际 Chart 与本地部署策略检查合计 19 项通过；常规回归 91 passed、6 skipped。生成 Dockerfile 的下载重试/HTTPS、Gateway 的真实 UID 1000 身份及直接 Node 启动前端已从本地运行反馈同步进 ACK 包，见 [ADR 0005](decisions/0005-ack-control-plane.md)。

历史 [CI 40266316155](https://github.com/mzydmer/deermate/actions/runs/40266316155) 在 `ca23f2c` 六个 job 成功，构建四个 linux/amd64 镜像并验证非 root Gateway 就绪、匿名拒绝、MCP/SSH 导入及凭据复制；[原始证据](verification/ack-package-2026-10-25.json)不代表本轮打包修正的 CI。后续 [CI 40295603001](https://github.com/mzydmer/deermate/actions/runs/40295603001) 在 `bf02720` 六个 job 全部通过，新增用户身份和前端登录 HTML 探针，[保存证据](verification/ack-package-2026-10-26.json)的 ZIP digest 已核对；这是前端 overlay 之前的历史打包证据。本轮 overlay 的运行/CI 范围见 [STATUS](STATUS.md)。

同源镜像已在 [Mac 本地 Docker](local-docker.md)完成页面、真实浏览器登录及真实 Codex/SSH 任务验收，保留[独立收据](verification/local-docker-2026-10-26.json)。这不代表实际 ACK 安装或云端到家庭链路已通过。ARM 镜像、ACR 推送、ACK 和真实家庭设备仍需在用户环境验收。

参考：[ACK 云盘 StorageClass](https://www.alibabacloud.com/help/zh/ack/ack-managed-and-ack-dedicated/user-guide/use-dynamically-provisioned-disk-volumes)、[ACK 私有镜像拉取](https://www.alibabacloud.com/help/en/ack/ack-managed-and-ack-dedicated/user-guide/faq-about-applications)、[固定上游 Helm Chart](https://github.com/bytedance/deer-flow/tree/a1b89d0432de4e45adc59f512cb25bb386ea1e51/deploy/helm/deer-flow)、[Helm 3 post-renderer](https://v3.helm.sh/docs/topics/advanced/#post-rendering)、[kubectl port-forward](https://kubernetes.io/docs/tasks/access-application-cluster/port-forward-access-application-cluster/)。
