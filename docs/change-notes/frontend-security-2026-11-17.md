# 固定上游的 Next 安全补丁

构建 Next16.4.1 时实际出现安全版本提示。官方2026-11-03公告 GHSA-pc58-hwjq-p385 等覆盖16.4.1，修复版为16.4.5；选择同一16.4系列的16.4.6维护补丁（官方2026-11-09发布）。这不等于当前应用的具体利用条件均满足。

- 官方依据：https://github.com/vercel/next.js/security/advisories/GHSA-pc58-hwjq-p385
- 固定补丁：https://github.com/vercel/next.js/releases/tag/v16.4.6

DeerFlow SHA仍只读 deploy/deerflow.lock，不修改原检出。frontend/patches.json 对原 package.json 和完整pnpm-lock.yaml做SHA-256前置检查；package将next约束为精确16.4.6，受管overlay提供冻结锁。锁只变更next、@next/env和八个@next/swc包的版本/官方registry完整性及相关peer引用；其他依赖对象与原锁完整相等。固定十个包的版本元数据通过现有服务器到官方registry只读获取，未下载或执行远端脚本。

首次无界pnpm metadata解析因本地网络长时间等待而停止，没有把它当作通过。冻结安装、Linux运行、前端构建和CI按后续真实结果更新，不修改已公开Alpha的tag/资产。设计token、控件和布局不变；仍需原有设计门禁及页面回归。
