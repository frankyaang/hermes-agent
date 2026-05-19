# Hermes × gstack — Round 10 Final Decision Package

## Goal

将前九轮关于 GStack Control Protocol、performance governance、implementation contract、dry-run/sandbox/replay、feature flag、production readiness 的方案收束为最终决策包，产出 MVP skeleton 实现交接文档。

## Scope

- 只读调研：agent_system/ARCHITECTURE.md、runtime.py、cli_bridge.py、capability_readiness.py、readiness_manifest.json、hermes_constants.py、hermes_logging.py、hermes_cli/config.py、toolsets.py、tools/browser_tool.py、tools/delegate_tool.py、tests/conftest.py
- 产出 RFC：docs/rfcs/RFC-gstack-final-decision-package-v0.md
- 新建 agent_system/gstack_control/（16 个文件，MVP skeleton）
- 追加 readiness_manifest.json 三个 gstack phase 条目
- 新建测试文件：agent_system/tests/agent_system/test_gstack_control_*.py

## Non-goals

- 不调用真实 gstack CLI
- 不启用 browser daemon / GBrain / telemetry / proactive mode
- 不修改 Gateway / 用户 config / runtime.py / cli_bridge.py / capability_readiness.py
- 不实现 blocking 模式（allow_blocking 默认 False）
- 不执行 ship/canary/deploy 真实流程

## Go / No-Go

**决定：GO — 进入 MVP Skeleton 实现**

理由：边界清晰、回滚简单（rm -rf gstack_control/ + git checkout readiness_manifest.json）、Hermes 行为在 enabled=False 时完全不变、现有 readiness gate / 路径管理 / 测试框架完备可复用。

## Milestones

- [x] 只读调研（Round 10 计划阶段）
- [x] Go/No-Go 决策（已确认 GO）
- [x] RFC 产出：docs/rfcs/RFC-gstack-final-decision-package-v0.md
- [x] PLANS.md 追加本轮条目
- [ ] MVP skeleton 实现（Round 11）
- [ ] scripts/run_tests.sh 0 失败（Round 11 验收）

## Validation

- `scripts/run_tests.sh`（实现后）
- `grep -r "~/.gstack" agent_system/gstack_control/ | wc -l` = 0
- `git diff gateway/` 为空
- 三个 gstack phase 条目在 readiness_manifest.json 中 production_ready=false

## Rollback

`rm -rf agent_system/gstack_control/ && git checkout agent_system/readiness_manifest.json && scripts/run_tests.sh`

---

# Builder Intent Layer And Context Prefill

## Goal

在 `agent_system/experts/builder_expert/builder.py` 中为深度养马 9 阶段流程增加规则意图识别、非推进问答、回退/修订和基于对话历史的预填。成功标准是普通 `answer_current_question` / `continue` 路径保持现有 9 阶段推进；信息类意图不写字段、不推进 stage；预填内容可被后续回答或修订覆盖；`scripts/run_tests.sh tests/agent_system/` 通过。

## Scope

- `builder.py`：新增纯规则 `recognize_intent`，返回固定 8 个标签；在每轮 `handle()` 保存状态前完成意图分流。
- `builder.py`：新增 ask_definition / ask_advice / confirm_understanding / show_current / revise_previous / go_back 处理器。
- `builder.py`：新增规则上下文提取与首轮 copy 渲染，预填字段写入 state 但不破坏 session/draft 隔离。
- `builder_dispatcher.py`：仅在进入模式时调用 builder 的初始化/首轮渲染能力，保持状态文件路径策略不变。
- `tests/agent_system/`：补充 6 个指定场景，避免真实 LLM/API。

## Non-goals

- 不引入 LLM、网络或外部 API 调用。
- 不删除已有 state/draft/audit/output 文件。
- 不重构 ARCHITECT/DRAFT/VALIDATE/DRY_RUN/TRIAL_RUN/COMMIT 主流程。
- 不回撤当前工作区已有的无关改动。

## Context

- dispatcher 负责进入/退出模式与 session 级 state 文件路径；`builder.handle()` 当前每轮 `load_state -> handler -> save_state`。
- `write_drafts()` 已按 `state_identity` 写入 `agent_system/temp/builder_sessions/<state_identity>/`，`handle_commit()` 已读取 `session_draft_root`。
- run_agent 目前调用 agent-system bridge 时没有显式传入 `conversation_history`；预填需要从 `parent_agent.conversation_history`、`parent_agent.messages`、`parent_agent._session_db` 等可用对象中做 best-effort 规则读取。

## Milestones

- [x] M1：新增并导出 8 类意图识别函数，覆盖关键词/模式匹配。
- [x] M2：在 `handle()` 中统一识别并路由，非推进意图用状态快照保证不变更。
- [x] M3：实现信息类 handler 的静态模板响应。
- [x] M4：实现 revise_previous / go_back 的字段定位、原值展示、待覆盖态和回退态。
- [x] M5：进入模式时生成 prefill 和首轮 copy，普通无上下文入口保持可用。
- [x] M6：新增测试并跑 `scripts/run_tests.sh tests/agent_system/`。

## Parallel Workstreams

- 代码实现集中在 builder 入口和 dispatcher 初始化，需串行避免状态协议错配。
- 测试可与实现分离，但会依赖新增 public helper 和首轮返回文案。

## Risks / Unknowns

- 会话历史来源在真实运行时并非固定属性，需要容错读取并在不可用时回退空 INTAKE。
- revise/go_back 如果直接改 `_current_question` 容易误写字段；需要用 `_pending_revision_field` 明确下一轮覆盖目标。
- 现有工作树已有大量改动，必须避免格式化或重写无关文件。

## Validation

- `scripts/run_tests.sh tests/agent_system/`
- 手工检查 `git diff -- agent_system/experts/builder_expert/builder.py agent_system/builder_dispatcher.py tests/agent_system/...`
- 确认没有新增删除 draft/output/audit 文件的逻辑。

## Progress

- [x] 完成只读审查：确认 9 阶段 handler、state 保存点、draft/session 隔离和 dispatcher 入口。
- [x] 2026-05-14 本轮复核完成 Task 1 侦察，并新增 `BUILDER_RECON.md` 记录真实路径、字段、历史入口和隔离约定。
- [x] 2026-05-14 Task 2 基线已跑：`scripts/run_tests.sh tests/agent_system/` → `75 passed`，无需环境修复。
- [x] 实现意图识别和路由。
- [x] 2026-05-14 Task 3-7 静态复核通过：当前实现已满足 8 类规则意图、非推进分支、修订/回退、上下文预填和首轮文案要求，无需额外核心改动。
- [x] 实现预填和首轮 copy。
- [x] 2026-05-14 Task 8 聚焦测试复核：`scripts/run_tests.sh tests/agent_system/test_builder_intents.py -q` → `8 passed`。
- [x] 2026-05-14 为满足最终数量验收，额外补充 6 个 builder intent / prefill 边界测试；聚焦回归更新为 `14 passed`。
- [x] 补测试并验证：新增测试 `8 passed`，全量 `tests/agent_system/` 为 `75 passed`。
- [x] 2026-05-14 Task 9 最终验证：`scripts/run_tests.sh tests/agent_system/` → `81 passed`，0 失败。
- [x] 2026-05-14 本轮补强：`recognize_intent` 改为字符串兼容的 `IntentResult`，为 `revise_previous` / `go_back` 携带目标字段或阶段；首轮文案改为以任务指定中文 copy 开头。
- [x] 2026-05-14 本轮最终验证：`scripts/run_tests.sh tests/agent_system/test_builder_intents.py -q` → `14 passed in 0.25s`；`scripts/run_tests.sh tests/agent_system/` → `81 passed in 1.65s`。

## Decision Log

- 意图层放在 `builder.handle()`，因为这是所有 in-mode 用户轮次的统一状态保存边界。
- 进入模式的首轮预填需要 dispatcher 配合调用 builder 初始化函数，但不改变 state 文件命名和退出清理策略。
- 非推进意图采用 `copy.deepcopy(state)` 快照恢复，避免底层 handler 意外污染状态。
- 预填只把 5 个现有必填问题映射进 `state.intake`，其余目标字段保留在 `state.prefill`，避免改变下游 draft_writer 契约。
- dispatcher 只在进入模式时调用 `render_initial_reply()`，不改变 state 文件路径、退出清理或 draft/session 隔离策略。
- `recognize_intent` 保持 `str` 兼容，避免破坏既有 `intent in BUILDER_INTENTS` 与 `handle()` 分支，同时通过 `.target` / `.target_type` 暴露可验证目标。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
sed -n '1,220p' agent_system/experts/builder_expert/builder.py
sed -n '180,340p' agent_system/builder_dispatcher.py
scripts/run_tests.sh tests/agent_system/
```

---

# Gateway Progress UI Single-Channel Repair

## Goal

修复飞书进度模块双轨显示：assistant 中间消息 / 最终回复中的 `🧭 任务规划`、`🛠 执行记录` 不再作为普通消息发送或污染新增历史，统一进入 Gateway 可编辑进度模块。

## Scope

- 新增共享进度 UI 解析 helper，供 Gateway 展示链路和 AIAgent 历史清理复用。
- `gateway/run.py`：interim assistant 与 final response 先抽取进度 UI；进度进入 progress queue，剩余正文继续走 commentary/final。
- `run_agent.py`：assistant 可见 `content` 写入消息历史前剥离 leading progress UI，保留 tool calls、reasoning、Codex opaque state。
- 聚焦测试覆盖裸 `🧭 任务规划` + `🛠 执行记录`、旧 `# 专家层调度`、final response stripping 和 history sanitize。

## Non-goals

- 不批量清洗旧 `state.db` 或历史 JSONL。
- 不改变普通 commentary、工具进度事件和 `tool_progress=off` 的显示策略。

## Validation

- `scripts/run_tests.sh tests/gateway/test_run_progress_topics.py tests/run_agent/test_run_agent_codex_responses.py`
- `scripts/run_tests.sh tests/gateway/test_stream_consumer.py`
- `git diff --check`

## Progress

- [x] 新增 `agent/progress_ui.py` 共享解析器。
- [x] Gateway interim/final 进度 UI 改走 progress queue。
- [x] AIAgent 新增历史清理，避免新增可见历史污染。
- [x] 聚焦回归通过：`92 passed`；stream consumer 回归通过：`75 passed`。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py tests/run_agent/test_run_agent_codex_responses.py
scripts/run_tests.sh tests/gateway/test_stream_consumer.py
```

---

# Hermes Model Traffic Optimization

## Goal

将当前 Hermes official 环境从“Opus 作为隐性默认运行模型”调整为“GPT 5.5 默认执行，Opus 仅保留为显式规划备用”。成功标准是：普通 Feishu turn、auxiliary 任务、agent-system execution/audit、cron job 默认不再消耗 Opus；agent-system 命中时不会在进入 bridge 前触发主模型压缩；路由日志不再把 planning 误写成父模型。

## Scope

- `/Users/frank/.hermes/config.yaml`：默认模型和 auxiliary 任务切到 `openai-codex / gpt-5.5`，增加默认关闭的 `agent_system.planning_llm` 配置。
- `/Users/frank/.hermes/cron/jobs.json`：两个 Hermes cron job 模型切到 `openai-codex / gpt-5.5`，保留原 enabled/state。
- `run_agent.py`：agent-system pre-LLM short-circuit 提前到系统提示构建和 preflight compression 之前。
- `agent_system/cli_bridge.py`：路由日志改为 `planning=local planner`，避免误导。
- `hermes_cli/config.py`：补充 `agent_system.planning_llm` 默认配置，默认关闭。
- 聚焦测试覆盖 agent-system 命中时不会触发 preflight compression。

## Non-goals

- 不改变 agent-system execution/audit 的 GPT 5.5 目标模型。
- 不启用真实 Opus planning LLM；本轮只落默认关闭的配置入口。
- 不回撤当前工作区已有的无关改动。

## Validation

- `rg "claude-opus-4-7|auto|gpt-5.5" ~/.hermes/config.yaml ~/.hermes/cron/jobs.json`
- `scripts/run_tests.sh tests/agent_system/test_cli_bridge.py tests/agent_system/test_model_routing.py`
- `git diff --check`
- 重启 Gateway 后确认进程仍在运行。

## Progress

- [x] 只读确认当前 Opus 消耗来源：顶层默认模型、auxiliary auto、cron、agent-system bridge 位置。
- [x] 更新本地配置和 cron job。
- [x] 调整代码路由和日志。
- [x] 补充并运行测试：第一轮聚焦回归 `29 passed`，修正 planning/react 后聚焦回归 `45 passed`，`git diff --check` 通过。
- [x] 重启 Gateway 并确认状态：新 PID 97146，Feishu connected，active_agents=0。

## Decision Log

- 默认运行模型切到 `openai-codex / gpt-5.5`，优先降 Opus 消耗。
- `title_generation` 继续走 Kimi，不切 GPT 5.5。
- `planning_llm` 在当前 Hermes 环境启用，但只服务 agent-system 规划阶段；仓库默认配置仍保持关闭，避免新安装环境隐性消耗 Opus。
- 修正：用户明确要求规划阶段保留 Opus，且规划包括 initial plan 与 audit 之后的 react/re-plan。所谓“受限”应限制 Opus 的职责边界、上下文输入和触发阶段，而不是把规划关掉或只允许首次调用。
- 当前实现：`initial_plan` 与 `post_audit_react` 走 `agent_system.planning_llm`；execution/audit 子节点继续按 phase routing 使用 GPT 5.5。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
git status --short
sed -n '1,160p' /Users/frank/.hermes/config.yaml
jq -r '.jobs[] | [.id,.name,.enabled,.state,.model,.provider] | @tsv' /Users/frank/.hermes/cron/jobs.json
scripts/run_tests.sh tests/agent_system/test_cli_bridge.py tests/agent_system/test_model_routing.py
```

