# 公开 Alpha 发布 runbook

内部操作说明，不加入产品部署导航。候选方案与验收见[规格](specs/public-alpha-release.md)，用户范围见[发行说明](../releases/alpha-notes.md)。

1. 实现 PR 由独立评审合并；不要从未合并分支发布 tag。所有 tag/Release 发布另经操作员核验，准备候选不产生发布授权。
2. 在干净 checkout 核对 tag/Worker/CFF/`releases/alpha.json` 一致，读取实际 UTC 日期；只有拟发布的同日才设置日期。若审阅跨日，重新提交候选与日期并重验，不能假称旧日期是实际发布日期。
3. 核验 main 的完整 SHA 和同 SHA 的 13 项 CI 成功；检查 candidate workflow 中 wheel/sdist、manifest/SHA256SUMS、干净 venv help/readiness 和 Linux 全栈 startup receipts。不得以旧 SHA 的成功 CI 替代。
4. 审阅者核验具体 tag、源码 SHA、日期、CI 和清单后，操作员才在该 main commit 创建新的 annotated tag，并用现有 SSH 连接 push 单个 tag。不要找本机 token/凭据，不使用 force，不移动已有 tag。
5. tag 流水线下载同SHA main已成功验证的候选，保持wheel/sdist字节不变，查询实际 CI，检查 main 祖先与 UTC 同日，再以 Actions 自带 token 创建 draft。四个上传文件的服务端 digest/size 和名单全部匹配才公开 prerelease；contents:write 仅在 publish job，其他 job 只读。
6. 发布后通过公开 API 重新核对 tag 解析 SHA、published_at UTC 日期、prerelease、四份资产和下载校验；在新的干净环境安装下载的 wheel 并运行 help，记录实际发布事实后更新 STATUS/发行日志。此动作不部署托管实例。

失败时保留日志与 draft；不自动覆盖/删除 Release、不续传未知上传、不移动 tag。API/上传响应不明时先只读核对已有对象。跨 UTC 日期会在公开前拒绝；已有 tag 不可静默重写，需操作员决定新的候选版本。

## v0.1.0-alpha.1 已有正文的三处链接修复

GitHub Release 正文直接使用源码 Markdown 的相对链接时，Worker、本地工作台、冷备三条指南缺少 tag/ref。仓库发行说明已改为 `https://github.com/mzydmer/deermate/blob/v0.1.0-alpha.1/docs/...`；既有 Release 的修复由 `alpha-release-body.yml` 单独执行，不重发发行版。

该修复 PR 经独立评审合入 main 后，受路径限制的 main push 自动触发作业；PR 只有只读预检，人工 workflow_dispatch 也仅允许 main。当前 job token 只对 Release `447839083` PATCH `body` 一个字段。原正文摘要必须为 `a4a491fa0699fb501a7a09760d7c0c230c3198c2db5269ea048440d08e868bf8`，替换三条链接后的摘要固定为 `113f8c5b847464d7251a5a3061210af9d6eea4d6c98824725f8ac5d82b5f8af7`。修复前后重新查询 annotated tag/source、发布时间、draft/prerelease 和四份 asset ID/size/digest；已有正确正文只读通过，未知正文或 API 结果停止，不盲重试 PATCH。成功证据上传为 `alpha-release-body-verification`，在其实际成功及公开链接核验之前不关闭 #7。

流水线参考 GitHub 官方 [GITHUB_TOKEN 权限](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)、[Release API](https://docs.github.com/en/rest/releases/releases)与[资产摘要](https://docs.github.com/en/rest/releases/assets)。token 来自当前 Actions job，不落盘、不写清单或日志。
