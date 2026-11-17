# 可追溯公开 Alpha 发布

状态：Issue #7 发布候选，待独立评审与合并；tag/Release 尚未发布。基线 main `303e839a78115746cea3e4809a4324711af202bc`。对应 NFR-006/007/010，保留既有权限、任务身份和数据恢复约束。

## 范围与验收

| 编号 | 约束与证据 |
| --- | --- |
| REL-01 | `v0.1.0-alpha.1` 对应 Worker `0.1.0a1`；tag 全 SHA、DeerFlow 唯一锁、实际成功 CI、构建 run、平台与制品哈希进入机器清单 |
| REL-02 | 首版提供 wheel、sdist、manifest.json、SHA256SUMS；不发布公共 OCI 镜像，完整工作台从固定 tag 源码构建 |
| REL-03 | 干净 venv 校验 wheel SHA 后安装，运行 CLI `--help` 和无任务 Worker readiness；Linux/amd64 实际完整源码栈就绪，users/runs/MCP tasks 均为 0 |
| REL-04 | 分支/PR 只生成候选；只有已合入 main 的真实 tag push 可进入发布，必须实际查询同 SHA 的全部 13 项 CI 成功 |
| REL-05 | 先创建 draft、上传四份资产、核对服务端 digest/size/完整名单，再公开 prerelease；已有 Release 不覆盖、不自动续传，失败保留 draft 供核对 |
| REL-06 | CFF version/date、包版本、tag 与政策文件一致；发布前再次核对实际 UTC 日期，跨日拒绝发布；DOI/论文身份仍禁止虚构 |

版本/日期政策位于 `releases/alpha.json`。候选清单不宣称已公开或 CI 已通过，只有实际 API 验证后才记录成功 CI proof。普通主 CI 保持独立，发布 job 仅获 contents:write 与 actions:read，不读取本机凭据。

## 交付流程

实现 PR 通过独立评审并合入后，再核验 main 的实际 CI、UTC 日期、候选清单和 smoke。操作员得到明确授权后才用已有 SSH push 新 tag，Actions 提升同SHA main成功候选，分发文件逐字节不变，再核对实际CI与上传。禁止在评审/合并前创建 tag 或 Release，禁止自动移动已有 tag。发布日期变化时重新准备候选，不伪造或回填实际日期。

用户说明见[Alpha 发行说明](../../releases/alpha-notes.md)，内部步骤见[发布 runbook](../releasing.md)。runbook 不登记到产品部署导航。托管实例 rollout 与公开自托管 Release 分开；本任务不部署、不调用真实 Provider/Native，也不恢复历史设备授权。