---

# Real Feishu Knowledge Capture Landing

## Goal

将已在 dev 验证的“模型自主判断写入业务知识”能力同步到 official，并在真实 Feishu 身份上下文下完成首条 `yang_ma` 产品线知识沉淀。成功标准是：Feishu 张嫄 open_id 可通过 ACL，`knowledge_write` 在 `hermes-feishu` 默认可见，阿基米德 Charter 核心事实可 upsert 到 gbrain，并产生授权审计记录。

## Scope

- `toolsets.py`：默认 `hermes-cli` / `hermes-feishu` 启用 `knowledge_query` 和 `knowledge_write`。
- `hermes_cli/tools_config.py`：工具配置页展示 `knowledge`，并修复显式空 toolset 不应被插件默认补回的边界。
- `agent/prompt_builder.py` + `run_agent.py`：仅当 `knowledge_write` 可用时注入自动业务事实沉淀协议。
- `tools/knowledge_tool.py`：Gateway Feishu `ou_xxx` 规范化为 `feishu:ou_xxx`，保留 raw fallback。
- `tests/...`：覆盖默认可见性、提示词注入和 Feishu 身份解析。
- `/Users/frank/.hermes/knowledge/users.yaml`：新增张嫄 `yang_ma` 普通知识权限（不提交）。

## Non-goals

- 不把整段飞书聊天或完整 Charter 原文入库。
- 不开放张嫄财务知识权限。
- 不绕过 `source_uri`、ACL 或审计。
- 不回撤 official 中已有的无关脏改。

## Validation

- `scripts/run_tests.sh tests/hermes_cli/test_tools_config.py tests/agent/test_prompt_builder.py tests/agent/test_knowledge_system_prompt.py tests/tools/test_knowledge_tool.py tests/agent/test_knowledge_acl.py tests/agent/test_knowledge_manager.py tests/agent/test_knowledge_audit.py -q`
- Feishu session 模拟：`platform=feishu`、`user_id=ou_92e78aea6cb26fd9f159aa5b367e4e84`、`chat_id=oc_fbcdc70ecae72e4b87bbb82c1fd6e364` 调用 `knowledge_write`。
- 查询 `yang_ma` + `阿基米德 核心升级点` 命中 `pl-yang_ma-general-archimedes-charter-core-upgrades-20260511`。
- 审计日志包含 `action=write`、`granted=true`、`product_line_id=yang_ma`、Charter `source_uri`。
- `hermes gateway restart` 后 Gateway `running`，Feishu `connected`。

## Progress

- [x] official 同步运行时必需改动。
- [x] official 回归测试通过：`211 passed, 1 skipped`。
- [x] 张嫄 ACL 已写入真实 users registry。
- [x] 首条阿基米德 Charter 知识写入成功，查询命中预期 slug。
- [x] 审计记录确认授权写入。
- [x] Gateway 已重启，实际进程为 `/Users/frank/.hermes/hermes-agent-official/venv/bin/python -m hermes_cli.main gateway run --replace`，Feishu connected。

## Decision Log

- 张嫄只授权 `yang_ma` 普通知识，`finance_product_line_ids` 保持空。
- 首条知识 `confidence=draft`，因为 Charter 属于草稿/立项阶段材料。
- 使用确定性 `doc_slug=archimedes-charter-core-upgrades-20260511`，重复执行按 gbrain `put` upsert。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
scripts/run_tests.sh tests/hermes_cli/test_tools_config.py tests/agent/test_prompt_builder.py tests/agent/test_knowledge_system_prompt.py tests/tools/test_knowledge_tool.py tests/agent/test_knowledge_acl.py tests/agent/test_knowledge_manager.py tests/agent/test_knowledge_audit.py -q
python - <<'PY'
from pathlib import Path
print(Path('/Users/frank/.hermes/knowledge/users.yaml').read_text())
PY
cat /Users/frank/.hermes/gateway_state.json
```

---

# Agent-System Dynamic Planner Sync

## Goal

将 dev 环境中已验证的动态 Planner 修复同步到 official：普通任务仍可进入 agent_system，但由主专家动态生成 TaskSpec / Pipeline，避免非 VOC 任务误进 `voc_insight`，并拆分飞书 reply 引用上下文，避免引用内容污染当前意图。

## Scope

- official 中新增 `agent_system/planner.py` 和 artifact/doc/report 相关技能。
- 合并 `cli_bridge.py` 的 PlannerEngine 入口，保留 builder 模式、progress callback、模型路由和输出选择器。
- 合并 `runtime.py` 的 `run_dynamic_pipeline`、planning audit 元数据和 ephemeral expert 支持，保留心跳与任务规划进度事件。
- 只追加 routes 新流程，不改旧流程的线上配置。
- 合并聚焦测试，保留 official 的 Codex auth fail-closed 与 progress 测试。

## Validation

- `python -m py_compile agent_system/planner.py agent_system/cli_bridge.py agent_system/runtime.py`
- `scripts/run_tests.sh tests/agent_system/test_cli_bridge.py tests/agent_system/test_runtime.py tests/agent_system/test_model_routing.py`
- `git diff --check`
- 手工探针验证：转云文档/状态查询/交付结果/飞书 reply 转文档不进 `voc_insight`；真实 VOC 分析才进 `voc_insight`；普通问候不进 agent_system。

## Progress

- [x] 只读确认 dev 已有 Planner，official 缺 planner/new skills 且仍使用 `_IMPLICIT_PIPELINE_MAP`
- [x] 新增 planner 与五个非 VOC 产物/文档技能目录
- [x] 合并 cli_bridge 动态 Planner 入口和飞书 reply 拆分
- [x] 合并 runtime 动态 pipeline、planning_meta 审计、ephemeral expert 支持
- [x] routes 只追加 artifact/doc/report/dashboard_from_artifact flows
- [x] 运行验证并记录结果：py_compile 通过，聚焦测试 `42 passed`，`git diff --check` 通过，手工探针符合预期

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
git status --short
rg -n "PlannerEngine|run_dynamic_pipeline|artifact_status_flow" agent_system/cli_bridge.py agent_system/runtime.py agent_system/scheduler/main_scheduler/routes.json
scripts/run_tests.sh tests/agent_system/test_cli_bridge.py tests/agent_system/test_runtime.py tests/agent_system/test_model_routing.py
```

---

# Agent-System Model Routing Fix

## Goal

修复 Hermes agent-system 的模型路由问题：insight_flow / dashboard_flow 中的执行节点（voc_insight、ops_dashboard、briefing）通过 delegate_task 静默继承父代理 claude-opus-4-7。目标是执行/audit 节点改用 kimi-for-coding (via kimi-coding provider)，规划/DAG 路由保持 claude-opus-4-7。同时修复 `_format_final_response` 捞历史旧报告的 bug。

## Root Cause

1. `config.yaml` 中 `delegation.model/provider` 均为空字符串
2. `_resolve_delegation_credentials` 返回全 None → `_build_child_agent` 执行 `effective_model = model or parent_agent.model` = `claude-opus-4-7`
3. kimi-coding provider 已在 `auth.json credential_pool` 中配置（key 完整），可直接用于 delegation

## Changes

1. `~/.hermes/config.yaml` — 设置 `delegation.model: kimi-for-coding` / `delegation.provider: kimi-coding`；新增 `agent_system.models` 文档节
2. `agent_system/cli_bridge.py` — `_make_delegate_skill_executor` 新增执行模型日志；`_format_final_response` 按 run_id 时间戳过滤旧文件
3. dev workspace 同步相同改动

## Validation

1. 重启 gateway
2. 触发 insight_flow / dashboard_flow 测试任务
3. 日志中规划阶段 claude-opus-4-7，执行节点 kimi-for-coding

## Status

- [x] 根因分析完成
- [x] config.yaml：delegation.model=kimi-for-coding，delegation.provider=kimi-coding；agent_system.models 文档节
- [x] cli_bridge.py（official + dev）：执行模型日志 + stale-report 时间戳过滤
- [x] gateway 重启：PID 51172，Feishu 已连接
- [x] 验证：凭据解析 PASS，时间戳解析 PASS，12 测试通过（1 个预存在失败）

---

# Kimi Fallback Real Request Repair Plan

## Goal

修复 Hermes fallback 到 Kimi 后的 HTTP 404。成功标准是：真实 Kimi API smoke test 返回 200，Hermes fallback 使用真实 key 可访问的 OpenAI-compatible Chat Completions endpoint 和 `/models` 返回的模型名，`xhigh` 作为 Hermes 内部抽象映射为 Kimi thinking 请求参数，而不是透传 `output_config.effort`。

## Scope

- 用最小真实请求验证 Kimi key、base_url、endpoint、model。
- 将 `/Users/frank/.hermes/config.yaml` 的 fallback 模型保持为真实 `/models` 返回的 `kimi-for-coding`，并保留 `agent.reasoning_effort=xhigh`。
- 修正 Kimi provider 的 base_url / api_mode 解析，避免 `sk-kimi-*` 自动落到 `https://api.kimi.com/coding/`。
- 修正 Chat Completions Kimi 请求构造：不发送 `output_config`，按官方参数启用 thinking、max_tokens、temperature、stream。
- 增加 sanitized debug log，打印 provider/model/base_url/endpoint/stream/max_tokens/thinking，不打印 API key。
- 增加聚焦单测和真实 smoke 脚本。

## Non-goals

- 不修改无关飞书消息路由、专家层 UI、Gateway progress 逻辑。
- 不暴露或打印任何 Kimi API key。
- 不把 OpenAI Codex 主模型切换掉；本轮只修 fallback。

## Context

- 当前配置为 `fallback_providers: kimi-coding / kimi-for-coding`，且 `agent.reasoning_effort=xhigh`。
- 之前为了尝试 xhigh 修改了 Anthropic adapter，使 Kimi `/coding` 发送 `output_config.effort=xhigh`；这与 Kimi 官方 OpenAI-compatible Chat Completions 文档不一致，且可能导致 404/参数错误。
- 真实验证显示：当前 `sk-kimi-*` key 访问 `https://api.moonshot.ai/v1` 返回 401；访问 `https://api.kimi.com/coding/v1/models` 返回 200，且唯一模型是 `kimi-for-coding`，display name 为 Kimi-k2.6。
- `https://api.kimi.com/coding/v1/chat/completions` 在带 Coding Agent User-Agent 时返回 200；因此本轮以该 OpenAI-compatible Chat Completions endpoint 修复 fallback。

## Milestones

1. 真实 curl/smoke 验证 key、endpoint、model。
2. 修正配置和 provider/runtime 路由。
3. 修正 Kimi Chat Completions 参数映射与日志。
4. 增加测试和 smoke 脚本。
5. 运行验证并重启 Gateway。

## Validation

- `curl https://api.moonshot.ai/v1/chat/completions ... model=kimi-k2-thinking` 预期对当前 key 返回 401，用于确认 key 类型。
- `curl https://api.kimi.com/coding/v1/models` 预期返回 `kimi-for-coding`。
- `curl https://api.kimi.com/coding/v1/chat/completions ... model=kimi-for-coding` 预期返回 200。
- `scripts/run_tests.sh tests/agent/transports/test_chat_completions.py tests/hermes_cli/test_api_key_providers.py`
- `MOONSHOT_API_KEY=... python scripts/smoke_test_kimi_fallback.py`
- `venv/bin/python -m hermes_cli.main gateway restart`

## Progress

- [x] 确认当前仓库有未提交无关改动，保留不动。
- [x] 核对官方文档方向：Moonshot Chat Completions，而不是 Kimi `/coding` Anthropic path。
- [x] 完成真实 curl 验证：Moonshot endpoint 401，Kimi Coding `/models` 和 `/chat/completions` 200。
- [x] 完成配置和代码修正。
- [x] 完成测试与 smoke。
- [x] 重启 Gateway 并记录最终状态：launchd service definition 已匹配当前 checkout，Gateway loaded，PID 59302。
- [x] 触发真实 Hermes chat 验证 fallback：session `20260506_103454_feafb9` 返回 `OK`，agent.log 记录 `provider=kimi-coding model=kimi-for-coding base_url=https://api.kimi.com/coding/v1/ endpoint=/chat/completions ... thinking={'type': 'enabled', 'keep': 'all'}`。

## Decision Log

