# 持续秘书 Alpha

入口是登录后的「秘书与工作」。本轮实现了持久 Router、工作账本、异步执行、单仓库 GitHub 观察和有界召回；部署默认关闭。当前验证范围见[验收记录](verification/continuous-secretary-2026-11-04.json)，完整产品与研究验收见 [spec](specs/m4-continuous-agent.md) 和 [plan](specs/m4-continuous-agent-plan.md)。

## 使用步骤

1. 管理员先完成下面的运行配置。在首页展开「秘书设置」，选择已配置的模型并启用。自动执行额度初始为 0，手动操作仍须有效设备授权。
2. 在「交代给秘书」输入目标。秘书使用同一个 Router 对话，返回答复或工作提议；执行工作有自己的对话和 Codex 会话。也可以展开「直接创建一项工作」，填写目标、注册项目 ID 和授权 ID。
3. 打开工作详情，确认范围后执行。接纳前检查设备、协议、授权版本、项目和当前轮次；接纳后显示原操作状态。执行对话在运行时接纳后出现。
4. 后续针对这项工作的要求，从工作详情发送追问，继续原 Codex 根。另一项独立目标创建另一项工作。若同时从普通执行对话产生了新一轮，工作台会拒绝过时 head 并更新指针；重新核对后明确发送下一步，不自动重放。
5. 「暂停」阻止后续派单；「请求停止」等待原执行器确认。回执未知时使用「核对原结果」，系统只查原操作，不创建替代会话。
6. 如需观察 GitHub，展开来源与规则，先启用来源、等待基线建立，再添加 observe 规则。候选需本人接受；已绑定 Thread 的更新进入原工作上下文，不自动启动新 Native 轮次。

auto 需要本人明确选择模式、限定项目和授权，并设置非零额度。首期上限为每天 2 个自动 Native 轮次；Router/Assessor 合计每天 20 个接纳请求，按 UTC 记账。额度预留不等于供应方实际账单，未知投递继续占额。规则变更不回放历史候选。

## 运行配置

Go 控制端增加以下环境变量；对现有部署修改环境后重建对应容器，不复制私人模型或设备凭据到源码：

```dotenv
DEERMATE_CONTINUOUS_ENABLED=true
DEERMATE_GITHUB_REPOSITORY=owner/repository
DEERMATE_GITHUB_SECRET_HOME=/run/deermate-github
```

后两项仅在启用 GitHub 时需要。仓库由操作员固定，浏览器不能填写任意 URL 或 token 路径。将只读细粒度 GitHub token 放在 secret home 的 `github-read-token` 文件中：普通文件、内容不带换行、权限 0600，并由 Go 的运行 UID 可读。建议只授予目标仓库的 Metadata、Issues、Pull requests、Checks 读取权限；不要授予 Contents 写入或使用本机 `gh`/Codex 登录。请求只访问 `https://api.github.com` 固定 GET 路径，不跟随重定向或环境代理。

首次启用仅保存当前增量基线。轮询有一分钟重叠窗口、ETag、页数和事件数上限；失败/限流不提前推进游标。存储最多 10,000 个事件、1,000 个候选；达到上限会停止推进并显示原因，首期没有自动归档清理。删除只能在接口实际给出不可读/替代修订时确认，不能从一次增量列表中缺席推断远端删除。

模型沿用现有[管理配置](tools-and-connections.md)。支持有界 Chat Completions 的 `BaseChatOpenAI` 适配器；强制输出上限 1024、SDK 重试 0，拒绝可覆盖限制的嵌套配置。启用时的能力检查验证适配器限制，不测试供应方密钥、余额或网络。Responses/Codex 专用模型客户端不用于此后台模式。

### Worker 和运行时

升级 Go、Gateway wheel、前端、实际 Worker 和连接器。设备须报告 `continuous_protocol=work-orders-v1`，并有 90 秒内有效观测及逐版本本机确认；旧授权不会自动扩大，原生 Codex 登录始终留在设备。完整配对流程见[Agent 授权](agent-authorizations.md)。

Gateway 还须有名称为 `deermate` 的已启用 MCP profile，指向当前授权 relay。授权 API 只维护 `bridge.json`，不自动安装/替换 MCP profile。容器内安装 wheel 的配置示例（实际 home/解释器路径须匹配部署）：

```yaml
extensions:
  mcpServers:
    deermate:
      enabled: true
      command: /app/backend/.venv/bin/python
      args:
        - -m
        - deermate.cli
        - --relay-config
        - /app/backend/.deer-flow/agent-authorizations/bridge.json
        - mcp
      task_toolsets:
        - name: coding
          submit_tool: submit_task
          status_tool: get_task_status
          cancel_tool: cancel_task
        - name: followup
          submit_tool: continue_task
          status_tool: get_continuation_status
          cancel_tool: cancel_continuation_task
```

已有配置还要通过上游支持的 extensions 配置/生命周期入口安装，保留其他 profile；任务驱动配置在 Gateway 启动时读取，完成配置后重启 Gateway。不要直接覆盖正在使用的 `extensions_config.json`。缺 profile、旧协议或未确认授权均应拒绝派发。

