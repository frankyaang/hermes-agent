# Builder Expert Recon

目标目录：`/Users/frank/.hermes/hermes-agent-official`

## 实际仓库结构

本仓库存在深度养马 builder expert，真实路径与预期一致：

- `agent_system/experts/builder_expert/builder.py`
  - `INTAKE_QUESTIONS`：33-40，定义 INTAKE 的 5 个必填字段。
  - `PROGRESS_LABELS`：51-60，显示 in-mode 阶段进度；`ENTRY` 不在这里显示。
  - `BUILDER_INTENTS`：62-71，固定 8 类用户意图标签。
  - `IntentResult`：175-208，字符串兼容的意图结果，附带 `label`、`target`、`target_type`。
  - `recognize_intent(...)`：218-269，纯规则 / 关键词意图识别，无 LLM/API 调用。
  - `load_state(...)` / `save_state(...)`：274-285，状态文件读写。
  - `_current_field_key(...)`：296-311，定位当前 INTAKE 字段或阶段字段。
  - `_set_field_value(...)`：330-358，写入 INTAKE 字段或 `state["prefill"]`，用户覆盖会标记 `source=user_override`。
  - `_find_field_in_message(...)`：408-420，按字段别名定位目标字段。
  - `_find_stage_in_message(...)`：422-427，按阶段别名定位目标阶段。
  - `_set_pending_revision(...)`：454-466，为回退 / 修改设置待覆盖字段并调整 INTAKE 指针。
  - `_answer_pending_revision(...)`：484-503，下一轮回答覆盖目标字段，然后回到后续缺失字段。
  - `_handle_definition_intent(...)`：505-514，只解释当前/目标字段，不推进。
  - `_handle_advice_intent(...)`：516-525，只给建议与理由，不推进。
  - `_handle_confirm_understanding_intent(...)`：527-540，只复述当前理解，不推进。
  - `_handle_show_current_intent(...)`：542-563，只展示当前 state 摘要，不推进。
  - `_handle_revise_previous_intent(...)`：566-587，定位字段、展示原内容、支持内联改写或进入待覆盖态。
  - `_handle_go_back_intent(...)`：589-617，定位阶段或字段，支持返回指定阶段或字段。
  - `_handle_continue_intent(...)`：619-645，处理“继续/默认/跳过”。
  - `_collect_conversation_messages(...)`：660-693，从 `parent_agent` 与 session DB 收集近端历史。
  - `_extract_labeled_value(...)`：696-720，规则抽取“字段：值”内容。
  - `build_context_prefill(...)`：723-756，生成养马卡预填结构。
  - `_apply_prefill_to_state(...)`：758-776，把预填映射进 INTAKE，并把指针移到第一个缺失字段。
  - `_render_entry_with_context(...)`：778-826，渲染有上下文的首轮回复。
  - `render_initial_reply(...)`：828-839，进入模式时决定上下文预填或空 INTAKE 文案。
  - `_next_intake_question(...)`：844-849，查找第一个未回答必填字段。
  - `handle_intake(...)`：947-1010，INTAKE 主流程。
  - `_handle_optional_answer(...)`：1012-1034，选填表单处理，完成后进入 `ARCHITECT`。
  - `scan_reusable_experts(...)`：1123-1130，ARCHITECT 复用扫描。
  - `handle_architect(...)`：1133-1260，复用/扩展/新建方案协商，确认后进入 `DRAFT`。
  - `handle_draft(...)`：1261-1305，调用 draft writer 写会话隔离草稿，然后进入 `VALIDATE`。
  - `handle_validate(...)`：1307-1408，校验、重名自动重试与表单兜底。
  - `handle_dry_run(...)`：1410-1493，结构试加载、mock 和输出形态检查。
  - `handle_trial_run(...)`：1495-1616，真实数据来源选择、试运行确认。
  - `handle_commit(...)`：1618-1758，从会话 draft root 落盘并 `git add`。
  - `handle_next_or_exit(...)`：1760-1789，继续创建下一匹马或提示退出。
  - `_HANDLERS`：1794-1803，阶段到 handler 的分发表。
  - `handle(...)`：1806-1857，每轮用户输入的统一入口，先识别意图再分支处理。