- 不再把 `xhigh` 直接透传给 Kimi；它只映射为 Kimi thinking 模型的请求策略。
- 不选 `kimi-k2-thinking`，因为当前 key 对 Moonshot endpoint 返回 401；按真实 `/models` 结果使用 `kimi-for-coding`。
- 对 `sk-kimi-*` 继续使用 `https://api.kimi.com/coding/v1`，但运行协议改为 OpenAI-compatible Chat Completions 的 `/chat/completions`，不再走 Anthropic `/messages`。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
sed -n '1,40p' /Users/frank/.hermes/config.yaml
sed -n '200,280p' agent/transports/chat_completions.py
sed -n '860,950p' hermes_cli/auth.py
git status --short
```

---

# Codex Switcher Takeover Import Plan

## Goal

实现一次性 takeover import：从 Codex Switcher 账号池复制 token bundle 到 Hermes `credential_pool.openai-codex`，由 Hermes 后续负责刷新和轮转，并归档 Switcher 原 token store，避免两个程序共用同一批 refresh token。

## Scope

- 增加正式命令 `hermes auth import-codex-switcher --provider openai-codex --mode takeover [--dry-run]`。
- 增加正式命令 `hermes auth test openai-codex --label <label>`，输出仅包含 label/provider/auth_mode/status。
- 自动定位并解析 Codex Switcher 存储，当前真实文件为 `/Users/frank/.codex-switcher/accounts.json`。
- 导入前备份 Hermes auth store，并设置安全权限。
- 导入时重建 Hermes credential metadata，不迁移 Switcher 运行态、冷却、错误状态。
- 导入成功后归档 Switcher token store，确保 takeover 不是共享。
- 更新 `credential_pool_strategies.openai-codex=least_used`。

## Non-goals

- 不做实时同步，不做 symlink，不让 Hermes 和 Codex Switcher 同时读写同一份 token。
- 不打印 access_token、refresh_token、id_token、Authorization、Bearer 或完整 token 字段。
- 不删除 Switcher 数据；只做归档或脱敏保留。

## Context

- 当前 Hermes `openai-codex` 池只有 1 个账号，且状态为 429 rate-limited。
- Codex Switcher 存储文件 `/Users/frank/.codex-switcher/accounts.json` 包含 4 个账号，结构为 `accounts[].auth_data.{access_token, refresh_token, id_token, account_id, type}`。
- Hermes 代码当前故意不在运行时自动读取 `~/.codex/auth.json`，以避免 refresh token 被不同程序复用。

## Milestones

1. 只读定位 Switcher 存储并输出非敏感摘要。
2. 实现 import/test 命令与单测。
3. dry-run 验证。
4. 正式导入、备份 Hermes auth store、归档 Switcher token store。
5. 更新 config、运行 smoke test、重启 Gateway。

## Validation

- `hermes auth list openai-codex`
- `hermes auth import-codex-switcher --provider openai-codex --mode takeover --dry-run`
- `hermes auth import-codex-switcher --provider openai-codex --mode takeover`
- `hermes auth test openai-codex --label <label>`
- `scripts/run_tests.sh tests/hermes_cli/test_codex_switcher_import.py`
- `git diff --check`

## Progress

- [x] 确认当前 Hermes `openai-codex` 池只有 1 个 rate-limited 账号。
- [x] 定位 Switcher token store：`/Users/frank/.codex-switcher/accounts.json`，发现 4 个账号。
- [x] 实现正式命令和测试。
- [x] dry-run 验证：只输出来源、账号数、label、auth_mode、token 布尔状态、label 冲突和 action。
- [x] 正式导入和归档：导入 4 个账号，Hermes auth backup 为 `/Users/frank/.hermes/auth.json.bak.20260506-105235`，Switcher 原 token store 归档到 `/Users/frank/.codex-switcher-archived/accounts.imported-to-hermes.20260506-105235.json`。
- [x] smoke test、重启 Gateway、总结最终状态：3 个导入账号 auth test 通过，1 个导入账号 401 且刷新失败后标记短期 exhausted；Hermes chat session `20260506_105508_4f2a95` 返回 `OK`；Gateway loaded，PID 70571。

## Decision Log

- takeover import 后，Switcher token store 必须归档，不能继续让 Switcher 使用同一批 refresh token。
- 导入只复制 token bundle 和账号标识；Hermes 自己生成 credential id、状态、计数和轮转元数据。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
hermes auth list openai-codex
ls -la /Users/frank/.codex-switcher /Users/frank/.codex-switcher-archived 2>/dev/null
git status --short
```

---

# Gateway Dynamic Task Plan Progress Rendering Plan

## Goal

在 Gateway 工具进度模块中实现动态任务规划刷新与执行记录追加。成功标准是：`("__task_plan__", plan_text)` 能替换当前任务规划区域，`("__execution_log__", log_line)` 能持续追加执行流水，渲染时固定组合为“最新任务规划 + 完整执行记录”，并兼容当前 leading “专家层调度 / 任务规划”正文抽离逻辑。

## Scope

- 扩展 official `gateway/run.py` 的 progress queue 协议，新增 `__task_plan__` 和 `__execution_log__` 事件。
- 将工具启动进度改为结构化执行记录事件，保留 dedup 计数能力。
- 将 interim/final 的 leading 专家层/任务规划 UI 注入为结构化任务规划事件，支持后续刷新替换。
- 更新快速完成时的 progress queue 兜底 flush，使用同一套任务规划 + 执行记录渲染状态。
- 补充 Gateway 测试，覆盖任务规划替换、执行记录追加、最终正文剥离和普通进度兼容。

## Non-goals

- 不改变 DAG、Skill、人工审批和复盘运行逻辑。
- 不实现独立前端组件；本轮仍通过现有 Gateway 工具进度消息渲染。
- 不要求模型每次都输出任务规划；仅在收到结构化事件或 leading 规划块时刷新。

## Context

- 当前 Gateway 工具进度由 `progress_queue` 驱动，已有 `("__dedup__", msg, count)` 事件。
- 当前 working tree 已有任务规划标题归一化和执行记录分区的未提交逻辑，本轮在其上继续实现替换/追加状态模型。
- 用户要求模板顺序为：全局任务规划、专家分工、当前阶段任务规划、执行记录。

## Validation

- `python -m py_compile gateway/run.py tests/gateway/test_run_progress_topics.py`
- `scripts/run_tests.sh tests/gateway/test_run_progress_topics.py`
- `scripts/run_tests.sh tests/agent_system/test_runtime.py tests/agent_system/test_cli_bridge.py`
- `git diff --check`

## Progress

- [x] 完成现有 progress queue 和未提交变更核查。
- [x] 实现结构化任务规划/执行记录事件。
- [x] 补充回归测试。
- [x] 完成验证。

## Decision Log

- `__task_plan__` 事件替换当前规划，不保留旧规划文本。
- `__execution_log__` 事件追加到执行记录区，不覆盖历史记录。
- 旧式 raw string 仍兼容：任务规划标题开头的 raw string 视为规划刷新，其他 raw string 视为执行记录追加。
- dedup 只作用于执行记录最后一行，不影响任务规划区域。
- 验证结果：`scripts/run_tests.sh tests/gateway/test_run_progress_topics.py` 通过 27 个测试；`scripts/run_tests.sh tests/agent_system/test_runtime.py tests/agent_system/test_cli_bridge.py` 通过 11 个测试；`git diff --check` 通过。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
sed -n '100,150p' gateway/run.py
sed -n '9950,10130p' gateway/run.py
sed -n '10980,11045p' gateway/run.py
git status --short --branch
```

---

# Gateway Expert Layer UI Progress Injection Plan

## Goal

将 assistant 输出开头的“专家层调度”UI 块从正文中抽离，并在 Gateway 工具进度模块中展示。成功标准是：`gateway/run.py` 能识别 leading expert layer UI，`_interim_assistant_cb` 和 final response 都能把该 UI 注入 `progress_queue`，最终正文不重复携带 UI 内容，普通中间消息、Skill 渲染、DAG/Skill/复盘闭环不受影响。

## Scope

- 在 official `gateway/run.py` 增加 `_extract_leading_expert_layer_ui(...)`。
- 在 `_interim_assistant_cb` 里将 leading expert layer UI 写入工具进度队列，并继续发送剩余普通 commentary。
- 在 final response 返回前剥离 leading expert layer UI，并写入工具进度队列。
- 增加 Gateway 聚焦回归测试，验证进度模块展示 UI、正文剥离 UI、普通 commentary 不受影响。

## Non-goals

- 不改变 agent_system DAG、Skill 执行、复盘和审计逻辑。
- 不改变普通工具进度事件格式。
- 不引入新的 UI 协议；本轮仅兼容当前 leading “专家层调度”块。

## Context

- dev 环境已有 `_extract_leading_expert_layer_ui(...)`，规则为仅识别正文开头的 `#` 到 `######` “专家层调度”标题块，遇到首个空行后切分。
- official Gateway 已有 `progress_queue`、`send_progress_messages()` 和 `_interim_assistant_cb`，但没有 expert layer UI 抽离。
- final response 在 run_sync 内返回，progress task 在外层 finally 中取消并 drain 队列，因此 final response 注入的 UI 仍可被最终编辑到工具进度消息。

## Milestones

1. 复用 dev 的 expert layer UI 提取逻辑。
2. 接入 interim assistant callback。
3. 接入 final response 剥离和 progress_queue 注入。
4. 补充 Gateway 测试。
5. 运行聚焦验证并提交本地改动。

## Validation

- `python -m py_compile gateway/run.py tests/gateway/test_run_progress_topics.py`
- `scripts/run_tests.sh tests/gateway/test_run_progress_topics.py`
- `git diff --check`

## Progress

- [x] 完成 official 与 dev 差异核查。
- [x] 完成 `gateway/run.py` 注入逻辑。
- [x] 完成 Gateway 回归测试。
- [x] 完成聚焦验证。

## Decision Log

