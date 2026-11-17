# 公开Alpha候选的文档影响

涉及releases/alpha.json、releases/alpha-notes.md、scripts/release_artifacts.py、release_publish.py、verify_release_workspace.py、verify_citation.py、tests/test_release.py及release workflow。发布动作与安装/版本选择是客户可见变更，双语README、产品overview/changelog、CFF/references、SPEC/STATUS/EVOLUTION/roadmap和目录同步，生成产品JSON。候选不冒充已发布，实际tag/Release仍由独立评审核验后执行；不部署生产或扩大设备权限。

内部docs/releasing.md仅供维护操作，不进入产品部署导航；生产架构和交互未改变，七图无需重绘。17项离线合同已验证实际13job API proof结构一致、篡改/缺件/错误CI/日期/身份拒绝及服务端digest不匹配时不公开draft。真实干净venv和Linux全栈候选验证单独记实际结果。

补充实际验证：ed59c1b干净源码生成wheel/sdist并在新venv校验安装、CLI help、空Worker readiness通过，0任务/真实Provider调用。新增最小main候选/提升边界后26项发布合同通过；拒绝PR/错SHA/失败run/过期制品及错smoke/wheel，并保持原build_run_id与字节哈希。候选过期ref可取消，tag发布ref不自动取消。真实Linux完整栈由PR19最终head候选CI验收，未创建tag/Release。
