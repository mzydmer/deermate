# DeerMate v0.1.0-alpha.1

公开自托管 Alpha；Worker 包版本为 `0.1.0a1`。这是公开版本基线，不表示维护者托管实例已升级，也不表示生产安全、真实模型质量或所有 R-EVAL 已验收。

已公开预发行与下载入口：[v0.1.0-alpha.1](https://github.com/mzydmer/deermate/releases/tag/v0.1.0-alpha.1)。源码为 `b9f20fb75162a51102ecc53b0f9cee20d2e30aee`；实际发布时间为 UTC `2026-11-17T00:46:52Z`（用户时区 America/Los_Angeles 为 2026-11-16）。[公开下载与安装验收收据](../docs/verification/public-alpha-release-2026-11-17.json)记录 main CI、构建/发布 run、四份资产和干净环境验证；收据的后续提交不改变发布源码或分发字节。

## 产物和平台

提供 `deermate-0.1.0a1-py3-none-any.whl`、`deermate-0.1.0a1.tar.gz`、`manifest.json` 和 `SHA256SUMS`。清单记录应用 tag、完整源码 SHA、DeerFlow SHA、Worker 版本、实际成功 CI run、构建 run、平台、大小和 SHA-256。SHA256SUMS 覆盖两个分发文件与 manifest，自身不自引用。

wheel 为纯 Python 分发；安装 smoke 覆盖 Linux/amd64 与 Intel macOS，Python 3.11+。完整工作台提供 Linux/amd64 的固定 tag 源码构建及实际启动 smoke。首版不提供公共 OCI 镜像或 digest 下载地址；本地构建的 Docker 镜像不是公开镜像。其他架构与 Windows 不在本次验证范围。

## 校验和安装 Worker

从同一 Release 下载上述四个文件，在下载目录执行校验。Linux：`sha256sum --check SHA256SUMS`；macOS：`shasum -a 256 --check SHA256SUMS`。确认全部通过后：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install ./deermate-0.1.0a1-py3-none-any.whl
.venv/bin/deermate --help
```

CLI help 和空 Worker readiness 不调用 Codex。实际执行前仍须按[Worker 指南](https://github.com/mzydmer/deermate/blob/v0.1.0-alpha.1/docs/local-worker.md)配置项目、Codex 和有效授权；MCP/SSH 是独立 extras，wheel 不包含完整网页工作台。

## 从固定 tag 构建完整工作台

Linux/amd64 需要 Docker/Compose、Python 3.12、Git、Go 1.27.3 和 Helm 3.18+ 的 3.x。只运行 init/prepare/build，不运行 ACK deploy，不需要集群权限：

```bash
git clone --branch v0.1.0-alpha.1 --depth 1 https://github.com/mzydmer/deermate.git
cd deermate
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]' 'cryptography==48.0.1'
.venv/bin/python scripts/ack_deploy.py init --registry deermate.local/alpha --context local-only --tag v0.1.0-alpha.1
.venv/bin/python scripts/ack_deploy.py prepare
.venv/bin/python scripts/ack_deploy.py build
.venv/bin/python scripts/single_host.py --images-config .deermate/ack/config.yaml --output .deermate/alpha --project deermate-alpha --port 2027
cd .deermate/alpha
./start.sh
```

从 loopback 端口进入首次管理员 setup 表示启动就绪。全栈 smoke 检查 Go readiness、生产 setup HTML 和空用户/模型/任务表，不提交执行任务。Mac Docker Desktop 的交互式开发入口继续见[本地指南](https://github.com/mzydmer/deermate/blob/v0.1.0-alpha.1/docs/local-docker.md)，也应从同一 tag 开始。

## 兼容、备份与回退

本发布工具变更不增加运行时数据库迁移；运行时基线包含此前 main 的改动，不能据此承诺任意旧数据库直接兼容。建议新空环境开始；升级已有实例先停止所有写入方并创建[共同状态冷备](https://github.com/mzydmer/deermate/blob/v0.1.0-alpha.1/docs/backup-restore.md)，保留原源码/镜像和完整匹配归档。

首版没有更早的公开 Alpha Release 可作为回退目标。已有部署应使用自己保留的原版本与匹配共同快照，在新隔离实例验证恢复；不要在线覆盖旧数据库、混搭单个状态文件或重放未知操作。设备授权、截止时间、撤权和任务原身份照常适用。

## 已知限制与托管状态

单 owner/有界来源和设备权限边界保持。首批离线实验保留前台超时、准备失败与 Go 未收敛样本，SQLite 锁竞争写者尚未确定；不宣称已通过完整生产或长期负载验收。真实模型质量、费用、用户注意力、其他适配器和更多故障点仍未验收。

维护者托管实例的历史 rollout 是独立记录；发布 tag/Release 不会升级、重启或修改该实例。完整实验身份仍是其自己的 producer SHA，不能用本 Release SHA 替换旧结果来源。