- 仅抽取 leading “专家层调度”标题块，避免普通说明或其他标题被误剥离。
- UI 注入工具进度模块时保留 `🧭` 前缀，与 dev 行为一致，便于用户识别专家层展示。
- tool progress 关闭时不额外发送 expert UI，保持“工具进度模块显示”语义，不把 UI 重新塞回正文。
- progress task 取消时如果队列里只有 final expert UI 且尚未创建进度消息，也会发送一次完整进度内容，避免快速完成的 final UI 丢失。
- 验证结果：`scripts/run_tests.sh tests/gateway/test_run_progress_topics.py` 通过 26 个测试，覆盖 progress_queue 展示、正文剥离、普通 commentary 保留。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
sed -n '90,170p' gateway/run.py
sed -n '10270,10310p' gateway/run.py
sed -n '11090,11140p' gateway/run.py
git status --short --branch
```

---

# Agent System Runtime Closed Loop Plan

## Goal

将专家层模板中的“主/辅专家 + Skill + DAG 调度 + 审计 + 复盘 + 人工介入”占位落到固定功能闭环运行器，并补齐本轮必落地的五个运行能力：CLI 主循环自动触发、人工审批 UI、多层子智能体、真实 Skill 执行绑定、自动 Skill 权重回写。成功标准是本地 `agent_system` 能读取 `scheduler/main_scheduler/routes.json`、`experts/*/expert.json`、`skills/*/skill.json`，按 DAG 生成单节点任务包，平行执行主/辅专家各自的真实 Skill / Agent 调用，处理 optional、user_gate、阻塞异常，写入 `audit/audit.jsonl`、`audit/review_summary.json`、`skill_weights.json`，并沉淀专家和 Skill 私域经验。

## Scope

- 新增轻量运行时模块，专门承接 agent_system 示例闭环执行。
- 新增 CLI 桥接模块，只有用户消息明确触发 `agent_system` 且命中 pipeline 时，才接管默认聊天主循环并自动执行闭环。
- 新增 agent_system 独立人工审批适配层，底层可复用 CLI / Gateway 回调，输出结构化审批决策。
- 让运行器根据 `delegation.max_spawn_depth` 生成 leaf / orchestrator 任务包，保持 DAG 依赖在多层委托下可追踪。
- 通过 `delegate_task` 绑定真实 Agent / LLM 执行默认 Skill，保留本地 executor 作为测试和离线回退路径。
- 生产路径记录线上 Agent / LLM 执行模式、凭据状态和 API 调用观测，避免“看起来执行但实际只是占位”。
- CLI 桥接必须在主 Agent 执行线程绑定之后运行，确保真实子智能体继承中断、活动和审批链路。
- 保留现有模板占位、权重公式、异常映射、人工介入字段、私域经验积累和复盘字段。
- 增加聚焦测试覆盖 DAG、optional、user_gate、审计、复盘和权重更新。
- 最小改动主 Agent 大循环，只插入窄触发桥接，不改变普通对话、工具循环或 prompt cache 语义。

## Non-goals

- 不让普通聊天自动进入 agent_system；必须由明确触发词和 pipeline 命中共同触发。
- 不重写 CLI / Gateway 的底层输入控件；agent_system 只提供独立审批适配层和结构化决策语义。
- 不让辅专家管理全局 DAG 或跨节点调度。
- 不重写 `delegate_task` 子智能体实现，只从 agent_system 桥接调用它。

## Context

- 现有 `agent_system/hermes_sdk.py` 负责初始化 Skill、Expert、Scheduler 和 Audit 资产。
- `routes.json` 已包含 `pipeline_id`、`depends_on`、`trigger`、`optional`、`user_gate`、`final_output`、`supervision.primary_expert` 和 `secondary_experts`。
- 现有 `delegate_task` 已支持 `role='orchestrator'` 和可配置 `delegation.max_spawn_depth`；本轮运行器需要把这个配置反映到任务包，并在 CLI 桥接中真实调用 `delegate_task`。
- `clarify` 工具已通过 `AIAgent.clarify_callback` 接入 CLI / Gateway 交互；本轮 `user_gate` 通过独立审批适配层复用该回调，收集 `human_input_summary` 和审批决策。
- 权重公式沿用模板：`Skill_Weight = Base_Weight + Success_Rate*0.4 + Output_Quality*0.3 - Exception_Count*0.2 + Dynamic_Coverage_Frequency*-0.1`，结果需要限制在 0-100。
- 用户补充“经验固化版”要求：模板占位与运行闭环必须明确分层，并增加静态验证与运行验证，避免后续再次出现占位和执行不一致。

## Milestones

1. 新增运行器：加载资产、构建 DAG、生成主/辅专家单节点任务包。
2. 实现执行闭环：节点执行、optional、user_gate、异常映射、审计 JSONL。
3. 实现复盘与权重：复盘摘要、权重建议和 `skill_weights.json` 回写。
4. 补充测试并运行聚焦验证。
5. 固化经验准则：模板增加占位 / 运行闭环分层说明、验证要求，运行器支持可配置 `max_spawn_depth` 且默认保持 1。
6. 接入 CLI 主循环：新增窄触发桥接，自动运行指定 pipeline，并返回审计、复盘和权重产物摘要。
7. 落地真实 Skill 绑定：CLI 桥接通过 `delegate_task` 调用真实 Agent / LLM，运行器继续支持测试 executor。
8. 落地人工审批：`user_gate` 缺人工输入时调用 `clarify_callback`，人工结论进入审计、复盘和权重数据。
9. 补强线上落地观测：审计记录必须包含 `real_skill_execution`、`skill_execution_modes`、`human_review_ui_available` 和线上 API 调用观测字段。
10. 正式审批语义：人工审批输出 `approved/blocked/missing` 决策，阻塞或退回复核会阻断下游 DAG。

## Validation

- `python -m py_compile agent_system/hermes_sdk.py agent_system/runtime.py agent_system/cli_bridge.py agent_system/human_approval.py agent_system/init_experts.py tests/agent_system/test_runtime.py tests/agent_system/test_cli_bridge.py`
- `scripts/run_tests.sh tests/agent_system/test_runtime.py tests/agent_system/test_cli_bridge.py`
- `scripts/run_tests.sh tests/tools/test_delegate.py tests/tools/test_delegate_toolset_scope.py tests/tools/test_skills_tool.py`
- `rg -n "human_review_required|human_input_summary|human_review_decision|human_review_blocking|skill_weights.json|audit.jsonl|optional_failed|max_spawn_depth|delegate_task|orchestrator|real_skill_execution|skill_execution_modes|online_llm_call_observed" agent_system/runtime.py agent_system/cli_bridge.py agent_system/human_approval.py tests/agent_system`
- `rg -n "CLI 主循环|人工审批|真实 Skill|真实 Agent|max_spawn_depth|自动回写|运行验证|线上凭据|API 调用观测" agent_system/EXPERT_LAYER_TEMPLATE.md agent_system/experts/*/EXPERT.md`

## Progress

- [x] 完成只读核查，确认当前缺少运行时闭环执行器。
- [x] 新增运行器。
- [x] 增加测试。
- [x] 完成验证。
- [x] 固化模板占位 / 运行闭环分层和验证要求。
- [x] 接入 CLI 主循环窄触发。
- [x] 接入人工审批 UI 回调。
- [x] 接入真实 `delegate_task` Skill 执行绑定。
- [x] 验证多层子智能体任务包和权重自动回写。
- [x] 刷新专家文档并完成聚焦回归测试。
- [x] 补强线上功能落地审计字段和执行线程绑定位置。
- [x] 落地独立人工审批适配层和审批阻塞语义。
- [x] 完成正式环境闭环模板字段扫描和最终验证记录。

## Decision Log

- 选择新增 `agent_system/runtime.py`，而不是把执行逻辑放进模板生成器或主 Agent 循环。
- 运行器默认使用本地被动 Skill 执行，提供 `skill_executor` 回调作为真实 Skill/Agent 接入口。
- `user_gate=true` 表示节点执行后需要人工输入确认；缺少人工输入时节点记录为 `blocked`，下游非 optional 依赖暂停。
- optional 节点失败或阻塞不阻断主流程，依赖 optional 节点的下游可继续。
- 辅专家只承接单节点任务包并调用自身可用 Skill，不管理全局 DAG。
- 权重更新固定生成复盘建议并回写 `skill_weights.json`。
- 私域经验固定追加专家和 Skill 的运行摘要，形成长期能力积累。
- 同一节点内主/辅专家 Skill 调用并行执行，结果按主专家优先、辅专家顺序稳定汇总。
- 模板必须明确区分“模板占位”和“运行闭环落地”；静态字段检查不能替代运行测试。
- `max_spawn_depth` 在运行器中可配置，模板示例和默认运行值保持为 1。
- 本轮 CLI 接入必须是窄触发，避免普通聊天被 agent_system 抢走。
- 人工审批由 `agent_system/human_approval.py` 提供独立适配层，底层复用 `clarify_callback(question, choices)`，保持 CLI、TUI 和 Gateway 的既有交互一致。
- 人工审批返回“阻塞并补充资料”“退回复核”等结果时，当前节点保持 blocked，下游非 optional 节点按 DAG 暂停。
- `max_spawn_depth > 1` 时任务包使用 `role='orchestrator'`，否则使用 `role='leaf'`，由 `delegate_task` 自身继续强制深度上限。
- 真实 Skill 绑定放在 `agent_system/cli_bridge.py`，运行器保持 executor 注入能力，方便测试和后续替换。
- CLI 桥接移动到 `run_conversation()` 的执行线程绑定之后，避免真实 `delegate_task` 运行时缺少中断和活动追踪上下文。
- 生产路径不在自动测试中消耗线上凭据，但 `cli_bridge` 默认执行真实 `delegate_task`；若凭据缺失或子智能体未产生 API 调用，会进入审计字段和异常复盘。
- 运行验证结果：`scripts/run_tests.sh tests/agent_system/test_runtime.py tests/agent_system/test_cli_bridge.py` 通过 9 个测试。
- 正式审批语义验证结果：`scripts/run_tests.sh tests/agent_system/test_runtime.py tests/agent_system/test_cli_bridge.py` 通过 11 个测试，覆盖审批放行和审批阻塞。
- 回归验证结果：`scripts/run_tests.sh tests/tools/test_delegate.py tests/tools/test_delegate_toolset_scope.py tests/tools/test_skills_tool.py` 通过 199 个测试。
- 格式验证结果：`git diff --check` 通过。
- 模板静态验证结果：`rg -n "人工审批|human_review_decision|human_review_blocking|human_review_channel|真实 Skill|真实 Agent|线上凭据|API 调用观测|运行验证" agent_system/EXPERT_LAYER_TEMPLATE.md agent_system/experts/*/EXPERT.md` 确认模板与四个专家文档均包含正式环境闭环字段。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-dev
```

优先查看：

```bash
sed -n '1,260p' agent_system/runtime.py
sed -n '1,220p' tests/agent_system/test_runtime.py
git status --short --branch
```

---

# Agent System Three-Layer Experience Isolation Plan

## Goal

将 Hermes Agent System 的私域经验从“统一追加摘要”升级为三层隔离闭环：系统级经验、专家级经验、Skill 级经验各自独立管理、独立写入、可追溯审计。成功标准是运行器、模板和测试都能证明：专家和 Skill 可以按规则读取上层上下文，但写入只进入自身层级；临时子专家产生的经验按专家/Skill 归属写入，不直接污染系统级经验；复盘摘要能说明本次更新了哪些层级经验。

## Scope

- 更新 `agent_system/runtime.py` 的经验写入逻辑，拆分系统级、专家级、Skill 级经验记录。
- 在任务包和 Skill 执行上下文中加入经验访问/写入策略字段，供真实 Agent / LLM 执行时参考。
- 更新 `review_summary.json` 和 `audit.jsonl` 的经验字段，记录经验归属、路径和写入原因。
- 更新 `EXPERT_LAYER_TEMPLATE.md` 及生成后的专家文档，明确三层经验隔离和访问规则。
- 补充测试，验证三层经验文件独立生成、内容不混写、复盘摘要包含经验更新记录。

## Non-goals

- 不实现新的长期记忆数据库或外部向量库。
- 不把 Skill 经验提升为专家级经验，也不让专家经验覆盖 Skill 经验。
- 不让临时子专家直接写系统级经验。
- 不改变已有 DAG、optional、user_gate、真实 `delegate_task`、权重公式和审计闭环。

## Context

- 当前运行器已有专家/Skill `MEMORY.md` 写入，但写入内容相同，尚未表达分层边界。
- `agent_system/hermes_sdk.py` 已有系统用户记忆目录 `memory/user_mem`，但运行器闭环缺少系统级经验摘要目录。
- 用户明确要求：系统级由 Hermes 主代理维护；专家级由对应专家维护并记录 Skill 使用；Skill 级由对应 Skill 维护执行历史、异常统计、复盘反馈；跨层允许读取，不允许跨层覆盖写入。

## Milestones

1. 定义运行器中的三层经验策略字段和写入记录结构。
2. 拆分经验写入：系统级、专家级、Skill 级分别写入不同目录和不同内容。
3. 将经验更新摘要写入 `review_summary.json` 和 `audit.jsonl`。
4. 更新模板和专家文档，固化三层隔离规则。
5. 补充并运行聚焦测试。

## Validation

- `python -m py_compile agent_system/runtime.py agent_system/hermes_sdk.py tests/agent_system/test_runtime.py`
- `scripts/run_tests.sh tests/agent_system/test_runtime.py tests/agent_system/test_cli_bridge.py`
- `scripts/run_tests.sh tests/tools/test_delegate.py tests/tools/test_delegate_toolset_scope.py tests/tools/test_skills_tool.py`
- `rg -n "三层经验|系统级经验|专家级经验|Skill级经验|experience_updates|memory_access_policy|write_scope" agent_system/EXPERT_LAYER_TEMPLATE.md agent_system/experts/*/EXPERT.md agent_system/runtime.py tests/agent_system`

## Progress

- [x] 明确三层经验隔离设计原则。
- [x] 更新运行器经验访问和写入字段。
- [x] 更新模板和专家文档。
- [x] 补充测试。
- [x] 完成验证。

## Decision Log

- 经验写入按执行角色归属，默认不跨层写入。
- 系统级经验只记录运行级全局摘要、用户偏好或全局规则信号；临时子专家不直接写系统级。
- 专家级经验记录该专家参与的节点、决策状态、异常、Skill 使用和复盘结果。
- Skill 级经验记录该 Skill 的调用次数、成功/异常、输出质量和复盘反馈。
- `review_summary.json` 作为复盘总索引，记录三层经验更新清单，但不把三个层级的经验正文混在一起。
- 运行验证结果：`scripts/run_tests.sh tests/agent_system/test_runtime.py tests/agent_system/test_cli_bridge.py` 通过 11 个测试，覆盖三层经验写入、审批和 DAG 闭环。
- 回归验证结果：`scripts/run_tests.sh tests/tools/test_delegate.py tests/tools/test_delegate_toolset_scope.py tests/tools/test_skills_tool.py` 通过 204 个测试。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-official
```

优先查看：

```bash
sed -n '1,260p' agent_system/runtime.py
sed -n '1,460p' agent_system/EXPERT_LAYER_TEMPLATE.md
sed -n '130,230p' tests/agent_system/test_runtime.py
```

---

# Agent System Expert Template Group Collaboration And Human Review Plan

## Goal

将专家层模板更新为“主/辅专家群体协作 + 平行 Skill 执行 + 碳基人工介入 + 调度层 DAG 约束”的版本。成功标准是后续生成的 `EXPERT.md` 明确：主专家负责任务判断、节点分配、复盘优先评估、默认 Skill 多重加载和动态覆盖规则；辅专家负责分配节点任务并独立调用 Skill；主/辅专家在执行阶段可平行调用 Skill，但必须遵守 DAG 依赖和调度顺序；人工复核结果进入审计、复盘和 Skill 权重优化。

## Scope

- 更新 `agent_system/EXPERT_LAYER_TEMPLATE.md` 作为群体协作 + 人工介入版本的标准模板。
- 更新 `agent_system/hermes_sdk.py` 中专家文档生成逻辑。
- 刷新 `agent_system/experts/*/EXPERT.md`。
- 只做文档和生成器优化，不接入真实运行时调度。

## Non-goals

- 不实现 `expert_task` 工具。
- 不修改 `delegate_task` 核心逻辑。
- 不改 `routes.json` 的执行语义。
- 不展开 Skill 内部步骤。
- 不让辅专家越权管理全局 DAG、跨节点并行控制或调度暂停。
- 不让专家模板替代调度层的运行时执行器。
- 不实现真实人工审批 UI，只保留 `human_review_required` 和 `human_input_summary` 等字段。

## Context

- 当前 `agent_system/experts/*/EXPERT.md` 由 `HermesExpertManager._write_expert_doc()` 生成，必须同步更新生成器。
- 用户已确认新版口径：主/辅专家可平行执行 Skill，辅专家执行分配节点任务；主专家在复盘优先评估和节点分配上保持主责；人工介入用于关键节点复核、异常确认和用户确认。
- 模板仍需保留默认 Skill 权重公式、动态覆盖占位、输入/输出字段单位、枚举可扩展、异常映射占位、复盘审计占位和 `max_spawn_depth=1`。
- 为避免下次运行 `init_experts.py` 覆盖手工文档，必须同步更新生成器。

## Milestones

1. 固化群体协作 + 人工介入版本的专家层标准模板文档。
2. 更新专家文档生成器，使每个专家文档自动包含新版模板结构。
3. 重新运行专家初始化脚本刷新现有专家文档。
4. 运行语法和内容校验，确认主/辅专家、人工介入、权重公式、异常映射和复盘字段齐全。

## Validation

- `source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || true; python -m py_compile agent_system/hermes_sdk.py agent_system/init_experts.py`
- `source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || true; python agent_system/init_experts.py`
- `rg -n "主/辅专家职责|碳基|人工介入|human_review_required|human_input_summary|Skill_Weight|max_spawn_depth=1|异常映射|动态覆盖|复盘与权重优化" agent_system/EXPERT_LAYER_TEMPLATE.md agent_system/experts/*/EXPERT.md`
- `rg -n "Callable Skills|辅专家.*全局 DAG|辅专家.*调度暂停|辅专家.*跨节点并行控制" agent_system/EXPERT_LAYER_TEMPLATE.md agent_system/experts/*/EXPERT.md || true`
- `git diff -- agent_system PLANS.md`

## Progress

- [x] 明确群体协作 + 人工介入新版口径。
- [x] 更新标准模板文档。
- [x] 检查生成器占位兼容性。
- [x] 刷新专家文档。
- [x] 完成验证。

## Decision Log

- 选择更新生成器，而不是只手改 `EXPERT.md`，因为专家文档是生成物，手改会被初始化脚本覆盖。
- 专家层文档允许出现主/辅专家平行执行 Skill 的说明，但执行阶段必须服从调度层 DAG 依赖和顺序。
- 辅专家执行被分配节点任务并独立调用 Skill、积累私域经验和 pipeline 数据，但不管理全局 DAG 或调度暂停。
- 人工介入只以字段和复盘输入占位表达，不实现审批 UI。
- 人工介入字段统一为 `human_review_required` 和 `human_input_summary`，进入输出、审计和复盘摘要，但不替代真实用户确认流程。
- 调度层负责 DAG、阻塞、暂停、审计汇总和复盘数据，不由专家模板实现运行时执行器。
- 动态覆盖只保留触发条件和处理逻辑，不固定可覆盖 Skill 名单。
- 生成器改为读取 `EXPERT_LAYER_TEMPLATE.md` 并替换专家占位与默认 Skill 表，避免模板和生成器内容双写漂移。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-dev
```

