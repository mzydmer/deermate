# DeerFlow 版本锁与升级

`deploy/deerflow.lock` 是当前构建和验证的唯一上游版本输入。文件只保存一个完整的 40 位小写 Git SHA，可有一个结尾换行，不接受分支、标签、短 SHA、空值或全零值。读取器只使用 Python 标准库，CI 在 checkout DeerFlow 前即可校验；没有环境变量或命令行参数覆盖构建版本。

```bash
python scripts/deerflow_lock.py
```

ACK 构建与 Helm 渲染、本地 Compose、单机包、前端开发准备、视觉验收的 Gateway、驱动合同和完整 Gateway local/SSH 验证都读取这个文件。CI 的两个上游 checkout job 使用读取器的 `revision` 输出；前端与 ACK job 通过相同的构建脚本读取锁。`frontend/patches.json` 继续验证实际覆盖文件的哈希，不能用版本锁代替接口兼容检查。

## 预检与追溯

缺失或非法锁会在抓取上游前失败；构建也不会先启动 Go 镜像构建。已有 checkout 的 HEAD 必须与锁一致，报错会同时给出 `expected` 和 `actual` SHA。工具不会 reset、覆盖或自动升级已有目录。

ACK 使用整个干净 checkout；Gateway 检查 `backend`，纯驱动合同检查实际加载的源码路径，前端准备检查归档使用的 frontend、contracts、skills、examples 和 backend。所需路径的已暂存、未暂存和未忽略的新文件都会阻止使用；被 Git 忽略的虚拟环境和缓存不受影响。

| 产物或检查 | 可核对的版本 |
| --- | --- |
| 构建 / 前端准备 / Gateway 验证输出 | `DeerFlow upstream commit: <完整 SHA>` |
| ACK 构建目录 | 成功后生成 `build-receipt.json`，含实际归档 SHA、本次镜像、平台及推送状态 |
| Gateway 与前端镜像 | `io.deermate.deerflow.commit` 镜像标签；镜像 smoke 在启动容器前核对标签与锁 |
| Helm 资源及 Pod template | `deermate.io/deerflow-commit` annotation |
| 本地 Compose / 前端准备目录 | `upstream.json`；本地执行验收另在 `verification.json` 保存 `upstream_commit` |
| 单机包 | `bundle.json` 的既有 `upstream_pin` 字段，值来自已验证的 HEAD |
| Gateway local / SSH 验收 | JSON 中的 `upstream_commit`，并保留上游 `uv.lock` 哈希 |

例如，核对已构建的 Gateway 镜像：

```bash
docker image inspect --format '{{ index .Config.Labels "io.deermate.deerflow.commit" }}' YOUR_GATEWAY_IMAGE
```

Go 和 nginx/tools 辅助镜像没有 DeerFlow 源码标签。标签说明构建时使用的源码，不替代镜像 ID、依赖锁或原有安全/执行验收。旧镜像没有新增标签时，需通过当前构建入口重新构建后运行新版 smoke，不能事后给旧镜像补标签冒充本次构建。

## 升级与回退

1. 核对目标上游的完整提交，显式修改 `deploy/deerflow.lock`。其余入口不再同步抄写 SHA；若接口、配置或覆盖文件改变，另外完成适配。
2. 保留当前 checkout、镜像、生成清单和收据。ACK 选择新的 `--config` 工作目录及镜像 tag；前端选择新的 `--output`；Gateway 使用新的上游目录。工具检测到旧 HEAD 时会停止，不会替你切换原目录。
3. 运行锁与预检反例测试、实际 Helm/Compose 合同、前端 overlay 和镜像 smoke，以及 Gateway local/SSH 合同。安装上游依赖继续使用该提交的 `uv.lock` 和 `--frozen`。
4. 对照日志、镜像标签、渲染清单和收据中的完整 SHA，再决定部署。修改锁本身不会升级已运行服务或重新授予设备权限。
5. 回退源码版本时，将锁恢复到已验收的 SHA，在新的工作目录重新验证和构建。部署回退另按对应部署指南处理，先核对活动任务并一致备份数据；不能用旧数据库覆盖新工作。

历史 ADR、演进日志、已提交验收 JSON 和旧生成包保留当时的 SHA，不随当前锁重写。当前修复不改变上游版本，也不重新解释历史验收范围。[Issue #9](https://github.com/mzydmer/deermate/issues/9) 跟踪本次统一工作。
