# 文档影响检查：统一 DeerFlow 版本输入

结论：无需更新客户文档。

理由：本次仅将构建、CI checkout 和验收工具中重复的上游提交迁移到 deploy/deerflow.lock，保留相同 DeerFlow 源码、依赖锁、用户界面及 Go/Python 运行边界。预检、构建标签和收据属于维护者工作流，不改变客户的对话、记忆、工具、授权或任务行为，也不需通过重建线上前端来发布文案。历史验收与 ADR 的原始 SHA 不改写。

涉及文件：deploy/deerflow.lock；scripts/deerflow_lock.py、ack_deploy.py、ack_image_smoke.py、local_docker.py、single_host.py、frontend_dev.py、design_visual_fixture.py、verify_deerflow_gateway.py；tests/test_deerflow_lock.py、test_deerflow_compat.py 及已有部署合同；.github/workflows/ci.yml。

工程文档：新增 docs/deerflow-version.md，说明唯一版本输入、缺失/非法/不匹配预检、实际版本输出、升级与回退；ACK、本地、单机和 Gateway 指南引用相同规范。SPEC 增加 NFR-010。仅输入版本与工程产物追溯发生变化，产品业务数据流和图示不变，仍检查现有七幅图的一致性。

验证：结果和实际合入状态见 STATUS、EVOLUTION 及本次验收收据，不以脚本存在代替 CI 或镜像验收。