优先查看：

```bash
sed -n '1,260p' agent_system/EXPERT_LAYER_TEMPLATE.md
sed -n '605,660p' agent_system/hermes_sdk.py
git status --short --branch
```

---

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

---

# Final Output Selection Fix（Task #13）

## Goal

修复"用户要报告/云文档，但系统把执行记录发出去"的 bug。成功标准：final response 优先展示 analysis/report_generation 型 skill 的用户产物；云文档失败时如实告知；执行记录仅在无用户产物时作为 fallback（带标签）。

## Scope

- `agent_system/output_selector.py`（新建）— 产物分类 + 优先级选择
- `agent_system/cli_bridge.py` — `_make_delegate_skill_executor` 提取 `main_report_path`；`_format_final_response` 使用 output_selector
- `tests/agent_system/test_output_selector.py`（新建）— 3 个场景测试

## Non-goals

- 不改 runtime.py、skill.json、routes.json、gateway 层

## Milestones

1. 新建 output_selector.py + 单测（Scenario A/B/C）
2. 修改 cli_bridge.py 两处
3. 运行 scripts/run_tests.sh 验证无退化

## Validation

```bash
scripts/run_tests.sh tests/agent_system/test_output_selector.py tests/agent_system/test_cli_bridge.py tests/agent_system/test_runtime.py
```

## Progress

- [ ] 新建 agent_system/output_selector.py
- [ ] 修改 _make_delegate_skill_executor（提取 main_report_path）
- [ ] 修改 _format_final_response（优先 main_report_path，次选 select_output_files）
- [ ] 新建 tests/agent_system/test_output_selector.py
- [ ] 运行测试，确认无退化

---

# Dev / Official 环境完整整合（2026-05-14）

## Goal

将 `hermes-agent-official` 当前 snapshot 与 `hermes-agent-dev` 当前 Git 可见工作区完整整合到独立工作区，并在验证通过后合回 `codex/dev-env`。

## Scope

- 基线：`snapshot/hermes-local-20260514-224006` at `18bf580df`
- Dev 快照：`codex/dev-wip-snapshot-20260514-232334` at `071b80c62`
- 整合分支：`codex/integrate-dev-official`
- 整合工作区：`/Users/frank/.hermes/hermes-agent-integrate`

## Decisions

- 保留完整 Git 可见内容，包括 `dist/`、`dist_skills/`、`extracted_data/`、运行输出和本地快照。
- `agent_system` 核心入口、runtime、planner、routes 和模型路由测试以 official 较新版本为主，保留 planning LLM、progress heartbeat、internal skill call、防递归和 Codex auth fail-closed。
- `knowledge_tool.py` 与知识提示词测试以 dev 快照为主，保留 product-line alias、pending capture 和失败可恢复提示。
- `toolsets.py` 以 official 版本为主，因为它已包含 `codex_pipeline` 与 `knowledge_query` / `knowledge_write` 的并集。
- `PLANS.md` 主体保留 official 的现场计划记录，并在本节记录整合恢复信息；dev 知识系统计划同时保留在 `.plans/2026-05-10-knowledge-system-poc.md` 与 `KNOWLEDGE_SYSTEM_PLAN.md`。

## Validation

- `scripts/run_tests.sh tests/agent/test_knowledge_user_registry.py tests/tools/test_knowledge_tool.py tests/agent/test_prompt_builder.py tests/agent_system/test_model_routing.py tests/agent_system/test_cli_bridge.py tests/agent_system/test_runtime.py tests/hermes_cli/test_tools_config.py tests/tools/test_session_search.py`
- `scripts/run_tests.sh`

## Progress

- [x] 创建 dev WIP 快照分支并提交：`071b80c62`
- [x] 创建整合工作区与 `codex/integrate-dev-official`
- [x] 解决 merge 冲突并提交整合分支：`e8e257a8b`
- [x] 聚焦测试通过：277 passed, 1 skipped
- [x] 5 个代表性失败全部修复并验证（2026-05-15）
- [x] 完整测试验证：69 failed（17589 passed, 56 skipped），全部失败归类确认（2026-05-15）
- [ ] 测试通过后 merge 回 `codex/dev-env`

## Validation Notes

- 2026-05-14：新 worktree 没有本地虚拟环境；测试时临时创建 `.venv` 软链接指向 `/Users/frank/.hermes/hermes-agent-official/venv`，测试结束后删除，不纳入 Git。
- 2026-05-14：完整测试首次执行未进入 pytest，`scripts/run_tests.sh` 在 macOS bash 3.2 + `set -u` 下空参数展开触发 `ARGS[@]: unbound variable`。已改为有参/无参两个 `exec pytest` 分支后重跑。
- 2026-05-14：完整测试已进入 pytest 并跑完，结果为 17504 passed, 54 skipped, 82 failed, 22 errors。代表性失败包括 `tools.memory_tool.get_memory_dir` monkeypatch 参数不兼容、Anthropic beta header 期望缺少 `context-1m-2025-08-07`、builtin registry 期望列表缺少 `codex_pipeline_tool` / `feishu_sheet_tool` / `knowledge_tool`。按整合计划，未合回 `codex/dev-env`。
- 2026-05-15：复测聚焦整合用例，结果为 277 passed, 1 skipped。复核完整测试代表性失败仍存在：`tests/tools/test_memory_tool.py::TestMemoryStoreAdd::test_add_entry` error，`tests/agent/test_anthropic_adapter.py::TestBuildAnthropicClient::test_custom_base_url` failed，`tests/tools/test_registry.py::TestBuiltinDiscovery::test_matches_previous_manual_builtin_tool_set` failed，`tests/tools/test_code_execution_modes.py::TestResolveChildPython::test_project_with_broken_venv_falls_back` failed，`tests/run_agent/test_tool_arg_coercion.py::TestCoerceNumber::test_inf_stays_string_for_integer_only` failed。由于代表性失败已确认，未重复执行完整套件。
- 2026-05-15：建立归因矩阵并修复全部 5 个代表性失败（提交 87042c706..f5d9a33cf），5 passed 验证，聚焦测试 277 passed, 1 skipped。详细归因：
  - `test_memory_tool::test_add_entry`：official 引入 `get_memory_dir(user_id)` 签名，fixture 0-arg lambda TypeError → 更新为 `lambda *a, **kw: tmp_path`（3 处）
  - `test_custom_base_url`：`context-1m` 加入 `_COMMON_BETAS` 后 generic 第三方 URL 也携带 → `_common_betas_for_base_url` 对非 Azure/Bedrock 第三方端点剥除 context-1m
  - `test_matches_previous_manual_builtin_tool_set`：integrate 引入 3 个自注册工具（codex_pipeline_tool/feishu_sheet_tool/knowledge_tool）→ 更新 expected 集合（27→30）
  - `test_project_with_broken_venv_falls_back`：CONDA_PREFIX 环境泄漏导致回退到 conda python → patch.dict 补充 `CONDA_PREFIX=""`
  - `test_inf_stays_string_for_integer_only`：`_coerce_number` 对 inf 统一返回字符串 → 区分 integer_only：False 返回 float，True 返回字符串
  - 完整测试正在进行中
- 2026-05-15：复核 Claude Code 修复后状态：5 个代表性失败已通过（5 passed），聚焦整合测试继续通过（277 passed, 1 skipped）。但完整 `HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv scripts/run_tests.sh` 未通过，结果为 17527 passed, 54 skipped, 81 failed。主要剩余失败集中在 subagent stop hook、Anthropic/Claude Code credentials keychain 隔离、gateway approval/session/status、systemd/WSL service tests、file read/staleness guards、model_tools inf/nan 契约、clipboard WSL detection、TUI protocol/provider 等。按整合计划，仍不能 merge 回 `codex/dev-env`。
- 2026-05-15：Phase 3 修复提交（c33616f71、3d1e8b972）后完整套件结果：69 failed, 17589 passed, 56 skipped（560s）。失败归类：
  - **pre-existing official**（~47）：test_file_read_guards(6)、test_gateway_service(3)、test_gateway_wsl(2)、test_session_split_brain_11016(3)、test_status_command(3)、test_file_staleness(3)、test_file_state_registry(2)、test_phase3_semantic_search(2)、test_update_autostash(2)、test_provider_config_validation(2)、test_auth_codex_provider(2)、test_protocol(1)、test_make_agent_provider(1)、test_local_interrupt_cleanup(1)、test_web_server(1)、test_tencent_tokenhub_provider(1)、test_plugin_scanner_recursion(1)、test_cmd_update(1)、test_matrix(1)、test_gateway_shutdown(1) 等，以上在 official 基线已有
  - **xdist 并行 flaky**（22）：test_delegate(14)、test_clipboard::TestIsWsl(3)、test_resolve_path(2)、test_cli_skin_integration(1) — 单线程运行全部通过（test_delegate:120 passed；其余 isolated pass）；official 也有这些测试文件，official baseline 那次运行碰巧未触发并行冲突
  - **已修复 vs official**（+26）：test_memory_tool(2)、test_registry(1)、test_memory_tool_import_fallback(1)、test_code_execution_modes(1)、test_tool_arg_coercion(1)、test_anthropic_adapter(20)
  - **结论**：integrate 无代码回归，对 official 基线净改善 26 个测试。可执行 merge 到 `codex/dev-env`。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-integrate