## 数据和恢复

Go 在现有 SQLite 中保存版本化工作、输入、来源、规则、决策、预算和投递记录。Python 内部适配层复用 DeerFlow AgentRuns、普通任务驱动和原 native journal，不另建原生调度器。Router 只有类型化路由工具；Assessor 无工具；外部事件和 Worker 的范围报告不能修改授权。

每次可能发送前先持久化屏障。超时或重启后只查询同一操作的原 run/journal；明确的接纳前拒绝也有持久回执。暂停、关闭、取消请求和取消确认分别保存。停用模块阻止新派发，已发送操作仍可只读核对；不要用旧数据库覆盖未知操作。

引用读取最多 3 跳、20 对象、32 KiB，游标绑定本人、工作和版本。FTS5 只收录本人工作卡/事件预览，不复制完整聊天或 Native 日志；返回最近写入的 20 个关键词匹配，不对全部历史做 BM25 评分。少于 3 字符的搜索只查最近 200 张卡。来源停用、不可读和换代会过滤正文并移除索引；迟到回报不能重新索引已失效来源。

备份时同时保存一致性 SQLite、应用 home、模型文件、个人记忆和原 native journal。关闭开关是首选应用回退方式；旧镜像兼容性需在副本上验证，不能假定所有历史镜像兼容新表。

## 离线复现

使用[单机打包脚本](single-host.md)和当前完整 Go/Gateway/前端镜像生成全新 bundle，名称以 `-check` 或 `-fixture` 结尾、端口不能是 2026、不得预配模型/Worker。不要使用个人环境作为 fixture。

```bash
python scripts/single_host.py --images-config /private/images.json \
  --output .deermate/continuous-check/bundle \
  --project deermate-continuous-check --port 2036
python scripts/prepare_continuous_fixture.py .deermate/continuous-check/bundle
sh .deermate/continuous-check/bundle/start.sh
python scripts/verify_continuous.py --url http://localhost:2036 \
  --owner-file .deermate/continuous-check/bundle/owner.json \
  --restart-project deermate-continuous-check \
  --output .deermate/continuous-check/api.json
python scripts/verify_continuous_load.py --url http://localhost:2036 \
  --owner-file .deermate/continuous-check/bundle/owner.json \
  --project deermate-continuous-check --output .deermate/continuous-check/load.json
python scripts/verify_continuous_native.py --url http://localhost:2036 \
  --owner-file .deermate/continuous-check/bundle/owner.json \
  --bundle .deermate/continuous-check/bundle \
  --output .deermate/continuous-check/native.json
```

这些脚本只接纳单个离线模型 `continuous-fixture`。前两个须先于 Native fixture 执行；Native fixture 要求无已配设备和原生任务，运行中断后应检查原操作，不可换 ID 重跑。Native fixture 在 Gateway 内嵌 toy Worker，需要使用 [测试专用 Dockerfile](../deploy/testing/Dockerfile.continuous-native) 添加 Git：`docker build --build-arg DEERMATE_GATEWAY_IMAGE=<当前Gateway镜像> -f deploy/testing/Dockerfile.continuous-native -t deermate-native-fixture:local .`，仅将该隔离 bundle 的 Gateway 镜像切换为此测试镜像，再启动 Native 验收。生产 Gateway 不需要安装 Git。

Fake 模型与假 Codex 仅在测试文件里，不在生产 wheel 中；真实驱动、relay、连接器和 Worker 路径仍被使用。合成设备确认只适用于临时 toy 仓库，不代表真实设备授权。

## 当前边界

单 owner、单仓库、Codex，原生轮次并发 1；Claude、多租户、邮件/桌面适配器和 Github 写操作未实现。已有普通聊天仍可使用原链路；工作台不会持续镜像所有从普通执行聊天直接发起的轮次。旧 MCP 名称/执行器不能自动迁移为持续工作。界面首期需要填写注册项目/授权 ID，后续补可视化选择。

本地合成验收与真实 GitHub、真实模型、真实设备、云端升级和研究对照分开记录。历史临时 SSH 不能作为新部署权限。R-EVAL 对照/消融尚未开展，当前不能宣称 Router 带来性能或注意力成本改善。

本轮指定旧 Go 镜像的兼容检查可由 `scripts/verify_continuous_rollback.py --url <隔离入口> --bundle <隔离bundle> --owner-file <合成owner文件> --previous-image <本机已保留的deermate.local旧Go镜像> --output <私人收据文件>` 复现。先等待活跃 Native 轮次结束；脚本停用模块、切换指定镜像并恢复新镜像，不恢复数据库。仅对实际测试的版本声明兼容。

已检查的 390px 合成页面：[浅色截图](assets/continuous-home-390-light.png) / [深色工作详情](assets/continuous-home-390-dark.png)。这是同源 iframe 的真实产品布局，非原生手机或减少动态模拟验收。
