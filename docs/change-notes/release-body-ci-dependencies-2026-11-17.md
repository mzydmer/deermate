# Release 正文修复 CI 的共享夹具依赖

结论：无需更新客户文档。

理由：仅补齐内部只读验证作业的开发依赖，不改变用户安装方式、运行时行为、权限、发布范围或任何现有 Release 字段。

涉及文件：`.github/workflows/alpha-release-body.yml` 使用仓库统一的 `pip install -e '.[dev]'`。实际 PR run `43991859491` 的 job `133734199689` 在载入共享 `tests/conftest.py` 时缺少 `uvicorn`，测试尚未开始，repair job 已跳过，没有写入 Release。此处保留失败事实；不绕过共享夹具，也不放宽正文或资产判定。

验证：补依赖后的实际 Linux 测试与只读 API 预检由最终 exact-head CI 复验；原 13 项正文修复合同及公开 wheel 干净环境安装证据继续保留各自范围。