git status --short
git diff --name-only --diff-filter=U
```

如需重来，保留 `codex/dev-wip-snapshot-20260514-232334` 不删，删除并重建 `codex/integrate-dev-official` 工作区即可。

---

# Production Readiness 机制 (2026-05-15)

## Goal
在 integrate 建立可验证、可迁移、可发布的 agent-system production readiness 机制，
让所有准入判断归一到 capability_readiness.py + readiness_manifest.json，
消除散落多处的 flag 检查。

## Scope
- agent_system/readiness_manifest.json（新增，权威 manifest）
- agent_system/capability_readiness.py（新增，统一 helper）
- agent_system/cli_bridge.py（修改：gate 移到 Opus 前）
- agent_system/runtime.py（修改：enforce 默认开启）
- agent_system/scheduler/main_scheduler/routes.json（修改：allowed_entrypoints）
- scripts/check_agent_system_readiness.py（新增，发布门禁）
- tests/agent_system/test_production_readiness.py（扩展至 14 个测试）

## Non-goals
- 不修改 official 环境
- 不重启 gateway（只给出建议命令）
- 不实现真正 skill executor（保留 system executor 模型）
- 不关闭 Opus planning_llm

## Definition of Done
1. 所有 route/skill 分类为 ready / non_ready / unknown（manifest 驱动）
2. Feishu/gateway 普通入口对 unknown 默认 blocked（return None）
3. Opus planning candidates 只包含 ready route
4. runtime 默认阻断 non-executable skill
5. 新增 route/skill 缺 readiness 元数据时 validate_readiness_manifest 报错
6. 张嫄养马类消息不进入 report_revision_flow，不调用 Opus，不执行空 skill
7. integrate 全量测试通过

## Route Inventory（初始分类）
- insight_flow → unknown
- dashboard_flow → unknown
- html_flow → unknown
- artifact_status_flow → unknown
- artifact_delivery_flow → unknown
- doc_publish_flow → unknown
- dashboard_from_artifact_flow → unknown
- report_revision_flow → non_ready（stub skills）

## Skill Inventory（初始分类）
- voc_insight, ops_dashboard, dashboard_html, audit, briefing,
  artifact_resolver, artifact_status, artifact_delivery, doc_publish,
  superpowers → unknown
- report_revision → non_ready

## Milestones
- [x] M1: readiness_manifest.json created
- [x] M2: capability_readiness.py created
- [x] M3: routes.json updated with allowed_entrypoints
- [x] M4: test_production_readiness.py extended to 14 tests (RED)
- [x] M5: cli_bridge.py updated (gate before Opus)
- [x] M6: runtime.py updated (enforce by default)
- [x] M7: scripts/check_agent_system_readiness.py created
- [x] M8: test fixtures migrated, all tests GREEN

---

# Hermes Knowledge Sedimentation Governance Plane Phase 5（2026-05-15）

## Goal

在 integrate 环境建立 Knowledge Sedimentation Governance Plane：KnowledgeCandidate 数据契约、AssetRouter 分层路由、IdentityResolver 身份解析、ScopeResolver scope 分类、PendingCapture 扩展（list/mark_terminal）、SedimentationMetrics 指标观测。修复 cli_bridge 三大 bug（身份 + 枚举 + pending on failure）。

## Scope

- `agent/knowledge_models.py`（修改：+KnowledgeCandidate, +TerminalState, +CandidateType）
- `agent/pending_capture.py`（修改：+platform/suggested_next_action/terminal_state, +list_pending, +mark_terminal）
- `agent/identity_resolver.py`（新增）
- `agent/scope_resolver.py`（新增）
- `agent/asset_router.py`（新增）
- `agent/sedimentation_metrics.py`（新增）
- `agent_system/cli_bridge.py`（修复：session identity + 合法枚举 + pending on failure）

## Non-goals

- 不直接修改 official（只读参考）
- 不重启线上 gateway
- 不实现 pending→approved UI
- 不迁移历史聊天全文
- 不实现完整 Knowledge Background Review worker（deferred）

## Baseline Evidence（2026-05-15）

- cli_bridge.py:346 `cli:frank:default` 身份，Feishu session 丢失 → _get_user_default_product_line_id 返回空 → 沉淀静默跳过
- cli_bridge.py:395 `confidence='high'/'medium'` 非法
- cli_bridge.py:396 `knowledge_type='business_fact'` 非法
- cli_bridge.py 未检查 knowledge_write 结果，失败静默（无 pending）
- IdentityResolver / AssetRouter / ScopeResolver / Metrics 均不存在

## Validation（2026-05-15）

- 聚焦测试：48 passed（test_knowledge_candidate + test_identity_resolver + test_scope_resolver + test_asset_router + test_sedimentation_metrics + test_pending_capture_extended + test_cli_bridge_sedimentation）
- 全量回归：201 passed, 1 skipped（无 regression）

## Progress

- [x] Task 1: KnowledgeCandidate + TerminalState + CandidateType（commit d4bf522ae，4 passed）
- [x] Task 2: PendingCapture 扩展 list/mark_terminal/platform（commit 900ab42a4，16 passed）
- [x] Task 3: IdentityResolver（commit 3f384ae5e，6 passed）
- [x] Task 4: ScopeResolver（commit 24bafaea9，11 passed）
- [x] Task 5: AssetRouter + Golden Tests（commit 716a3cc76，9 passed）
- [x] Task 6: SedimentationMetrics（commit 26ad1e2df，5 passed）
- [x] Task 7: cli_bridge 修复（commit e155e8249，18 passed）
- [x] Task 8: 全量回归 + PLANS.md

## Recovery

```bash
cd /Users/frank/.hermes/hermes-agent-integrate
git log --oneline -10
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/agent/test_asset_router.py tests/agent/test_identity_resolver.py -q
```

---

# Agent-System Readiness 第二阶段收口（2026-05-15）

## Codex 恢复记录（2026-05-15）

- 发现 `f55d4e42d feat(readiness): agent-system production readiness phase 2` 被 `1611b519f Revert "feat(readiness): agent-system production readiness phase 2"` 整包回滚；回滚来自 Knowledge Sedimentation 审计的交付边界清洁，不代表 readiness 方案验证失败。
- Codex 接管时，工作区存在一处未提交的 `agent_system/cli_bridge.py` 清理改动，内容为移除 `capability_readiness` 引用。该改动与恢复 readiness phase 2 目标相反，已先保存在 `stash@{0}: codex-preserve-cli-bridge-readiness-cleanup`，没有丢弃。
- 本轮通过 `git revert --no-commit 1611b519f` 恢复被误回滚的 readiness phase 2，并重新执行聚焦验证。
- 后续任务不得为了清洁其他专题交付边界而直接 revert agent-system readiness commit；若认为当前分支含 unrelated committed work，必须报告或新建隔离分支。

## 恢复步骤记录

### 第一步：停止悬挂测试
当前会话无悬挂 run_tests/pytest 进程，跳过 kill 操作。

停止重复 full suite，因为当前任务是 readiness 收口，后台 grep/tail 输出为 0 字节，没有提供诊断价值。

### 第二步：未提交文件清单（production readiness 第二阶段）
- `agent_system/runtime.py` — 修改：enforce_skill_readiness 参数 + capability_readiness 导入
- `agent_system/scheduler/main_scheduler/routes.json` — 修改：routes 结构调整
- `tests/agent_system/test_cli_bridge.py` — 修改：新增 readiness 集成测试
- `tests/agent_system/test_production_readiness.py` — 修改：新增 14 个 readiness 验证测试
- `tests/agent_system/test_runtime.py` — 修改：新增 enforce_skill_readiness 测试
- `agent_system/capability_readiness.py` — 新增：ReadinessResult + 检查逻辑
- `agent_system/readiness_manifest.json` — 新增：manifest 单一事实源
- `scripts/check_agent_system_readiness.py` — 新增：readiness gate 脚本

这些文件属于 production readiness 第二阶段，不属于 integrate 全量测试修复。

### 第三步：唯一目标
完成 agent-system readiness 第二阶段最小闭环。

### gateway progress 红测修复
- 根因：`get_tool_emoji("terminal")` 在 `tools.terminal_tool` 未 import 时返回 fallback `⚙️`
- 修法：在 `agent/display.py` 新增 `_HARDCODED_TOOL_EMOJIS = {"terminal": "💻"}` 作为注册顺序安全的第 3 级 fallback
- 不修改测试期望值，不将期望从 💻 改成 ⚙️

### 最终验证结果
- `python -m py_compile agent_system/capability_readiness.py agent_system/cli_bridge.py agent_system/runtime.py scripts/check_agent_system_readiness.py` → passed
- `python scripts/check_agent_system_readiness.py` → READINESS CHECK PASSED
- `tests/agent_system/test_production_readiness.py tests/gateway/test_run_progress_topics.py::test_run_agent_moves_bare_interim_progress_ui_to_single_progress_module` → 15 passed
- `tests/agent_system/test_production_readiness.py tests/agent_system/test_cli_bridge.py tests/agent_system/test_runtime.py tests/agent_system/test_model_routing.py` → 59 passed
- `tests/agent_system/` 150 passed
- `tests/gateway/test_run_progress_topics.py` 30 passed
- 合计聚焦验证 254 passed，0 failed

## Skill Readiness
- artifact_resolver: ready（executor_type=system, executable=true, production_ready=true）
- 其余 skills: unknown（无 executor 合同声明）
- report_revision: non_ready（stub skill，无 executor）

## Route Readiness
- 全部路由: unknown 或 non_ready
- artifact_status_flow / artifact_delivery_flow / doc_publish_flow: unknown（required_skills 的 artifact_status/delivery/publish 无 executor）
- report_revision_flow: non_ready
- 无路由进入生产候选（Production Candidates = 0，符合预期）

## artifact_resolver 行为
- executor_type=system，不走 delegate_task
- manifest 标 ready 后 check_skill_readiness 不 blocking

## 张嫄养马类消息行为
- 无明确 artifact path 时，report_revision_flow 为 non_ready，不进入 planning LLM
- 返回 None（fallback 对话）或 blocked 状态，不触发 delegate_task 递归
- 不显示"子专家：无 + failed"

---

# Knowledge Sedimentation Phase 5E 闭环修复（2026-05-15）

## Goal

把 Phase 5 的 Governance Plane 从“组件存在”补齐到“主聊天/Feishu 场景可验证地进入 knowledge 或 pending，并可 replay”的最小闭环。

## Scope

- `agent/identity_resolver.py`：Feishu 缺失 user_id 时返回 UNRESOLVED，不 fallback CLI。
- `agent/pending_capture.py`：新增 `read_pending` / `replay_pending`，并接入 terminal_state 与 metrics。
- `agent/asset_router.py` / `tools/knowledge_tool.py` / `agent_system/cli_bridge.py`：接入沉淀漏斗 metrics 和 terminal_state。
- `run_agent.py`：在现有 background review 基础上增加 knowledge review，不破坏 memory/skills review。
- tests：补 identity、pending replay、metrics wiring、knowledge background review、vertical slice。

## Non-goals

- 不修改 official。
- 不重启 official gateway。
- 不改 readiness 机制，不 revert `a74df3801`。
- 不写入真实知识库，不绕过 ACL，不伪造 source_uri，不把整段 raw chat log 直接写入 knowledge。

## Context

- 第五轮审计确认 integrate 工作区干净，旧 Phase 5E 计划中的 Task 1（隔离 readiness 脏改）已经过期。
- 当前仍阻塞：Feishu identity fallback CLI、pending 无 read/replay、run_agent 无 knowledge background review、metrics 无真实调用、无 vertical slice。
- official 仍运行旧代码，PID 3337，本轮只在 integrate 修复。

## Milestones

- [x] M1: 修复 identity UNRESOLVED 不变量。
- [x] M2: 实现 pending read/replay 与 terminal_state。
- [x] M3: metrics 接入真实路径。
- [x] M4: run_agent knowledge background review 最小接入。
- [x] M5: vertical slice 覆盖 Feishu → candidate → pending/replay → metrics。
- [x] M6: 聚焦回归通过，更新本计划。

## Validation

```bash
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh \
  tests/agent/test_identity_resolver.py \
  tests/agent/test_pending_capture_extended.py \
  tests/agent/test_asset_router.py \
  tests/agent/test_sedimentation_metrics.py \
  tests/agent_system/test_cli_bridge_sedimentation.py \
  tests/tools/test_knowledge_tool.py \
  tests/run_agent/test_background_review_toolset_restriction.py \
  tests/integration/test_knowledge_sedimentation_vertical_slice.py \
  -q
```

## Progress

- [x] 2026-05-15：Codex 接手，确认 integrate 工作区干净，Phase 5E 从 Task 2 开始修复。
- [x] 2026-05-15：Feishu `platform=feishu` 且 `user_id=""` 时返回 `IdentitySource.UNRESOLVED`，不再 fallback CLI；旧测试已反转。
- [x] 2026-05-15：`pending_capture` 新增 `read_pending` / `replay_pending`，replay 成功标记 `knowledge_saved`，失败标记 `blocked`。
- [x] 2026-05-15：`knowledge_tool` / `cli_bridge` 写 pending 后标记 `terminal_state=pending_created`。
- [x] 2026-05-15：`sedimentation_metrics` 接入 candidate routing、pending、knowledge_write、replay 路径，并新增 module-level reset。
- [x] 2026-05-15：`run_agent.py` 增加 knowledge background review，保留 memory/skills 限权，并在 knowledge review 时只额外开放 knowledge toolset。
- [x] 2026-05-15：新增 vertical slice：Feishu identity → David/company scope → ACL denied pending → permission repair → replay success → metrics。
- [x] 2026-05-15：聚焦回归通过：64 passed；静态编译通过。

## Validation Results

```bash
python -m py_compile agent/identity_resolver.py agent/pending_capture.py \
  agent/asset_router.py agent/sedimentation_metrics.py tools/knowledge_tool.py \
  agent_system/cli_bridge.py run_agent.py

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh \
  tests/agent/test_identity_resolver.py \
  tests/agent/test_pending_capture_extended.py \
  tests/agent/test_asset_router.py \
  tests/agent/test_sedimentation_metrics.py \
  tests/agent_system/test_cli_bridge_sedimentation.py \
  tests/tools/test_knowledge_tool.py \
  tests/run_agent/test_background_review_toolset_restriction.py \
  tests/run_agent/test_background_review_summary.py \
  tests/integration/test_knowledge_sedimentation_vertical_slice.py \
  -q
# 64 passed
```

## Remaining Release Gate

- official 仍未修改、未重启；上线前需要单独做 RC diff、official merge/deploy 计划和 gateway restart 人工门。
- 本轮只证明 integrate 的 Phase 5E 闭环；未运行全量测试套件。

---

# Knowledge Sedimentation Phase 5F Pending 运营闭环（2026-05-15）

## Goal

把 Phase 5E 的 pending 从“代码里可 replay”补强为“真实运营可发现、可读取、可回放，并且回放使用原始捕获身份”。成功标准是：Feishu pending 在 CLI/后台场景回放时不会误用当前 CLI 身份；agent 可通过 knowledge toolset 查询 pending、读取 pending 详情、触发单条 replay；聚焦测试通过。

## Scope

- `agent/pending_capture.py`：replay 时临时恢复 record 中的 platform/user_id，避免使用当前会话身份。
- `tools/knowledge_tool.py`：新增 `knowledge_pending` 工具，支持 `list` / `read` / `replay`。
- `toolsets.py`：将 `knowledge_pending` 纳入 `knowledge` toolset。
- tests：覆盖跨会话身份 replay、pending 工具 list/read/replay、toolset 可见性。

## Non-goals

- 不修改 official。
- 不重启 gateway。
- 不新增审批 UI 或批量自动 replay。
- 不绕过 ACL；replay 仍走现有 `knowledge_write` 权限链路。

## Context

- Phase 5E 已实现 `read_pending` / `replay_pending`，但 `_knowledge_write` 依赖 `gateway.session_context` 当前身份。
- 真实运营中，pending 常由 Feishu 会话产生，却由 CLI、后台任务或治理 agent 在补权限后回放；如果不恢复捕获身份，会出现 `user_not_registered_or_config_error`、归属错误或审计用户错误。
- `pending_capture.py` 已保存 `platform` 与 `user_id`，可以作为 replay 身份来源。

## Milestones

- [x] M1: replay 恢复原始 platform/user_id，结束后清理上下文。
- [x] M2: `knowledge_pending` 工具支持 list/read/replay。
- [x] M3: toolset 纳入与聚焦测试。
- [x] M4: 更新验证结果。

## Validation

```bash
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh \
  tests/agent/test_pending_capture_extended.py \
  tests/tools/test_knowledge_tool.py \
  tests/agent_system/test_cli_bridge_sedimentation.py \
  tests/integration/test_knowledge_sedimentation_vertical_slice.py \
  -q