- `agent_system/builder_dispatcher.py`
  - `_session_state_identity(...)`：96-140，生成会话隔离 identity。
  - `_state_file_path(...)`：143-150，生成 `agent_system/temp/skill_creation_<state_identity>.json`。
  - `_state_file_path_for_agent(...)`：152-154，按 `parent_agent` 定位 state 文件。
  - `_enter_mode(...)`：185-233，进入深度养马模式，创建初始 state 并调用 `render_initial_reply`。
  - `_exit_mode(...)`：236-248，退出模式，只删除 state 文件。
  - `_dispatch_to_state_machine(...)`：251-271，活跃模式消息转发给 `builder.handle`。
  - `maybe_handle_builder_mode(...)`：288-337，深度养马模式入口/退出/活跃消息分发。
- `agent_system/experts/builder_expert/draft_writer.py`
  - `_session_draft_root(...)`：29-31，会话级 draft 根目录。
  - `_build_skill_files(...)`：44-97，生成 skill draft。
  - `_build_expert_files(...)`：100-134，生成 expert draft。
  - `_build_routes_patch(...)`：137-181，生成会话级 `routes.draft.json`。
  - `write_drafts(...)`：184-240，写入 `agent_system/temp/builder_sessions/<state_identity>/`。
- `agent_system/experts/builder_expert/EXPERT.md`
  - 9 阶段 SOP：22-35。
  - INTAKE 字段定义：48-70。
  - DRAFT 隔离目录：134-152。
  - COMMIT 规则：188-194。
- `agent_system/experts/builder_expert/expert.json`
  - 模式触发短语与专家 manifest，供 dispatcher 读取。

## 深度养马入口与状态隔离

入口位于 `agent_system/builder_dispatcher.py::maybe_handle_builder_mode(...)`（288-337）。它在常规 agent-system routes 分发前运行，先处理退出短语，再处理入口短语，最后在 state 文件存在时把消息交给 `builder.handle(...)`。

state 文件：

- 目录：`agent_system/temp/`
- 命名：`skill_creation_<state_identity>.json`
- `state_identity` 优先级：`gateway_session_key` → `platform + chat_id + thread_id + user_id` → `session_id` → `platform` → `default`
- 文件名组件由 `_safe_state_component(...)` 清洗，过长或不安全字符会附加 SHA-256 前 12 位摘要。

退出模式只删除当前 session 的 state 文件，不删除 draft、audit 或 output。draft 隔离在 `agent_system/temp/builder_sessions/<state_identity>/`，COMMIT 阶段从 `state["drafts"]["session_draft_root"]` 读取当前会话草稿。

## 9 阶段主流程

`agent_system/experts/builder_expert/EXPERT.md`（22-35）定义的 9 阶段是：

1. `ENTRY`：runtime / dispatcher 检测入口短语并创建状态文件。
2. `INTAKE`：收集必填字段。
3. `ARCHITECT`：复用扫描、方案协商、构建架构方案。
4. `DRAFT`：生成 draft 文件。
5. `VALIDATE`：JSON schema、重名、依赖完整性校验。
6. `DRY_RUN`：结构试加载、mock 数据与输出形态检查。
7. `TRIAL_RUN`：用户提供真实数据并确认输出。
8. `COMMIT`：draft 落正式位置、patch routes、`git add`。
9. `NEXT_OR_EXIT`：继续创建下一匹马或退出模式。

实现上，`ENTRY` 在 `agent_system/builder_dispatcher.py::_enter_mode(...)`（185-233）。其余 in-mode 阶段由 `builder.py::_HANDLERS`（1794-1803）分发，并由 `builder.py::handle(...)`（1806-1857）统一读取 state、处理当前轮、保存 state。

阶段推进写入点：

