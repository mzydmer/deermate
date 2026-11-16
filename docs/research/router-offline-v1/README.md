# Router 首批离线结果 v1

2026-11-16。主批次 36 项：**33 complete、2 outcome_unknown、1 failed**；同版本独立复跑 6 项全部 complete。真实 Go/Gateway/MCP/Relay/Worker 执行 toy 修复，Provider 与 Native 使用脚本 fixture。零付费模型或真实 Codex 调用，未部署生产；原 12 个容器身份、启动时间与重启计数不变。

## 实验身份与材料

实际生产源码始终为 [`7c84904e39f4b3adb0bed3d7430cc9adcb64934e`](https://github.com/mzydmer/deermate/tree/7c84904e39f4b3adb0bed3d7430cc9adcb64934e)，工作区干净。此后整理报告的 HEAD 不是实验生产提交。

- [协议](../router-protocol-v1.md)、[数据集](../router-dataset-v1.json)、[固定配置](../router-offline-config-v1.json)。数据集 SHA-256：`cfd1139bb9d068b9056db1f748abd1d4406ec370718d068e9f918821dd6493a6`。
- [主清单](main/manifest.json)、[主汇总](main/summary.json)、[36 行 JSONL](main/records.jsonl)；清单逐行链接同目录下的独立 `sample.json`。
- [复跑清单](repeat/manifest.json)、[复跑汇总](repeat/summary.json)、[6 行 JSONL](repeat/records.jsonl)、[离散计数对比](repeat/comparison.json)。
- [全部制品哈希与来源](provenance.json)。每个 JSONL 行包含计划身份、原始 JSON 的字节哈希和同一 raw 对象；独立 JSON 保留原件字节。
- [真实双 effect 负例](calibration/double-effect/sample.json)及[独立判定](calibration/double-effect/verdict.json)，[正常正例](calibration/positive/sample.json)及[判定](calibration/positive/verdict.json)，另有[判定器反例](calibration/counterexamples/receipt.json)。校准不混入正式样本。

清单记录上游锁、Python/Go/Docker/机器、实际镜像 ID、Gateway 安装包文件哈希与完整 harness 哈希。Go 镜像 label 和二进制 VCS 均为同一生产 SHA。镜像和固定 BPE 缓存预热，各样本 owner/home/工作区全新；执行串行，测量期间不改源码或并发重型测试。

## 完成与前台延迟

A 为单协调会话，保留真实异步 MCP 后台工具；B 的所有事件经 Router；C 将已有权威订阅的绑定事件直接附加原工作。A/B 的关联在真实 Router 完成后确定性附加，不声称模型自行判断归属。每场景每组计划分母固定为 6，六种配对顺序、输入、预算和截止时间不变。

服务指标为持久接纳到实际完整 JSON 成功 flush，客户端另报发送到完整 JSON 读取，均为毫秒。两域不相减，服务 flush 不等于浏览器显示时刻。分位数采用 nearest-rank `ceil(q*n)`；本批 n 为 5 或 6，所以 p95 等于最大值。缺失延迟为 null/删失，不填零。

| 场景 | 组 | 完整完成 | 延迟观测/计划 | 服务 p50 / p95 / max (ms) | 客户端 p50 / p95 / max (ms) |
| --- | --- | --- | --- | --- | --- |
| S1 | A | 6/6 | 6/6 | 7659.9 / 8041.1 / 8041.1 | 7668.9 / 8049.2 / 8049.2 |
| S1 | B | 6/6 | 6/6 | 5269.4 / 5827.4 / 5827.4 | 5279.6 / 5837.3 / 5837.3 |
| S1 | C | 5/6 | 5/6 | 5476.7 / 5808.9 / 5808.9 | 5492.5 / 5864.7 / 5864.7 |
| S2 | A | 5/6 | 5/6 | 7453.6 / 8042.7 / 8042.7 | 7464.8 / 8055.9 / 8055.9 |
| S2 | B | 5/6 | 6/6 | 7813.7 / 8387.4 / 8387.4 | 7825.2 / 8396.9 / 8396.9 |
| S2 | C | 6/6 | 6/6 | 8013.9 / 8179.7 / 8179.7 | 8022.0 / 8190.6 / 8190.6 |

S1 C 和 S2 A 各有一项延迟删失。[主汇总](main/summary.json)保留逐次值、排队/验证延迟、状态及 B−A/C−B 的逐 seed 配对差；双方均有观测才计算配对差，缺失配对仍列出。S2 B 的前台延迟虽可观测，一项完整完成屏障仍失败，不能从延迟表推定整项成功。

## 三项未完整通过

| 原始样本 | 事实 | 计数方式 |
| --- | --- | --- |
| [S1-1104-C](main/S1-1104-C/sample.json) | 前台在固定 30s 内未读到原回复；Worker/test/effect 已完成，原 Router/Inbox 不确定 | outcome_unknown；延迟删失，保留 C 的计划分母 6 |
| [S2-1103-A](main/S2-1103-A/sample.json) | 设备配对 POST 返回 503，没有进入 Native 或 ACK 注入 | outcome_unknown；准备失败，执行未观测，保留 A 的计划分母 6 |
| [S2-1106-B](main/S2-1106-B/sample.json) | 真正断开 ACK 后 query 确认同原 run；Worker/MCP/通知完成且单 effect，但 Go 操作/Inbox 到 90s 仍未收敛 | failed；不计完整恢复，保留 B 的计划分母 6 |

没有替换 seed、重放原 mutation、延长单组预算或补跑失败格。批后只读核对在两个收敛失败的私有 Gateway 日志中发现 `sqlite3.OperationalError: database is locked`，原记录为 `receipt_unconfirmed`；具体竞争写入方未确定，不能据此宣称根因已修复。准备失败与运行后未收敛分别报告。

## 重复执行与恢复

主批次实际观测 **35 份执行，额外 root/effect 均为 0，即 0/35 observed；另 1 项 unobserved**。不能表述为 36 项全部没有重复。分组原生根/副作用的 observed、planned 和 unobserved 分母均保留在汇总中。

本报告的恢复率要求原操作核对及**完整端到端屏障**，query 找回同 run 单独不足以计成功：S2 A 为 **5/5 已注入观测、5/6 计划**；B 为 **5/6 观测、5/6 计划**；C 为 **6/6 观测及计划**。B 的未完成项不是重复执行；它已找回原 run，但另有 Go 状态未收敛。

真实负例确实向同一工作区写入两次相同变更并记录两条 effect，仍是一个 root/turn 且独立测试退出 0；判定器只因 `one_actual_mutation_effect` 拒绝。判定不读取 runner 的成功布尔。错 root、缺独立测试、越 owner、超范围、缺 RPC，以及把校准混入正式 batch 的反例均未获 complete；把正常样本的 runner 布尔改为失败仍独立判 complete。

## 脚本模型调用与输入量

下表为实际记录的角色调用和 UTF-8 输入字节，包含 messages 与工具 schema。A 的 coordinator 调用完整计入。未完成样本的记录可能截断，因此观测总数不能当作各组相同已完成工作的完整成本，更不能换算供应方 tokens、账单或注意力收益。

| 场景 | 组 | 有调用观测/计划 | 完整屏障/计划 | 观测角色调用 | 观测角色输入 bytes |
| --- | --- | --- | --- | --- | --- |
| S1 | A | 6/6 | 6/6 | coordinator=24; notification=6 | coordinator=49566; notification=11682 |
| S1 | B | 6/6 | 6/6 | router=30; notification=6 | router=89700; notification=11682 |
| S1 | C | 6/6 | 5/6 | router=21; notification=6 | router=56069; notification=11682 |
| S2 | A | 5/6 | 5/6 | coordinator=10; notification=5 | coordinator=15730; notification=9735 |
| S2 | B | 6/6 | 5/6 | router=17; notification=6 | router=41302; notification=11682 |
| S2 | C | 6/6 | 6/6 | router=18; notification=6 | router=43800; notification=11682 |

所有已接纳绑定事件最终属于原工作，C 的绑定事件没有新增 Router 模型调用。通知统一使用 `owned-admission-v1` 测试输入适配，保留完整原通知及哈希，12,000 bytes 上限不变；这不是默认生产通知预算的验收。

## 独立六项复跑

复跑同一冻结版本、数据、配置、镜像，仅 seed 1101，两场景各 A/B/C，共六项；六项均 complete，与主批次对应样本的终态、Worker/MCP 数、Go operation 数、Native turn 数、模型调用数、root/effect 数均一致。各项 Worker/MCP/root/turn/effect 均为 1；Go operation / 模型调用数分别为 S1 A 4/5、B 6/6、C 5/5，S2 A 2/3、B 4/4、C 4/4。实际时间是新测量，不要求墙钟值相等。复跑没有替换主批次的三项未完整通过记录。

## 单命令重算

在仓库根目录执行。输出路径必须尚不存在；重算只读取已发布证据，不启动模型、Docker 或 Native：

```bash
python scripts/aggregate_router_evaluation.py --manifest docs/research/router-offline-v1/main/manifest.json --directory docs/research/router-offline-v1/main --output /tmp/router-main-recomputed.json
```

复跑使用相同命令，把两处 `main` 改为 `repeat` 并选新输出。单独复判真实负例：

```bash
python scripts/judge_router_evaluation.py --sample docs/research/router-offline-v1/calibration/double-effect/sample.json --dataset docs/research/router-dataset-v1.json --output /tmp/router-negative-verdict.json
```

该命令预期退出 1、仅返回重复 effect 的拒绝理由。重新执行系统可用 `scripts/run_router_evaluation.py freeze|execute`，参数见[协议](../router-protocol-v1.md)；需要自行准备固定上游的本地镜像 profile 及同干净 SHA 的 evaluation-tag 控制镜像。清单中的本机 image ID 是实际制品身份，不是公开镜像下载地址。

这批实验仅覆盖 toy 修复、固定事件和首次 coordinator admission ACK 丢失。其他中断点、消融、真实模型质量/账单、用户注意力和容量结论仍未验收，R-EVAL 总体验收保持未勾选。