```

## Progress

- [x] 2026-05-15：审计确认 Phase 5E 的剩余运营薄弱点是 pending replay 依赖当前会话身份，且 pending 操作未暴露为 agent tool。
- [x] 2026-05-15：`replay_pending` 回放前临时恢复 pending 记录里的 `platform` / `user_id`，回放后恢复当前上下文。
- [x] 2026-05-15：`knowledge_write` 失败生成 pending 时保存完整 `structured_candidate`，避免 replay 丢失 content / knowledge_type / finance / sensitivity / doc_slug。
- [x] 2026-05-15：新增 `knowledge_pending` 工具，支持 ACL 可见范围内的 `list` / `read` / `replay`。
- [x] 2026-05-15：`knowledge` toolset、`hermes-cli`、`hermes-feishu` 均纳入 `knowledge_pending`，保证默认平台可见性。

## Validation Results

```bash
python -m py_compile agent/pending_capture.py tools/knowledge_tool.py toolsets.py

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh \
  tests/agent/test_pending_capture_extended.py \
  tests/tools/test_knowledge_tool.py \
  tests/run_agent/test_background_review_toolset_restriction.py \
  -q
# 30 passed

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh \
  tests/agent/test_identity_resolver.py \
  tests/agent/test_pending_capture_extended.py \
  tests/agent/test_asset_router.py \
  tests/agent/test_sedimentation_metrics.py \
  tests/agent_system/test_cli_bridge_sedimentation.py \
  tests/tools/test_knowledge_tool.py \
  tests/run_agent/test_background_review_toolset_restriction.py \
  tests/run_agent/test_background_review_summary.py \
  tests/integration/test_knowledge_sedimentation_vertical_slice.py \
  tests/hermes_cli/test_tools_config.py \
  -q
# 123 passed

git diff --check
# passed
```

---

# Humanizer-zh Chinese Writing Skill MVP（2026-05-15）

## Goal

把 `op7418/Humanizer-zh` 作为 Hermes 的中文自然写作体验层 MVP 接入，让用户说“润色一下”“这段太 AI 了”“改自然点”“像人话一点”“发老板语气别太冲”等自然表达时，更容易通过 Hermes skill index 发现并加载中文润色规则，而不是要求用户显式说“使用 Humanizer-zh”。

## Scope

- 新增仓库内置 bundled skill：`skills/writing/humanizer-zh/`。
- 保留 `Humanizer-zh` MIT 许可证与来源说明。
- 优化 `SKILL.md` frontmatter，确保 description 前 60 字含中文触发词。
- 默认交互改为结果优先：短文本直接给修改后文本，长文本最多一句改动说明。
- 在 skill 指令中写入事实保真、高风险文本和 Markdown/代码块保护边界。
- 在 skill 正文中加入轻量保真示例，强化日期、项目名、百分比、截止时间不变。
- 添加聚焦测试覆盖 skill 元数据、prompt index、slash command、`skill_view`、bundled sync 和正文约束。

## Non-goals

- 不新增 `WritingIntentRouter`。
- 不重构 skill 系统、prompt cache、CLI/gateway/TUI。
- 不把 Humanizer-zh 做成 `tools/toolsets.py` 显式 tool。
- 不实现长期用户写作画像、memory 自动写入、多平台 UI 或大型质量评分引擎。
- 不处理当前 integrate 中已有的知识沉淀相关脏改。

## Current Architecture Findings

- `agent/prompt_builder.py::build_skills_system_prompt()` 扫描 `get_skills_dir()` 与 external skill dirs，将 skill `name` 与截断后的 `description` 注入系统提示。
- `agent/skill_utils.py::extract_skill_description()` 会把 description 截断到 60 字，因此中文触发词必须放在开头。
- 已有 `skills/creative/humanizer` 来源是 `blader/humanizer`，frontmatter 为英文描述，不足以覆盖“润色/改自然/去 AI 味/像人话”等中文自然触发。
- 仓库 bundled skills 会通过 `tools/skills_sync.py` 同步到用户 `~/.hermes/skills/`，因此 MVP 应放在仓库 `skills/` 树下。

## Humanizer-zh Source Findings

- 源仓库：https://github.com/op7418/Humanizer-zh
- 核心资产：`SKILL.md`，约 484 行，是 Claude Code 风格中文 skill。
- License：MIT，Copyright (c) 2026 歸藏。
- 源 skill 声明翻译自 `blader/humanizer`，工具部分参考 `hardikpandya/stop-slop`。

## Proposed MVP Integration

- 新增 `skills/writing/humanizer-zh/SKILL.md` 与 `LICENSE`。
- 不复制完整上游长 skill；提炼为 Hermes 日常体验版本，保留来源与核心规则。
- 默认不暴露工具名，不展示评分表；只在用户要求解释时展示诊断。
- 对正式/高风险文本默认轻改或中改，明确“不新增事实或承诺”。

## Router Decision

当前 MVP 不新增 router。理由：

- Hermes 已有 mandatory skill index 机制，模型在系统提示中会看到 `humanizer-zh` 的中文触发描述。
- description 前 60 字足以覆盖主要自然触发表达。
- 先用 skill metadata 验证触发收益，避免新增全局路由造成误触发、prompt caching 风险和额外维护面。

后续只有当真实使用证明 skill index 命中不足时，再考虑轻量 `WritingIntentRouter`，且仅输出“建议预加载 skill”，不改写用户消息。

## Risks / Unknowns

- 当前 integrate worktree 已有多项知识沉淀相关脏改，本任务只新增独立 skill 与测试，避免混入既有改动。
- integrate 缺少本地 `venv`，测试需要使用项目已有推荐方式或 `HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv`。
- 真实自动触发依赖模型遵循 skill index；MVP 测试只能验证索引可见性和元数据质量，不能完全证明线上模型一定加载。

## Validation Plan

```bash
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/agent/test_humanizer_zh_skill.py -q
```

必要时补跑：

```bash
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/tools/test_skills_sync.py \
    tests/agent/test_prompt_builder.py tests/agent/test_skill_commands.py -q
```

## Progress

- [x] 2026-05-15：确认 Claude Code 只完成 Phase 0，Humanizer-zh 集成尚未开始。
- [x] 2026-05-15：确认已有 `skills/creative/humanizer` 是英文/通用版，不等同于 Humanizer-zh。
- [x] 2026-05-15：拉取并检查上游 `SKILL.md` 与 MIT `LICENSE`。
- [x] 2026-05-15：新增 Hermes bundled skill `skills/writing/humanizer-zh/`。
- [x] 2026-05-15：添加聚焦测试并验证 skill metadata、prompt index、disabled skills、slash command。
- [x] 2026-05-15：补充 `skill_view("humanizer-zh")` 与 bundled sync 验证，确认 repo `skills/` 可同步到用户 skills 目录并写入 manifest。
- [x] 2026-05-15：补充保真示例，要求保留 `5月15日`、`X100`、`12%`、`6月30日`、`第二轮验证`，并禁止新增完成承诺。
- [x] 2026-05-15：将 `skills/writing/humanizer-zh/` 定向安装到真实用户目录 `/Users/frank/.hermes/skills/writing/humanizer-zh/`，避免全量同步触碰其它本地 skills。

## Validation Results

```bash
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/agent/test_humanizer_zh_skill.py -q
# 6 passed

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/agent/test_prompt_builder.py tests/agent/test_skill_commands.py -q
# 153 passed, 1 skipped

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/tools/test_skills_sync.py \
    tests/agent/test_prompt_builder.py tests/agent/test_skill_commands.py -q
# 198 passed, 1 skipped

git diff --check
# passed
```

真实用户目录检查：

```bash
test -f /Users/frank/.hermes/skills/writing/humanizer-zh/SKILL.md
# passed
```

## Decision Log

- 选择新增 `humanizer-zh` 而不是覆盖 `humanizer`，避免破坏已有英文/通用写作 skill。
- 选择 `skills/writing/humanizer-zh` 路径，因为这是中文写作体验层，不是 creative-only 能力。
- 暂不新增 router，优先使用现有 skill index + 中文触发 description 的低风险路径。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-integrate
git status --short --branch --untracked-files=all
sed -n '1,180p' skills/writing/humanizer-zh/SKILL.md
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/agent/test_humanizer_zh_skill.py -q
```

若验证真实用户目录安装状态：

```bash
test -f /Users/frank/.hermes/skills/writing/humanizer-zh/SKILL.md && \
  sed -n '1,45p' /Users/frank/.hermes/skills/writing/humanizer-zh/SKILL.md
```

---

# Integrate Closure / Remaining Validation（2026-05-15）

## Goal

把 dev / official 整合工作从“内容已聚合但工作区脏”收束到可审计提交态，并继续清理完整测试剩余失败，直到可以安全 merge 回 `codex/dev-env`。

## Current State

- 已确认 `codex/integrate-dev-official` 的历史包含：
  - `codex/dev-wip-snapshot-20260514-232334`
  - `snapshot/hermes-local-20260514-224006`
  - `codex/dev-env`
  - `main`
- 经验/知识系统 Phase 5E 已提交：`f549eb15b feat(knowledge): complete pending replay and sedimentation loop`
- `humanizer-zh` bundled skill 已提交：`05c3046c2 feat(skills): add humanizer-zh bundled writing skill`
- “回复问候”核查结论：未发现新的独立未提交代码差异；相关能力来自已合入的 dynamic planner / Feishu reply 拆分 / 普通问候不进 `agent_system` 验证记录。

## Validation Done

```bash
python -m py_compile agent/identity_resolver.py agent/pending_capture.py \
  agent/asset_router.py agent/sedimentation_metrics.py tools/knowledge_tool.py \
  run_agent.py agent_system/cli_bridge.py
# passed

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/agent/test_identity_resolver.py \
  tests/agent/test_pending_capture_extended.py \
  tests/agent/test_sedimentation_metrics.py \
  tests/agent_system/test_cli_bridge_sedimentation.py \
  tests/tools/test_knowledge_tool.py \
  tests/run_agent/test_background_review_toolset_restriction.py \
  tests/run_agent/test_background_review_summary.py \
  tests/agent/test_humanizer_zh_skill.py
# 63 passed

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/tools/test_skills_sync.py \
  tests/agent/test_prompt_builder.py tests/agent/test_skill_commands.py \
  tests/agent/test_humanizer_zh_skill.py
# 204 passed, 1 skipped

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/integration/test_knowledge_sedimentation_vertical_slice.py
# 1 passed

git diff --check
# passed
```

## Remaining Failure Clusters

完整测试仍未通过，最近结果为 `70 failed, 17610 passed, 54 skipped`。下一阶段按失败簇归因和修复，而不是逐个盲修：

- `delegate/subagent`：stop hook、delegate observability、cost rollup、blocked tools、agent guardrails。
- `auth/credential isolation`：Codex CLI auth fail-closed 测试、真实 keychain / auth store 隔离。
- `gateway async/session`：approve/deny、session split-brain、status、shutdown cancellation。
- `file state/staleness guards`：read dedup、staleness、state registry。
- `platform-local assumptions`：systemd、WSL、clipboard WSL detection、container defaults。
- `TUI protocol/provider`：mock DB / provider resolution 与当前接口契约不一致。

## Next Milestones

- [ ] M1：提交本节 `PLANS.md` 收束记录，保持工作区干净。
- [ ] M2：建立剩余完整测试失败簇归因表。
- [ ] M3：优先修复 `delegate/subagent` 失败簇。
- [ ] M4：修复 `auth/credential isolation` 失败簇，确保不削弱 fail-closed。
- [ ] M5：跑三层验证：失败簇测试、三会话聚焦测试、完整测试。
- [ ] M6：完整测试通过后 merge 回 `/Users/frank/.hermes/hermes-agent-dev` 的 `codex/dev-env`。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-integrate
git status --short --branch
git log --oneline --decorate --max-count=8
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv scripts/run_tests.sh
```

---

# Integrate Optimization Closure（2026-05-15）

## Goal

完成 dev / official 整合后的失败簇优化，把 `codex/integrate-dev-official` 收束到完整测试通过、可合回 `codex/dev-env` 的状态。

## Scope

- 修复/对齐 full-suite 暴露的 delegate、auth、gateway cancellation、file state、systemd/WSL、TUI provider、Matrix E2EE、TokenHub context、logging/cache/stale import 等失败簇。
- 保留 official 的 fail-closed auth、codex_pipeline、conversation access、planner/model routing 等较新行为。
- 保留 dev 的 knowledge pending replay / sedimentation / alias 相关能力。

## Progress

- [x] 修复 delegate/subagent 配置污染和 guardrail 测试导入时机问题。
- [x] 修复 file tools 在 macOS `/private/var` tempdir 下的误拦截。
- [x] 对齐 Codex auth fail-closed、gateway delivery manager、Tirith background install、gateway cancellation、Matrix E2EE mock、TUI provider/session resume、TokenHub 256Ki context、local interrupt cleanup。
- [x] 收敛完整测试中的 full-only 全局状态污染：`oneshot` logging restore、clipboard WSL stale binding、TUI env override、file tool backend cache、agent cache slow init、ACP forced redaction。
- [x] 完整测试通过。

## Validation

重点回归：

```bash
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/agent/test_subagent_stop_hook.py \
  tests/tools/test_delegate.py tests/run_agent/test_agent_guardrails.py
