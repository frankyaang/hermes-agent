# Hermes CLI Agent Codex Responses Repair Plan

## Goal

修复 `hermes-clean` 使用 Codex 登录运行 CLI agent 时卡住的问题。成功标准是官方干净安装的 `hermes-clean chat -Q --provider openai-codex --model gpt-5.4-mini -q '请只回答 OK'` 能稳定返回，且不影响旧的定制 Hermes。

## Scope

- 目标代码库：`/Users/frank/.hermes/hermes-agent-official`
- 目标 profile：`/Users/frank/.hermes/profiles/official-clean`
- 主要排查范围：`run_agent.py` 的 OpenAI client 构造、Codex Responses streaming、CLI agent 调用链。

## Non-goals

- 不修改 `/Users/frank/.local/bin/hermes` 指向的旧定制 Hermes。
- 不运行 `hermes doctor --fix`。
- 不迁移 OpenClaw 或 Feishu 定制改动到官方干净副本。
- 不把 API key 写入聊天记录。

## Context

- Codex 登录已经完成；`hermes-clean status` 显示 provider 为 `OpenAI Codex`，model 为 `gpt-5.4`。
- `hermes-clean doctor` 识别 Codex 已登录；`~/.local/bin/hermes points to wrong target` 是并行安装的预期告警。
- 直接用同一 OAuth token 调 `https://chatgpt.com/backend-api/codex/responses` 的 streaming Responses API 可以快速返回 `OK`。
- Hermes CLI agent 通过 `hermes-clean chat -Q ...` 会长时间无输出或超时。
- 已有失败 dump：
  `/Users/frank/.hermes/profiles/official-clean/sessions/request_dump_20260422_234145_d43d2b_20260422_234348_376901.json`
- 失败 dump 的请求体包含：
  `model=gpt-5.4`、`reasoning={"effort":"xhigh","summary":"auto"}`、`include=["reasoning.encrypted_content"]`、`tools=30`、`parallel_tool_calls=True`、`store=False`。

## Milestones

1. 固化最小复现：区分是 CLI 运行层、`AIAgent`、OpenAI client headers，还是 Responses stream 处理问题。
2. 对比 Hermes client 与直接可用 client 的差异，优先检查 `default_headers`、timeout、stream/event 处理。
3. 做最小补丁，避免影响其他 provider。
4. 运行聚焦验证：直接底层流、`AIAgent` 层、`hermes-clean chat` 层。

## Parallel Workstreams

- 日志和 dump 读取可以并行。
- 代码阅读可以按 client 构造、transport、streaming 三条线并行。
- 正式 patch 串行执行，避免误改核心 agent loop。

## Risks / Unknowns

- Codex 后端可能要求特定 header；缺失时可能不是立刻 403，而是表现为长时间无结果。
- `gpt-5.4` + `xhigh` 可能天然较慢，因此验证先用 `gpt-5.4-mini` 做连通性，再验证目标模型。
- CLI quiet 模式无流消费者时仍走 streaming path，需要确认不会把流事件吞掉。

## Validation

- `source venv/bin/activate` 后运行 Python 层最小测试。
- `HERMES_HOME=/Users/frank/.hermes/profiles/official-clean hermes-clean chat -Q --provider openai-codex --model gpt-5.4-mini -q '请只回答 OK，用于验证连接。'`
- `HERMES_HOME=/Users/frank/.hermes/profiles/official-clean hermes-clean status`
- 确认没有遗留 `hermes-clean chat` 或 `run_agent.py` 进程。

## Progress

- [x] 官方干净安装存在，旧 `hermes` wrapper 未覆盖。
- [x] Codex 登录完成，profile 隔离配置存在。
- [x] 直接底层 Codex Responses streaming 验证通过。
- [x] 找到 CLI agent 卡住的具体代码原因：ChatGPT Codex streaming 与 Hermes 注入的 keepalive `httpx.Client` 不兼容。
- [x] 实施修复：仅对 `chatgpt.com/backend-api/codex` 跳过 keepalive transport，保留其他 provider 的 keepalive/proxy 逻辑。
- [x] 完成端到端验证：`gpt-5.4-mini`、显式 `gpt-5.4`、默认配置 `gpt-5.4` 均通过 `hermes-clean chat -Q` 返回 `OK`。

## Decision Log

