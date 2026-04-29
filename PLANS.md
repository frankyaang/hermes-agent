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