# 157 passed

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/tools/test_file_read_guards.py \
  tests/tools/test_file_staleness.py tests/tools/test_file_state_registry.py
# 61 passed

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/tools/test_tirith_security.py \
  tests/gateway/test_approve_deny_commands.py \
  tests/gateway/test_gateway_shutdown.py \
  tests/gateway/test_session_split_brain_11016.py
# 105 passed

HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv \
  scripts/run_tests.sh tests/hermes_cli/test_gateway_service.py \
  tests/hermes_cli/test_gateway_wsl.py tests/hermes_cli/test_update_autostash.py \
  tests/hermes_cli/test_cmd_update.py tests/hermes_cli/test_provider_config_validation.py \
  tests/test_phase3_semantic_search.py tests/tools/test_clipboard.py
# 293 passed
```

完整回归：

```bash
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv scripts/run_tests.sh
# 17681 passed, 54 skipped, 194 warnings
```

## Decision Log

- `oneshot` logging 静音必须恢复原始 `logging.disable` 状态；否则 full-suite 后续 caplog 会被跨测试污染。
- ACP `fs/read_text_file` 属于安全边界，读取内容即使全局 redaction 未开启也强制脱敏。
- 文件工具 integration 测试必须显式隔离 `TERMINAL_ENV=local` 并清理 terminal/file_ops 缓存，避免 full-suite 中其他 backend 测试残留。
- TUI provider 测试必须清空 `HERMES_MODEL` / `HERMES_INFERENCE_MODEL` / `HERMES_TUI_PROVIDER`，因为这些是合法 runtime override，不应污染该单元断言。

## Recovery

恢复时进入：

```bash
cd /Users/frank/.hermes/hermes-agent-integrate
git status --short --branch
HERMES_TEST_VENV=/Users/frank/.hermes/hermes-agent-official/venv scripts/run_tests.sh
```

---

# Weekly Flow + Quality Gate 完整闭环 — Round 12

## Goal

让两条真实用户路径发生改变：
1. Weekly flow：raw material → confirmed ExecutionContract（fake closure 永远被拒，ledger 持久幂等）
2. Quality gate：final_response 被真实评估，低质量时真实改写（QUALITY_LOOP_GATED=true）

## Scope

新建：agent_system/weekly/（7 模块）、agent_system/quality/（4 模块）、14 个测试文件
修改：run_agent.py（15 行）、PLANS.md

## Status: COMPLETED ✅ (2026-05-18)

### 新增文件
- `agent_system/weekly/__init__.py` + `models.py` + `issue_extractor.py` + `decision_gate.py` + `confirmation.py` + `ledger.py` + `bridge.py`
- `agent_system/quality/__init__.py` + `models.py` + `evaluator.py` + `gate.py`
- `tests/agent_system/test_weekly_flow_runtime_e2e.py` (W1–W7, 7 passed)
- `tests/run_agent/test_quality_gate_final_response.py` (Q1–Q7, 7 passed)

### 关键行为验证
- fake_closure_detected → gate returns None → no ExecutionContract ✅
- missing fields → DecisionCard(status=incomplete) + follow_up list ✅
- confirmed event → ExecutionContract written to HERMES_HOME/weekly/ledger.json ✅
- repeated callback → idempotent, single ledger entry ✅
- ledger recoverable: new WeeklyLedger() reads existing contracts ✅
- QUALITY_LOOP_GATED=false → run_agent.py output unchanged ✅
- QUALITY_LOOP_GATED=true, already_streamed=True → log only, no replace ✅
- evaluator exception → original returned, warning logged ✅
- rewrite = clean answer, NOT suggestions+original ✅

### 测试结果
- Weekly E2E: 7/7 passed
- Quality Gate: 7/7 passed
- tests/run_agent/ 全量回归: 1155 passed, 7 skipped, 0 failed
- 安全扫描: secrets=0, hardcoded ~/.hermes=0
- gateway diff: 0 行

### production_ready 状态
- Weekly flow 节点：仍为 non_ready（无 gstack CLI，ledger 逻辑已就绪但业务层需更多验证）
- Quality gate：新增，默认关闭（QUALITY_LOOP_GATED=false），ready 标准：heuristic evaluator 已通过，LLM-backed rewrite 待接入

### 阻塞原因记录（不设为 true 的理由）
- weekly：production 场景需要真实 Feishu webhook 验证（本地 E2E mock only）
- quality：heuristic evaluator 的 pass/rewrite 边界需要在真实流量中标定；LLM rewrite 未接入

### 提交
- `8e66b02e1` — feat(weekly+quality): close weekly flow and quality gate loops

### 恢复
```bash
rm -rf agent_system/weekly/ agent_system/quality/
git checkout run_agent.py
scripts/run_tests.sh  # must show 0 new failures
```

---

## Round 13 — Sedimentation Governance Backbone + gstack 专家层接入

> Date: 2026-05-19 | Status: contract_layer_complete; runtime wiring pending (Round 14)

### 目标

构建完整沉淀治理主干：统一入口（MemoryEvent）、5目的地分流（MemoryDispatcher）、
暂存区状态机（StagingStore）、回读标注（UsageHint）、结构化行动卡（ExperienceCard）、
三层经验 ACL（experience_layer）、gstack 专家层接入（gstack_bridge）。

### 产出文件

**新建（14个）：**
- `agent/memory_event.py` — MemoryEvent 统一入口
- `agent/memory_relations.py` — 10种强关系
- `agent/staging_store.py` — StagingEntry + next_action 状态机（5状态）
- `agent/usage_hint.py` — 6类 UsageHint，wrap_with_hint()
- `agent/experience_card.py` — ExperienceCard + DAVID_CARD
- `agent/project_process_store.py` — 项目流程存储
- `agent/memory_dispatcher.py` — 10规则5目的地分流器
- `agent/session_capture.py` — 会话风险探测
- `agent_system/sedimentation/__init__.py`
- `agent_system/sedimentation/feature_flags.py` — 全部默认 OFF
- `agent_system/sedimentation/experience_layer.py` — 三层 ACL
- `agent_system/sedimentation/gstack_bridge.py` — gstack → 沉淀链
- `docs/architecture/sedimentation-governance.md` — 架构决策记录
- `tests/agent/test_sedimentation_governance.py` — S1–S12 治理契约测试
- `RESTORE.md` — 回滚指令

### 测试结果

- S1–S12（治理契约）：12/12 passed ✅
- shadow mode 验证：GSTACK_SEDIMENTATION_ENABLED=false OK ✅
- secret scan：0 ✅
- path safety：0 ✅
- 全量回归：1155+ passed（待全量测试完成确认）

### 关键治理契约（均有测试覆盖）

- David 私聊 → staging（不进 knowledge）
- PBI → project_process（有 project_hint）
- 私聊→项目 → 需用户确认
- 用户纠正（有 scope）→ personal_memory + user_correction 关系
- tool_failure → staging(retry_write)，不丢失
- permission_unclear → staging，不丢失
- 所有回读携带 usage_hint
- expert_mem 仅 expert 自身可写
- skill_mem 仅 skill 自身可写
- gstack review → audit_evidence only
- gstack playbook → skill_asset（feature flag 守卫）
- gstack lesson → expert_mem_candidate（不直接写）

### production_ready 状态

- MemoryEvent/Dispatcher/Staging/UsageHint/ExperienceCard：new，non_ready（heuristic 层已通，需真实流量标定）
- gstack_bridge：new，non_ready（feature flag OFF，shadow mode）
- experience_layer ACL：new，有测试覆盖，non_ready（待 expert workflow 接入验证）

### 阻塞原因

- gstack sedimentation：GSTACK_SEDIMENTATION_ENABLED 默认 false，需生产验证
- usage_hint 注入：USAGE_HINT_INJECTION_ENABLED 默认 false，需知识库 E2E 验证
- 三层经验：经验写入工作流尚未接入真实 expert 执行路径

### 恢复

参见 RESTORE.md（Round 13 专用回滚指令）


---

## Round 14 — Sedimentation Runtime Wiring

> Date: 2026-05-19 | Status: ✅ COMPLETE

### 目标

把 Round 13 合同测试层升级为真实 runtime 闭环。所有特性开关保持默认 OFF（shadow mode）。

### 产出：修改文件（8个）

- `run_agent.py` — capture_turn() in on_turn_start, SESSION_CAPTURE_AUTO_ENABLED gate
- `agent/session_capture.py` — dispatch_event() after write_event()
- `tools/knowledge_tool.py` — dispatch_tool_failure() on all write failure paths; usage_hint on query
- `agent_system/cli_bridge.py` — dispatch_event() on permission_denied in _auto_sedate_knowledge()
- `agent/memory_manager.py` — wrap_with_hint() in build_memory_context_block() under flag
- `agent_system/runtime.py` — write_to_layer() ACL check before each _append_memory_line()
- `agent_system/sedimentation/feature_flags.py` — set_flag() runtime override + _env_bool() helper
- `agent_system/sedimentation/gstack_bridge.py` — map_phase_to_output_type() + route_gstack_result()

### 产出：扩展文件（2个）

- `agent/staging_store.py` — approve/reject/archive/update_next_action/stats + audit log + atomic writes
- `agent/pending_capture.py` — stats() + migrate_to_staging() idempotent

### 产出：新建测试（6个文件，52个测试）

- `tests/agent/test_session_capture_runtime.py`
- `tests/agent/test_knowledge_tool_sedimentation.py`
- `tests/agent/test_staging_ops.py` (18 tests)
- `tests/agent/test_usage_hint_readback.py`
- `tests/agent_system/test_experience_layer_runtime.py`
- `tests/agent_system/test_gstack_bridge_control.py`

### 文档更新（3个）

- `agent_system/readiness_manifest.json` — v1.1, sedimentation_components 区段，组件 → wired 状态
- `agent_system/ARCHITECTURE.md` — 沉淀治理层架构章节
- `RESTORE.md` — Round 14 回滚指令

### 测试结果

- S1–S12（治理契约）：12/12 ✅
- 新增 runtime 测试：52/52 ✅
- Gate 7 指定测试套件（8个文件）：64/64 ✅
- full suite：17864 passed, 0 failed ✅
- secret scan：0 ✅
- path safety（新文件）：0 ✅
- feature flags 默认 OFF：✅

### Smoke（Gate 6）

- `~/.hermes/knowledge/pending_captures.jsonl`：13行（全 pending_created，旧路径遗留）
- 新沉淀文件（events.jsonl/staging.jsonl）：不存在（预期，SESSION_CAPTURE_AUTO_ENABLED=OFF）
- 首次运行时触发：设置 SESSION_CAPTURE_AUTO_ENABLED=true 即可产生真实产物

### Commit

- Round 13: a39cd44cf（合同层骨架）
- Round 14 main: 6db73843d（runtime wiring, 20 files changed）
- Round 14 docs: fc5e27fec（RESTORE.md + readiness_manifest）
- Round 14 post: c7afd7872（PLANS.md 记录）
- Round 14 post: 371e5cbf5（knowledge_staging_ops tool entry point）
- Round 14 post: 9e89318ca（knowledge_staging_ops 14 tests）
- Round 14 post: d31354694（experience_card trigger_check injection wired）

### runtime wired 路径清单

| 触发点 | 路径 | 目的地 |
|--------|------|--------|
| user correction in session | run_agent.py → capture_turn() → dispatch_event() | personal_memory or staging |
| knowledge_write permission_denied | knowledge_tool.py → dispatch_tool_failure() | staging(retry_write) |
| knowledge_write write_failed | knowledge_tool.py → dispatch_tool_failure() | staging(retry_write) |
| auto_sedate permission_denied | cli_bridge.py → dispatch_event() | staging |
| memory context readback | memory_manager.py → wrap_with_hint() | prompt with hint |
| knowledge_query results | knowledge_tool.py → hint_for_knowledge() | doc._usage_hint |
| expert_mem write | runtime.py → write_to_layer() ACL check | expert_mem (or staging if denied) |
| skill_mem write | runtime.py → write_to_layer() ACL check | skill_mem (or staging if denied) |
| system_mem write | runtime.py → write_to_layer() ACL check | system_mem (hermes_main only) |
| gstack phase result | gstack_bridge.route_gstack_result() | by output_type (flag ON only) |
| user message trigger | run_agent.py → trigger_check() → render_card() | ephemeral prompt injection |

### staging ops（Gate 3 CLI 补完）

- `knowledge_staging_ops` tool：list/stats/approve/reject/archive/migrate_pending
- 14 个测试覆盖所有 action 路径和边界条件

### 仍 non_ready 的能力及原因

- gstack phases（all）：real_gstack=false，gstack CLI 未安装
- pending→staging 迁移：migrate_to_staging() 已实现，可通过 knowledge_staging_ops(migrate_pending) 手动触发
- production_ready：任何组件均需真实流量 smoke 验证才能升级

### Hermes 升级准入判断

不建议基于本轮升级 Hermes gateway/runtime。本轮 evidence 级别为 wired（有 runtime 接线，无真实产物）。
下一步：在 staging 环境打开 SESSION_CAPTURE_AUTO_ENABLED，积累 events.jsonl 产物，验证无回归后方可 production 升级。