- 先用 `gpt-5.4-mini` 验证 CLI agent 通路，因为它能更快暴露 Hermes 代码路径问题。
- 不把缺少第三方工具 API key 作为阻塞项；当前目标是主模型 Codex 登录通路。
- 直接 Responses streaming、`AIAgent._run_codex_stream` 使用普通 SDK client 都能成功；只有 `AIAgent._create_request_openai_client()` 注入 keepalive `httpx.Client` 后超时。
- 因此选择在 `run_agent.py` 的 OpenAI client 创建处对 ChatGPT Codex backend 使用 SDK 默认 transport，而不是改 prompt、工具、reasoning 或 retry 策略。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
source venv/bin/activate
```

优先查看：

```bash
git status --short
tail -n 120 /Users/frank/.hermes/profiles/official-clean/logs/agent.log
tail -n 120 /Users/frank/.hermes/profiles/official-clean/logs/errors.log
```

如果有卡住的验证命令，先检查并结束本次调试启动的 `hermes-clean chat` / `run_agent.py` 进程。

---

# Legacy OpenClaw / Hermes Cleanup Plan

## Goal

清理旧 OpenClaw、老 Hermes checkout、OpenClaw 迁移桥、共享导入桥和旧命令入口。成功标准是默认 Hermes 技能扫描只命中新 `domain` bundled skills，`hermes` / `hermes-clean` 都不再依赖老 `/Users/frank/.hermes/hermes-agent`，且当前 official checkout 保持可运行。

## Scope

- 删除 `/Users/frank/.openclaw`。
- 删除 `/Users/frank/.hermes/hermes-agent` 与 `/Users/frank/.hermes/hermes-agent.failed-20260416-155927`。
- 删除旧桥接目录：`hooks/feishu-openclaw-*`、`plugins/feishu-openclaw-bridge`、`migration/openclaw`、`memories/bridge-imports`。
- 删除旧 skill 桥：`/Users/frank/.hermes/skills/openclaw-imports`、`/Users/frank/.hermes/skills/shared-imports`、`/Users/frank/.hermes/legacy-skill-archive`。
- 删除旧 OpenClaw wrapper `/Users/frank/.local/bin/openclaw`。
- 将 `/Users/frank/.local/bin/hermes` 改指向 `/Users/frank/.hermes/hermes-agent-official/venv/bin/hermes`。

## Non-goals

- 不删除 `/Users/frank/.hermes/hermes-agent-official`。
- 不删除 `/Users/frank/.hermes/profiles/official-clean`。
- 不删除已经迁到 `skills/domain/` 的 `robot-product-voc-survey-insight`、`product-ops-dashboard`、`voc-dashboard-html`。
- 不清理 official 仓库内自带的 OpenClaw migration 文档/可选工具代码。

## Validation

- `command -v hermes hermes-clean openclaw`。
- `hermes skills list | rg "robot-product-voc-survey-insight|product-ops-dashboard|voc-dashboard-html"`。
- `find /Users/frank/.hermes/skills -path '*/openclaw-imports' -o -path '*/shared-imports'` 应无旧桥目录。
- `source venv/bin/activate && scripts/run_tests.sh skills/domain/product-ops-dashboard/tests skills/domain/robot-product-voc-survey-insight/tests skills/domain/voc-dashboard-html/tests`。

## Progress

- [x] 盘点旧体系入口和容量。
- [x] 检查是否有运行中旧进程。
- [x] 执行精确路径删除和 wrapper 更新。
- [x] 验证 official 环境与迁移技能。
- [ ] 需要人工 sudo 密码清理 root-owned npm OpenClaw 包：`/usr/local/lib/node_modules/openclaw`、`/usr/local/bin/openclaw`、`/Users/frank/.npm-global/lib/node_modules/openclaw`。

## Decision Log

- 旧 OpenClaw 目录约 16G，老 Hermes checkout 约 567M，旧 skill 桥约 1.5G。
- 本次按用户指令做永久清理，不再保留旧 OpenClaw / shared-imports 运行副本。
- 无密码 sudo 不可用，root-owned npm OpenClaw 包不能由当前进程删除；已经删除用户级 wrapper、LaunchAgents、Hermes 桥目录和旧运行目录。

## Recovery

如果误删后需要恢复，只能从系统备份、git remote、包管理安装源或上游仓库重新拉取；本次不会把 18G+ 旧运行目录再复制成备份。

---

# Feishu Group Mention Diagnostics Plan

## Goal

定位并修复飞书群聊 `@香农AI助手` 不触发 agent、但 Home 私聊可正常回复的问题。成功标准是群聊消息能够进入 agent，若仍被拦截，日志会明确给出是 allowlist、mention 还是飞书投递问题。

## Scope

- `gateway/platforms/feishu.py`
- `tests/gateway/test_feishu.py`
- 运行时配置 `~/.hermes/.env`

## Non-goals

- 不改动飞书群策略本身（仍保持 `allowlist`）。
- 不改动公网 webhook / 连接模式。
- 不扩大群聊用户白名单范围。

## Context

- Home 私聊可正常收发，说明 gateway 与飞书 websocket 连接正常。
- 群 `oc_6e8ceb560c2f9c44bacaa3820fa00036` 历史上能正常触发，但最近新消息没有进入 agent。
- `/bot/v3/info` 真实返回里包含 `app_name` 和 `open_id`。
- 当前群聊 gate 在失败时只打 `debug`，现场缺乏可诊断信息。

## Milestones

1. 修正 bot 身份解析，兼容 `/bot/v3/info` 返回 `app_name`。
2. 恢复群聊 gate 的可诊断日志，输出 drop reason 和关键信息。
3. 固定 bot 名称 / open_id 到本地 `.env`，减少运行时探测依赖。
4. 重启 gateway 并等待群聊复测日志。

## Validation

- `source venv/bin/activate && python -m py_compile gateway/platforms/feishu.py tests/gateway/test_feishu.py`
- `source venv/bin/activate && scripts/run_tests.sh tests/gateway/test_feishu.py::TestHydrateBotIdentity tests/gateway/test_feishu.py::TestFeishuBotProbeSdk`
- `source venv/bin/activate && scripts/run_tests.sh tests/gateway/test_feishu.py -k 'normalized_bot_name or allowlist_and_mention_both_required or matches_bot_open_id_when_configured or group_post_message_uses_parsed_mentions_when_sdk_mentions_missing'`
- `source venv/bin/activate && python -m hermes_cli.main gateway restart`
- 复测后查看 `/Users/frank/.hermes/logs/agent.log`

## Progress

- [x] 确认 `/bot/v3/info` 可返回 bot `open_id` 与 `app_name`。
- [x] 修正 `_parse_bot_response()`，兼容 `app_name`。
- [x] 增加群聊 gate 的 `info` 级 drop 日志，记录 reason、sender、mention 与 bot 身份。
- [x] 增加 mention 名称归一化，兼容 `@香农AI助手` 这类展示名。
- [x] 聚焦测试通过：7 项 bot 探测测试、4 项群聊 gate 测试。
- [x] 将 `FEISHU_BOT_NAME` / `FEISHU_BOT_OPEN_ID` 写入 `~/.hermes/.env`。
- [x] gateway 已重启并重新连上飞书 websocket。
- [x] 读取复测日志，确认邱士倬消息被 `sender_or_group_not_allowed` 拦截。
- [x] 找到单群 allowlist 未生效原因：规则被写在 `display.platforms.feishu.extra`，该位置不属于 gateway 平台 adapter 配置。
- [x] 将【地宝香农小龙虾】单群 allowlist 复制到正确位置：顶层 `platforms.feishu.extra.group_rules`。
- [x] 验证运行时配置：邱士倬只在目标群规则中放通，不在全局 `FEISHU_ALLOWED_USERS`。
- [x] gateway 已再次重启并重新连上飞书 websocket。
- [x] 放松 Feishu 群聊 sender gate：全局 `FEISHU_GROUP_POLICY=open`，目标群规则 `policy=open`。
- [x] 增加 Feishu 群聊文本唤醒词：`香农AI助手`、`香农龙虾智能体`。真实 @ 或文本出现唤醒词均可触发，普通群聊文本仍不触发。
- [x] 聚焦验证通过：非 Hermes allowlist 用户在目标群文本包含 `@香农AI助手` 时可进入，普通文本仍被拦。
- [x] 真实日志验证：邱士倬在【地宝香农小龙虾】发送的 `希望你：@香农AI助手...` 已进入 agent，并在 2026-04-24 11:25:08 发出回复。
- [x] gateway 已重启并重新连上飞书 websocket。
- [ ] 继续观察是否还有无唤醒词消息误入或应入未入。

## Decision Log

- 继续保留 allowlist 策略，先提高可观测性，再决定是否调整策略。
- bot 身份既保留运行时探测，也写入 `.env` 做显式兜底，避免探测失败导致群聊 mention 判断失真。
- 保持最小权限：不把邱士倬加入全局 `FEISHU_ALLOWED_USERS`，只在目标群的 `group_rules` 中放通。
- 用户确认飞书侧已做可用人群限制后，Hermes 侧 sender gate 改为开放，保留 mention / wake-term gate 控制触发范围。
- `group_wake_terms` 只配置明确机器人名，不配置 `香农`、`龙虾`、`你帮我` 等宽泛词，避免普通业务聊天误触发。

## Recovery

恢复时先执行：

```bash
cd /Users/frank/.hermes/hermes-agent-official
source venv/bin/activate
python -m hermes_cli.main gateway status
tail -n 80 /Users/frank/.hermes/logs/agent.log
```

若群聊仍无响应，让用户在群里重新发送一次真实 `@` 提及，然后立刻检查新出现的 `Dropping group message before agent` 或 `Inbound group message received` 日志。

---

# Robot Product Insight Skills Refactor Plan

状态：该方案中的“共享内核 + 上层 wrapper”迁移已被后续接入式重构方案暂缓，不作为当前产品运营 Dashboard 的执行方案。当前执行方案见下方 `Product Ops Dashboard Agent-System Implementation Plan`。

## Goal

将 `robot-product-voc-survey-insight`、`product-ops-dashboard`、`voc-dashboard-html` 按当前 `agent_system` 标准架构重构为“共享内核 + 分层 Skill + 专家编排 + 审计闭环”。成功标准是用户分析、产品运营 Dashboard 与 HTML 渲染职责清晰，公共脚本不再双份维护，现有业务入口仍可运行。

## Scope

- 只读审计对象：
  - `skills/domain/robot-product-voc-survey-insight`
  - `skills/domain/product-ops-dashboard`
  - `skills/domain/voc-dashboard-html`
- 文档产物：
  - `agent_system/SKILL_REFACTOR_AUDIT.md`
  - `agent_system/BUILD_GUIDE.md`
  - `agent_system/OPTIMIZATION_PLAN.md`
- 后续可选实现对象：
  - 新增 `skills/domain/robot-product-insight-core`
  - 收窄两个上层业务 skill 的 `SKILL.md`
  - 调整 `agent_system` scheduler / experts / audit gates

## Non-goals

- 本轮不删除现有 skill 目录。
- 本轮不移动现有脚本。
- 本轮不修改 `generate_insight_bundle.py` 等生产脚本行为。
- 本轮不破坏现有 `product-ops-dashboard`、`robot-product-voc-survey-insight`、`voc-dashboard-html` 入口。

## Context

- `robot-product-voc-survey-insight` 是“看用户”分析方法层，负责 JudgmentUnit、Top15、代际、竞品、FRR/FFR 和 PM 定义输入。
- `product-ops-dashboard` 是 Dashboard 交付编排层，应该先消费主报告，再生成 Dashboard 信息架构，并在需要 HTML 时桥接 `voc-dashboard-html`。
- `voc-dashboard-html` 是边界清晰的 HTML 渲染层，要求严格无损、保留所有章节/表格/单元格并生成 audit。
- 当前前两个业务 skill 共享 10 个脚本、3 个 examples、registry JSON 和 reference 文档，存在双份维护风险。

## Milestones

1. 完成本地文件盘点、读取和维度抽取。
2. 固化技能重构审计文档。
3. 将本地文档约束映射到当前标准架构。
4. 设计共享内核目录和上层 wrapper 策略。
5. 后续在用户确认后执行真实迁移与测试。

## Parallel Workstreams

- 文档对比、脚本盘点、reference 抽取可并行。
- 真正迁移脚本时必须串行，先建共享内核，再改 wrapper，再跑测试。

## Risks / Unknowns

- `generate_insight_bundle.py` 很大，且两个技能副本已有细微差异，不能直接用一次性 move 替代。
- 部分测试文件命名不同，但测试逻辑高度相似，需要迁移时保留历史入口。
- `ResponseCurator` 在当前环境可能不存在，相关包装逻辑需要保持 fallback。
- 如果上层 skill 过早删除本地脚本，会导致已有用户调用路径失效。

## Validation

- 文档层验证：
  - `rg -n "SKILL_REFACTOR_AUDIT|robot-product-insight-core|ResponseCurator|preflight" agent_system/*.md PLANS.md`
- 迁移后验证：
  - `source venv/bin/activate`
  - `scripts/run_tests.sh skills/domain/product-ops-dashboard/tests skills/domain/robot-product-voc-survey-insight/tests skills/domain/voc-dashboard-html/tests`

## Progress

- [x] 盘点本地相关 skill 文件。
- [x] 读取核心 `SKILL.md`、`ASSET_HARNESS.md`、reference、examples、scripts 和 tests。
- [x] 抽取分析维度、输出约束、Dashboard 约束与 HTML audit 约束。
- [x] 生成 `agent_system/SKILL_REFACTOR_AUDIT.md`。
- [ ] 用户确认后创建 `robot-product-insight-core` 共享内核 scaffold。
- [ ] 用户确认后收窄两个上层业务 skill 的 `SKILL.md`。
- [ ] 用户确认后迁移公共脚本并保留 wrapper 兼容。
- [ ] 跑完整技能测试。

## Decision Log

- 不直接移动脚本，因为当前两个业务 skill 虽高度重复，但 `generate_insight_bundle.py` 等文件存在局部差异。
- `voc-dashboard-html` 边界清晰，保持独立，不吸收分析逻辑。
- 共享内核应先承载公共 references、examples、registry 和脚本，再让上层 skill wrapper 引用。
- Dashboard 不是分析 skill，应该作为报告后的信息架构与交付编排节点。

## Recovery

恢复时从：

```bash
cd /Users/frank/.hermes/hermes-agent-official
```

优先读取：

```bash
sed -n '1,260p' agent_system/SKILL_REFACTOR_AUDIT.md
sed -n '1,260p' PLANS.md
git status --short --branch
```

如果后续迁移脚本失败，先保留原目录不动，撤回 wrapper 改动，再用现有 tests 验证旧入口仍可运行。

---

# Product Ops Dashboard Agent-System Implementation Plan

## Goal

将 `agent_system` 中的产品运营 Dashboard 示例架构落地为“业务报告 Skill 输出最终业务结果”的新版逻辑。成功标准是系统不再把通用 `final_report` 作为主链路节点，而是由 `ops_expert（运营专家）` 调用 `ops_dashboard（运营看板）` 输出产品运营报告和 Dashboard 结构；如需 HTML/PDF，再由 `dashboard_html（看板渲染）` 负责呈现。

## Scope

- 更新 `agent_system/init_skills.py`、`init_experts.py`、`init_scheduler.py`。
- 更新 `agent_system/ARCHITECTURE.md`、`BUILD_GUIDE.md`、`OPTIMIZATION_PLAN.md`。
- 刷新 `agent_system/skills/`、`experts/`、`scheduler/` 下由初始化脚本生成的示例配置。
- 保持 `skills/domain/product-ops-dashboard`、`robot-product-voc-survey-insight`、`voc-dashboard-html` 源技能目录不做内部迁移。

## Non-goals

- 不新增通用 `final_report（最终报告）` Skill。
- 不把 `superpowers（思考辅助）` 放入主 Pipeline。
- 不为每个 Skill 复制独立的 `briefing（过程汇报）`。
- 不移动或改写三个 domain skill 的生产脚本。

## Context

- 用户已明确：最终结论输出应该来自专家层调用具体报告生成 Skill 的结果。
- `ops_dashboard（运营看板）` 是产品运营 Dashboard 场景里的报告生成 Skill，不是通用打包前的中间节点。
- `dashboard_html（看板渲染）` 只消费 `ops_dashboard` 的结构化输出并做呈现，不重写业务内容。
- `superpowers（思考辅助）` 是专家层按需调用的辅助判断能力。
- `briefing（过程汇报）` 是调度层在关键节点完成后可选触发的通用过程能力。

## Milestones

1. 调整初始化脚本中的 Skill、Expert、Scheduler 命名和职责。
2. 删除或覆盖旧的 `_example` 主链路配置与 `final_report_example` 生成物。
3. 更新架构与建设文档，明确三条流程：洞察流程、看板流程、网页流程。
4. 运行初始化脚本和只读检查，确认列表、路由和文档不再残留通用 `final_report` 主链路。

## Validation

- `source venv/bin/activate && python agent_system/init_skills.py`
- `source venv/bin/activate && python agent_system/init_experts.py`
- `source venv/bin/activate && python agent_system/init_scheduler.py`
- `rg -n "final_report|final_pack|final_report_example|report_gen_example|analysis_1_example|ui_render_example|expert_A_example|expert_B_example" agent_system/skills agent_system/experts agent_system/scheduler agent_system/memory agent_system/audit`
- 检查 `agent_system/scheduler/main_scheduler/routes.json` 中三条主流程为 `insight_flow`、`dashboard_flow`、`html_flow`。

## Progress

- [x] 完成当前脚本、文档和路由现状读取。
- [x] 更新初始化脚本。
- [x] 刷新生成配置。
- [x] 更新架构文档。
- [x] 完成验证。

## Decision Log

- 使用正式短名称：`voc_insight（用户洞察）`、`ops_dashboard（运营看板）`、`dashboard_html（看板渲染）`、`superpowers（思考辅助）`、`briefing（过程汇报）`、`audit（核查）`。
- `ops_dashboard` 类型保持为 `report_generation`，因为它输出产品运营报告和 Dashboard 信息架构。
- `audit` 作为可被调度引用的核查 Skill 登记，同时保留现有 audit 模块用于日志落盘。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
```

优先查看：

```bash
sed -n '1,220p' agent_system/init_skills.py
sed -n '1,260p' agent_system/init_scheduler.py
git status --short agent_system PLANS.md
```

---

# Feishu Doc Access Optimization Plan

## Goal

让普通飞书群聊里的文档链接读取优先走飞书应用 API，而不是退回到无登录态浏览器。成功标准是飞书消息场景下的 agent 能拿到 `feishu_doc_read` 工具，并且该工具能在普通消息回合中使用当前飞书 adapter 的 client 成功读取文档内容。

## Scope

- 目标代码库：`/Users/frank/.hermes/hermes-agent-official`
- 主要改动范围：
  - `tools/feishu_doc_tool.py`
  - `tools/feishu_drive_tool.py`
  - `gateway/run.py`
  - `hermes_cli/tools_config.py`
- 目标平台：普通飞书消息链路与飞书后台任务链路

## Non-goals

- 不改飞书 App ID / Secret。
- 不改现有飞书 allowlist、群聊策略和连接模式。
- 不把浏览器登录态方案作为主修复路径。
- 不改飞书评论场景的既有行为。

## Context

- 当前飞书应用凭证可以直接调用飞书开放平台文档接口，读取 `docx` 正文成功，说明授权链路正常。
- 普通飞书群聊消息场景下，agent 当前没有启用 `feishu_doc` toolset，因此遇到文档链接时退回到 `browser_navigate`，最终跳转到飞书登录页。
- `tools/feishu_doc_tool.py` 与 `tools/feishu_drive_tool.py` 当前依赖评论场景注入的 thread-local client；普通消息链路没有做这一步。
- `gateway/platforms/feishu_comment.py` 已有评论场景注入逻辑，应保持兼容。

## Milestones

1. 为飞书文档/Drive 工具增加可按 `task_id` 解析的 client 绑定能力，同时保留 thread-local 兼容路径。
2. 在普通飞书消息与后台任务链路里绑定当前 adapter client。
3. 将 `feishu_doc` 纳入飞书平台默认可用工具集。
4. 完成本地校验并重启 gateway 验证。

## Risks / Unknowns

- agent 工具调用在线程池中执行，client 绑定必须避免只依赖当前线程上下文。
- 飞书平台已有用户改动，修改 `gateway/run.py` 时必须叠加，不回退已有本地定制。
- `feishu_doc` 默认启用后，应仍允许未来通过显式平台配置覆盖。

## Validation

- `source venv/bin/activate && python -m py_compile gateway/run.py tools/feishu_doc_tool.py tools/feishu_drive_tool.py hermes_cli/tools_config.py`
- `source venv/bin/activate && python - <<'PY'`
  `from hermes_cli.config import load_config`
  `from hermes_cli.tools_config import _get_platform_tools`
  `print(sorted(_get_platform_tools(load_config(), 'feishu')))`
  `PY`
- `source venv/bin/activate && python - <<'PY'`
  `from dotenv import load_dotenv`
  `from gateway.platforms.feishu import _build_onboard_client`
  `from model_tools import handle_function_call`
  `from tools.feishu_doc_tool import bind_client, unbind_client`
  `...`
  `handle_function_call('feishu_doc_read', {'doc_token': 'ZEF4dCbtPoCs2NxH67BcsshXnnf'}, task_id='feishu_doc_test')`
  `PY`
- `source venv/bin/activate && python -m hermes_cli.main gateway restart`
- `source venv/bin/activate && python -m hermes_cli.main gateway status`
- `tail -n 80 /Users/frank/.hermes/logs/gateway.log`

## Progress

- [x] 完成根因定位：授权正常，失败点在普通飞书消息回合退回浏览器登录页。
- [x] 确认普通飞书平台默认工具集缺少 `feishu_doc`。
- [x] 实现工具层 client 绑定增强。
- [x] 接入 gateway 普通消息与后台任务链路。
- [x] 启用飞书平台默认 `feishu_doc` 并完成验证。

## Decision Log

- 优先修“让 API 工具可用并可调用”，不先做提示词绕行或浏览器补登录。
- 普通消息链路沿用当前 adapter 的飞书 client，避免新增独立鉴权和重复 token 管理。
- `task_id` 继续沿用现有会话隔离语义，不改 agent 的终端 / 浏览器持久化行为；飞书 client 绑定通过引用计数补足并发解绑安全性。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
source venv/bin/activate
```

优先查看：

```bash
git status --short
python -m hermes_cli.main gateway status
tail -n 120 /Users/frank/.hermes/logs/gateway.log
```

---

# Feishu Sheet Tooling Plan

## Goal

为普通飞书消息场景补齐电子表格（Sheet）读取与编辑工具，让 agent 可以不依赖浏览器登录态，直接通过飞书开放平台 API 读取表结构、预览单元格数据，并向指定范围写入内容。

## Scope

- 目标代码库：`/Users/frank/.hermes/hermes-agent-official`
- 主要改动范围：
  - `tools/feishu_sheet_tool.py`
  - `tools/feishu_client_context.py`
  - `gateway/run.py`
  - `toolsets.py`
  - `hermes_cli/tools_config.py`
- 目标能力：
  - 读取表格基础信息
  - 读取工作表列表与预览范围
  - 向单个范围写入二维数据

## Non-goals

- 不实现多维表格（Bitable/Base）读写。
- 不实现复杂批量写入、追加、筛选、样式修改。
- 不修改现有飞书 App 凭证和权限配置。

## Context

- 现有 `feishu_doc_read` 已经能在普通消息场景工作，但用户这次卡住的是 `sheets/...` 链接。
- 当前仓库没有任何 `feishu_sheet_*` 工具，遇到表格链接时仍会退回浏览器登录页。
- 通过同一套飞书 App 凭证直接调用工作表 API，已确认目标表 `VX70s8q98hhaA4tk1RGcW8w9nlh` 可以返回表格信息与工作表列表，说明当前 app 对该表已有 API 访问权限。
- 官方文档已确认使用以下主接口：
  - 读取单个范围：`GET /open-apis/sheets/v2/spreadsheets/:spreadsheetToken/values/:range`
  - 向单个范围写入数据：`PUT /open-apis/sheets/v2/spreadsheets/:spreadsheetToken/values`
  - 获取电子表格信息：`GET /open-apis/sheets/v3/spreadsheets/:spreadsheet_token`
  - 获取工作表列表：`GET /open-apis/sheets/v3/spreadsheets/:spreadsheet_token/sheets/query`

## Milestones

1. 实现 `feishu_sheet_read` 与 `feishu_sheet_write` 工具。
2. 将 gateway 的 Feishu client 绑定逻辑切到共享上下文，覆盖所有飞书工具。
3. 将 `feishu_sheet` 纳入飞书默认工具集。
4. 用真实 sheet token 完成读取与写入验证。

## Validation

- `source venv/bin/activate && python -m py_compile gateway/run.py tools/feishu_sheet_tool.py tools/feishu_doc_tool.py tools/feishu_drive_tool.py hermes_cli/tools_config.py toolsets.py`
- `source venv/bin/activate && python - <<'PY'`
  `from hermes_cli.config import load_config`
  `from hermes_cli.tools_config import _get_platform_tools`
  `print(sorted(_get_platform_tools(load_config(), 'feishu')))`
  `PY`
- `source venv/bin/activate && python - <<'PY'`
  `# 通过 handle_function_call 验证 feishu_sheet_read / feishu_sheet_write`
  `...`
  `PY`
- `source venv/bin/activate && python -m hermes_cli.main gateway restart`
- `source venv/bin/activate && python -m hermes_cli.main gateway status`

## Progress

- [x] 确认当前仓库缺少 `feishu_sheet_*` 工具。
- [x] 通过真实 sheet token 验证目标表具备 API 可读权限。
- [x] 实现 `feishu_sheet_read` / `feishu_sheet_write`。
- [x] 接入飞书默认工具集并重启验证。

## Decision Log

- 优先实现“结构读取 + 单范围写入”这一最小可用集，不先扩展批量写入与样式能力。
- 为了让后续所有飞书工具受益，gateway 里的 task 级 client 绑定切换到共享上下文模块，不再通过 doc/drive 包装函数间接绑定。
- 写入验证使用 API 临时创建的电子表格完成，避免直接修改现有业务表。

## Validation Notes

- 真实业务表 `VX70s8q98hhaA4tk1RGcW8w9nlh` 已通过 `feishu_sheet_read` 成功读到：
  - 表标题：`产品线运营PPC（0410更新）`
  - 首个工作表：`X1MFFa / 主线与分品类路径`
  - 默认预览范围：`X1MFFa!A1:J20`
- 临时电子表格创建成功，且通过新工具完成：
  - `feishu_sheet_write` 写入 `A1:B2`
  - `feishu_sheet_read` 回读验证值为 `[['ok', 'write'], ['1', '2']]`
- gateway 重启后已重新连上飞书 WebSocket。

---

# Feishu Doc Deep-Read Fallback Plan

## Goal

优化 `feishu_doc_read`，当 `raw_content` 只能返回少量标题文本时，自动继续读取 Docx blocks，并对文档内嵌的电子表格做预览展开，避免 agent 误判“文档没有正文”。

## Scope

- 目标代码库：`/Users/frank/.hermes/hermes-agent-official`
- 主要改动范围：
  - `tools/feishu_doc_tool.py`
  - `tests/tools/test_feishu_tools.py`
- 目标能力：
  - 识别“正文过短”的 doc
  - 自动读取 blocks
  - 识别并解析嵌入 sheet token（`spreadsheetToken_sheetId`）
  - 自动拼接嵌入 sheet 的预览内容到 `content`

## Non-goals

- 不实现通用 bitable / 图片 / 文件块深读。
- 不改飞书 App 权限配置。
- 不在本轮实现任意块类型的通用写回。

## Context

- 目标文档 `CU52dwMADoqCBkxDtxFcpDGwn1c` 的 `raw_content` 只有标题。
- 通过 `GET /open-apis/docx/v1/documents/:document_id/blocks` 已确认该 doc 的主体是一个 `sheet` block，而不是普通正文段落。
- 飞书官方 FAQ 已说明：文档中嵌入电子表格时，该块 token 为 `spreadsheetToken_sheetId` 格式。
- 直接拆分 `RX8hsMOachgMz2tL2TrcIcKEnjg_5cfRcx` 后，使用：
  - `spreadsheet_token = RX8hsMOachgMz2tL2TrcIcKEnjg`
  - `sheet_id = 5cfRcx`
  可以成功读到该嵌入表格的真实内容。

## Milestones

1. 为 `feishu_doc_read` 增加 blocks 级 fallback。
2. 解析嵌入 sheet token 并复用 `feishu_sheet_read` 获取预览。
3. 将预览内容拼接回 `content`，同时保留结构化字段。
4. 补充回归测试，覆盖富文本 doc 和嵌入 sheet doc 两类场景。

## Validation

- `source venv/bin/activate && python -m py_compile tools/feishu_doc_tool.py tests/tools/test_feishu_tools.py`
- `source venv/bin/activate && scripts/run_tests.sh tests/tools/test_feishu_tools.py`
- `source venv/bin/activate && python - <<'PY'`
  `# 用真实 doc token 验证短正文 fallback 会读出嵌入 sheet 预览`
  `...`
  `PY`

## Progress

- [x] 定位到 `raw_content` 只返回标题的根因：主体内容在嵌入 sheet block。
- [x] 验证嵌入 sheet token 可以拆成 `spreadsheetToken_sheetId` 并成功读取。
- [x] 实现 `feishu_doc_read` 的 blocks fallback 与嵌入 sheet 预览拼接。
- [x] 完成本地测试与真实 token 回归验证。

## Decision Log

- 保持 `feishu_doc_read` 的现有调用入口不变，只增强返回内容，不新增必填参数。
- 优先复用 `feishu_sheet_read` 的现有读取逻辑，不在 doc 工具里重复实现一套 sheets API。
- 仅在正文过短时触发 blocks fallback，避免对正常长文档增加不必要的 API 调用。

## Validation Notes

- `scripts/run_tests.sh tests/tools/test_feishu_tools.py` 已通过，结果：`7 passed`。
- 使用真实 doc token `CU52dwMADoqCBkxDtxFcpDGwn1c` 调用增强后的 `feishu_doc_read`，结果为：
  - `blocks_fallback_used = true`
  - `embedded_resources = 1`
  - `blocks_summary = {"count": 6, "by_type": {"page": 1, "heading1": 1, "sheet": 1, "text": 2, "divider": 1}}`
  - `content` 已包含嵌入表格的预览内容，成功读出：
    - `VOC分析（电商VOC）`
    - `竞品布局及配置竞争分析`
    - `性能参数竞争分析`
    - `展会/情报`
    - `调研：定量、入户、专题，含国内及海外`
    - `需求管理及卡诺模型`
    - `市场分析`
    - `预研及技术储备`
    - `产品规划整体逻辑串联skill`
- gateway 已重启，日志显示 **2026-04-24 02:23:32** 重新连上飞书 WebSocket。