- `handle_intake(...)`（947-1010）逐题写入 `state["intake"][field]`，Q2 会写 `_scenario_kind`；5 个必填完成后进入 `OPTIONAL`。
- `_handle_optional_answer(...)`（1012-1034）写默认选填值或 `optional_raw`，然后 `state["stage"]="ARCHITECT"` 并 `_push_history(state, "INTAKE")`。
- `handle_architect(...)`（1133-1260）首次扫描候选并写 `state["architect_proposal"]`；用户确认复用/扩展/新建后写 experts/skills/routes，推进到 `DRAFT` 并记录 history。
- `handle_draft(...)`（1261-1305）调用 `write_drafts(state)`，把返回摘要写入 `state["drafts"]`，推进到 `VALIDATE`。
- `handle_validate(...)`（1307-1408）把校验报告写到 `state["validation"]`；通过后推进到 `DRY_RUN`，失败则进入 `awaiting_user`。
- `handle_dry_run(...)`（1410-1493）写 `state["dry_run"]`，通过结构检查后推进到 `TRIAL_RUN`。
- `handle_trial_run(...)`（1495-1616）写 `state["trial_run"]`，用户确认后推进到 `COMMIT`，否决时回到 `ARCHITECT`。
- `handle_commit(...)`（1618-1758）从会话 draft root 移动文件到正式目录、patch routes、执行 `git add`，推进到 `NEXT_OR_EXIT`。
- `handle_next_or_exit(...)`（1760-1789）若继续则重置本轮 `intake/architect_proposal/drafts/validation/dry_run/trial_run` 并回到 `INTAKE`。

## INTAKE 当前流程

`INTAKE_QUESTIONS`（builder.py 33-40）定义 5 个必填字段：

- `business_goal`：业务目标。
- `scenario`：典型使用场景 / 触发方式。
- `input_type`：输入材料 / 输入类型。
- `output_type`：输出产物。
- `pipeline_description`：执行流程。

初始 `_current_question` 是 `INTENT_CHOICE`。`handle_intake(...)`（947-1010）先让用户选 1-6 的能力类型，写入 `intake["_user_intent"]` 后进入 `Q1`。之后每轮把答案写入当前问题对应字段，并调用 `_next_intake_question(...)`（844-849）找下一个缺失字段。Q5 有轻量步骤校验；如果不像流程，会用 `_q5_reasked` 追问一次，再接受下一轮输入。必填完成后 `_current_question="OPTIONAL"`，由 `_handle_optional_answer(...)`（1012-1034）处理选填并推进到 `ARCHITECT`。

上下文预填会改变初始 INTAKE 指针：`_apply_prefill_to_state(...)`（758-776）把能映射的预填字段写入 `intake`，再把 `_current_question` 指到第一个仍缺失的字段；没有上下文时保持空 INTAKE，仍从 `INTENT_CHOICE` 开始。

## 意图层与每轮分支

`recognize_intent(...)`（builder.py 218-269）只使用确定性字符串/关键词规则，返回字符串兼容的 `IntentResult`。合法标签固定为 `BUILDER_INTENTS`（62-71）：

- `answer_current_question`
- `ask_definition`
- `ask_advice`
- `confirm_understanding`
- `revise_previous`
- `go_back`
- `show_current`
- `continue`

`revise_previous` 和 `go_back` 会附带目标：

- 字段目标：`target=<field_key>`，`target_type="field"`。
- 阶段目标：`target=<stage>`，`target_type="stage"`。
- “上一步”类表达会使用调用方传入的 `previous_field`。

`builder.handle(...)`（1806-1857）先调用 `recognize_intent(...)`，然后分流：

- `ask_definition` / `ask_advice` / `confirm_understanding` / `show_current`：使用 `copy.deepcopy(state)` 的只读快照，不调用 `save_state`，不推进阶段。
- `revise_previous`：调用 `_handle_revise_previous_intent(...)`（566-587），支持内联改写或设置 `_pending_revision`。
- `go_back`：调用 `_handle_go_back_intent(...)`（589-617），可回到指定阶段或字段；回字段时设置 `_pending_revision` 并调整 INTAKE 指针。
- `answer_current_question`：若存在 `_pending_revision`，先由 `_answer_pending_revision(...)`（484-503）覆盖目标字段；否则进入原阶段 handler。
- `continue`：先由 `_handle_continue_intent(...)`（619-645）处理跳到下一缺失字段、默认选填等；否则进入原阶段 handler。

普通 `answer_current_question` / `continue` 路径仍走 `_HANDLERS`，主 9 阶段流程没有被替换。

## conversation_history / recent session messages

builder 通过 `build_context_prefill(parent_agent)`（builder.py 723-756）进入上下文预填，具体历史读取在 `_collect_conversation_messages(parent_agent, limit=20)`（660-693）：

