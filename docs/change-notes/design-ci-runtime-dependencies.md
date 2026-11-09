# 文档影响检查：设计 CI 的测试依赖

结论：无需更新客户文档。

理由：GitHub Actions 的 design-system job 只安装 PyYAML 与 pytest，但共享 tests/conftest.py 会加载 uvicorn 和 DeerMate API。远端运行 42674679865 因缺少 uvicorn 在收集前失败。改用项目既有 dev 依赖，与 worker job 一致，不修改产品样式、操作、记忆、权限或运行限制。

涉及文件：.github/workflows/ci.yml 的 design-system 安装步骤。测试与门禁没有减弱，未跳过 conftest 或反例检查。

验证：本地既有 dev 环境中实际运行设计门禁与 tests/test_design_system.py；远端新运行结果另行核对，不把初次失败描述为通过。
