# 引用 DeerMate 与追溯研究来源

DeerMate 是软件项目，不是已发表的研究论文。根目录 [CITATION.cff](../../CITATION.cff) 使用 CFF 1.2 的 software 类型，署名沿用 [MIT 许可证](../../LICENSE)中的 **DeerMate contributors**；不虚构个人署名、DOI、ORCID、论文或研究效果。Python 包版本 `0.1.0a1` 不是已发布的 Release。本轮不填写 CFF 的 version、date-released、DOI 或 preferred-citation；公开 Alpha 由 issue #7 的实际 tag/清单决定，发布后再同步元数据。

## 软件引用

GitHub 在 CFF 收录到默认分支后提供 **Cite this repository** 入口，支持 APA/BibTeX；分支上文件可读取不等于默认分支引用 UI 已验收。该 UI/导出的实际结果在合入后单独记录。[GitHub 官方说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files)解释这一边界。也可在独立环境运行，避免旧版转换器的 jsonschema 依赖影响 MCP 运行时：

```bash
python3.12 -m venv .deermate/citation-env
.deermate/citation-env/bin/pip install cffconvert==2.0.0
.deermate/citation-env/bin/cffconvert --validate -i CITATION.cff
.deermate/citation-env/bin/cffconvert -i CITATION.cff -f bibtex
.deermate/citation-env/bin/cffconvert -i CITATION.cff -f apalike
```

导出记录引用软件整体。报告具体实验时，另外保存 `git rev-parse HEAD` 的完整 SHA、永久源码链接、数据集版本与哈希、上游锁、运行配置和原始结果。版本号不能替代实验所用的确切源码。

例如，已合入 main 的实际代码基线示例是 [`47c9d1a156d3db3c388871e60dafe386ce7cc10b`](https://github.com/mzydmer/deermate/tree/47c9d1a156d3db3c388871e60dafe386ce7cc10b)。它是该提交的软件状态示例，不是本轮实验的代码声明；本轮结果以实验清单记录的完整 SHA 为准。[记录模板](evaluation-record.template.json)中的空值必须由实际运行填写，不能当作已完成实验。

## 初始化实验记录骨架

先提交源码，确保工作区干净，再运行：

```bash
python scripts/evaluation_record.py --output .deermate/evaluation/record.json
```

生成器使用实际 `git rev-parse HEAD` 完整 SHA、永久源码 URL 和唯一的 `deploy/deerflow.lock`，其身份范围明确为当前用于初始化记录的 checkout。有数据集与结果文件时，另外提供 `--dataset FILE --dataset-version VERSION --results FILE --results-version VERSION`，只记录所提供文件的版本与实际 SHA-256。结果标为 `unverified`，生产源码 SHA 和所属数据集哈希保持 null，须依据原始运行清单核验后填写；当前 HEAD 不能冒充旧结果的生产提交。文件名不包含宿主绝对目录，已有输出不覆盖。没有数据集就不能登记结果。

这只初始化[模板](evaluation-record.template.json)：`template_only` 仍为 true，`experiment.status` 为 `not_run`；不会调用模型、执行实验或推断比较指标。真正运行后，由研究者填写协议、配置、环境、统计方法和失败样本。未产生的数据/结果版本保持 null，不能用骨架宣称完成了 R-EVAL。cffconvert 的本机 APA-like/BibTeX 检查比较标题、集体署名与仓库身份，GitHub 的 APA/BibTeX 界面与格式另外验证。

## 已公开的首批离线结果

[Router offline v1](router-offline-v1/README.md)公开36项主批次及独立6项复跑。实际生产源码为 [`7c84904e39f4b3adb0bed3d7430cc9adcb64934e`](https://github.com/mzydmer/deermate/tree/7c84904e39f4b3adb0bed3d7430cc9adcb64934e)；数据集、配置、raw JSON/JSONL、汇总和清单哈希见[provenance](router-offline-v1/provenance.json)。主批次33完成/2未知/1失败，复跑6项完成；报告整理时的HEAD不替代该生产SHA。模板的null/not_run仍表示模板自身，不用于描述这份已运行结果。

## 机制来源与本项目取舍

固定来源及具体链接集中保存在 [M4.5 研究来源](../specs/m4-continuous-agent.md#15-调研依据与已接受选择)。原始条目保留以下版本，后续更新追加取舍而不覆盖历史：

| 来源 | 记录的版本 | DeerMate 的使用与边界 |
| --- | --- | --- |
| DSH Super-agent prototype | `8c32a9dc5d72c033816c6a8110b37f40cf94fba4` | Router/Worker 分工、异步回报、订阅直通和观察模式；Go 接纳、设备范围和独立验证仍在模型提示词之外 |
| DeepSeek Harness session-query | `8bd073392eef6f54e921a093b95076248eb08cbb` | 精确读取与关系追溯；每跳检查本人权限与版本，并限制对象数和字节数 |
| DeerFlow | `deploy/deerflow.lock` 的完整 SHA | 复用实际图、运行时、ordinary driver 与 DeerMem；当前版本输入与历史实验版本分开记录 |
| Codex / MCP / AsyncSSH | 逐轮环境与协议收据记录实际版本 | 原生会话、工具协议与受控通信；离线协议 fixture 不等于真实模型或设备验收 |

来源参考不意味着上游作者为 DeerMate 的实现、实验结论或安全声明背书。研究问题、实验假设和功能验收分别记录；离线延迟与计数不能推断真实模型质量、账单或用户注意力收益。

格式与校验依据：[CFF 1.2.0](https://github.com/citation-file-format/citation-file-format/blob/1.2.0/schema-guide.md)、[cffconvert](https://github.com/citation-file-format/cffconvert)。