- `parent_agent.conversation_history`
- `parent_agent.messages`
- `parent_agent._conversation_history`
- `parent_agent._messages`
- 如果有 `parent_agent._session_db` 与 `session_id` / `_session_id`，调用 `get_messages_as_conversation(session_id, include_ancestors=True)`；若签名不支持则退回 `get_messages_as_conversation(session_id)`。

相关上游入口：

- `run_agent.py::run_conversation(...)`：10042-10260，在进入 LLM 主循环前调用 `agent_system.cli_bridge.maybe_run_agent_system_from_message(...)`，并把 `self` 作为 `parent_agent`。
- `agent_system/cli_bridge.py::maybe_run_agent_system_from_message(...)`：58-140，优先调用 `maybe_handle_builder_mode(...)`。
- `cli.py`：2122 初始化 `HermesCLI.conversation_history`；8520-8642 每轮把用户消息加入 history，并把 `self.conversation_history[:-1]` 传给 `AIAgent.run_conversation(...)`。
- `hermes_state.py::get_messages_as_conversation(...)`：1339-1370，从 SQLite session store 还原 OpenAI 格式消息，支持 `include_ancestors`。

## 上下文预填字段

`build_context_prefill(...)`（builder.py 723-756）从历史文本中规则抽取以下 8 个养马卡字段：

- `capability_candidate_name`：能力候选名。
- `business_goal`：业务目标，映射到 INTAKE `business_goal`。
- `typical_use_scenario`：典型使用场景，映射到 INTAKE `scenario`。
- `input_materials`：输入材料，映射到 INTAKE `input_type`。
- `output_artifacts`：输出产物，映射到 INTAKE `output_type`。
- `execution_flow`：执行流程，映射到 INTAKE `pipeline_description`。
- `judgment_criteria`：判断标准，保留在 `state["prefill"]`。
- `open_questions`：待澄清问题，保留在 `state["prefill"]`。

每个预填项使用结构：

```json
{
  "business_goal": {
    "value": "...",
    "source": "conversation_history",
    "confidence": "high"
  }
}
```

用户通过 `revise_previous` 覆盖预填字段时，`_set_field_value(...)`（330-358）会同步更新 `state["intake"]` 或 `state["prefill"]`，并把该字段改为 `source="user_override"`、`confidence="high"`。

## tests/agent_system

当前 `tests/agent_system/` 下的测试文件：

- `tests/agent_system/test_builder_dispatcher.py`
- `tests/agent_system/test_builder_intents.py`
- `tests/agent_system/test_cli_bridge.py`
- `tests/agent_system/test_draft_isolation.py`
- `tests/agent_system/test_model_routing.py`
- `tests/agent_system/test_output_selector.py`
- `tests/agent_system/test_runtime.py`

与本任务直接相关：

- `tests/agent_system/test_builder_intents.py`
  - `test_recognize_intent_returns_documented_labels`：53-82。
  - `test_intake_definition_question_does_not_advance_or_write`：84-93。
  - `test_intake_advice_question_does_not_advance_or_write`：95-105。
  - `test_go_back_previous_step_allows_overwrite_without_corrupting_fields`：107-135。
  - `test_show_current_returns_summary_without_advance`：137-155。
  - `test_deep_builder_entry_prefills_from_conversation_and_asks_missing_only`：157-207。
  - `test_prefilled_field_can_be_overwritten_when_user_negates_it`：209-241。
  - 其余边界测试覆盖无上下文入口、内联修订、指定字段回退、session DB 历史读取、空上下文回退和继续跳到下一缺失字段。
- `tests/agent_system/test_builder_dispatcher.py`
  - 24-257 覆盖会话级 state 隔离、活跃模式转发、退出短语保护与 state 文件命名。
- `tests/agent_system/test_draft_isolation.py`
  - 66-153 覆盖 draft root、routes draft、退出和 commit 的会话隔离。

运行必须使用：

```bash
scripts/run_tests.sh tests/agent_system/
```

`scripts/run_tests.sh` 会启用 hermetic 测试环境、清理 credential 环境变量、固定 `TZ=UTC` / `LANG=C.UTF-8` / `PYTHONHASHSEED=0`，并默认用 4 个 xdist worker。

## Final Verification

命令：

```bash
scripts/run_tests.sh tests/agent_system/
```

测试摘要行：

```text
============================== 81 passed in 1.65s ==============================
```

结果：0 failures。
