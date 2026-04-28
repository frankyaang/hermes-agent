# 用户分析专家

## 1. 模板目标

本模板用于 Hermes Agent System 的专家层运行闭环示例，描述主专家、辅专家、Skill、DAG 调度、人工介入、审计、复盘、权重优化和私域经验积累之间的固定协作关系。

模板覆盖：

- 主专家负责任务判断、节点分配、复盘优先评估、默认 Skill 多重加载和动态覆盖规则
- 辅专家负责执行分配节点任务，独立调用 Skill，返回输出、异常、审计点和待补项
- 主/辅专家在执行阶段可平行调用 Skill，但必须遵守 DAG 依赖和调度顺序
- 每个专家独立调用 Skill，沉淀私域经验和 pipeline 执行数据
- 碳基（人）介入关键节点复核、异常确认和用户确认
- 默认 Skill 多重加载、动态覆盖、异常映射、审计记录、复盘与权重优化
- 审计、权重更新和私域经验沉淀均纳入固定闭环

当前任务承接边界：运行器支持可配置子智能体层级，`max_spawn_depth` 默认值为 1，可按任务和配置提升到多层；专家模板必须明确当前实例采用的层级上限，并由调度层保持 DAG 依赖约束。

### 1.1 目标分层与一致性要求

| 层级 | 作用 | 固定要求 |
| --- | --- | --- |
| 模板占位 | 定义字段、权重公式、异常映射、人工介入字段、复盘触发、输入 / 输出约束 | 占位内容必须可被专家文档生成器刷新，不能伪装成已执行结果 |
| 运行闭环落地 | 执行 DAG、主/辅专家平行调用 Skill、写审计日志、生成复盘摘要、回写权重、沉淀私域经验 | 运行产物必须包含 `audit.jsonl`、`review_summary.json`、`skill_weights.json` 和专家 / Skill 记忆摘要 |
| 一致性验证 | 检查模板字段与运行器产物是否一致 | 每次模板或运行器变更后，必须同时做静态验证和运行验证 |

经验准则：模板负责说明“应该有哪些字段和规则”，运行器负责证明“这些字段和规则已经进入闭环执行”。两者不能互相替代，也不能把 Skill 内部步骤写入专家层模板。

### 1.2 必落地运行能力

| 能力 | 运行要求 | 产物 / 验证点 |
| --- | --- | --- |
| CLI 主循环接入 | 用户在默认聊天中明确触发 `agent_system` 且命中 routes pipeline 时，自动进入运行器，不需要手动调用脚本 | 返回运行摘要，写入 `audit.jsonl`、`review_summary.json`、`skill_weights.json` |
| 人工审批 UI | `user_gate=true` 或阻塞异常需要人工判断时，必须通过 agent_system 独立审批适配层收集审批动作和 `human_input_summary` | 审计记录中 `human_review_required=是`、`human_review_decision`、`human_input_summary` 均可追溯 |
| 多层子智能体 | `max_spawn_depth` 可配置；大于 1 时任务包可使用 orchestrator 角色继续委托 | 任务包记录 `max_spawn_depth` 和 delegate role，DAG 依赖仍按 routes 执行 |
| 真实 Skill 执行绑定 | 默认 Skill 调用必须绑定真实 Agent / LLM / `delegate_task` 执行，生产环境不得静默回退成本地占位 | Skill 调用记录包含真实执行摘要、状态、异常、线上凭据状态、API 调用观测和审计点 |
| 自动 Skill 权重回写 | 复盘后根据成功率、输出质量、异常次数和动态覆盖次数自动更新权重 | `skill_weights.json` 按公式回写并保留计算依据 |

## 2. 主/辅专家职责

### 2.1 主专家职责

| 项目 | 内容 |
| --- | --- |
| 专家 ID | user_analyst |
| 专家名称 | 用户分析专家 |
| 业务范围 | 负责用户洞察、VOC分析、竞品反馈和质量风险判断 |
| 角色定位 | 主专家 / 主智能体 |
| 主要职责 | 任务判断、节点分配、复盘优先评估、默认 Skill 多重加载、动态覆盖规则、异常复核、输出汇总 |
| Skill 执行 | 可独立调用默认 Skill 或动态覆盖 Skill；生产环境需通过真实 Agent / LLM / `delegate_task` 执行 |
| 协作方式 | 可与辅专家平行执行 Skill，但必须遵守 DAG 依赖和调度顺序 |
| 私域经验 | 启用，记录在 `expert_mem/` |
| 不负责内容 | 不替代调度层执行全局 DAG，不展开 Skill 内部执行细节，不替代人工审批 |

### 2.2 辅专家职责

| 项目 | 内容 |
| --- | --- |
| 角色定位 | 辅专家 / 子智能体执行单元 |
| 执行范围 | 仅执行被分配的节点任务 |
| Skill 执行 | 独立调用 Skill 完成节点任务；生产环境需触发真实 Agent / LLM / `delegate_task` |
| 返回内容 | 节点输出、异常、审计点、待补项、人工介入建议 |
| 经验沉淀 | 独立积累私域经验和 pipeline 执行数据 |
| 协作约束 | 可与主专家平行执行 Skill，但必须服从 DAG 依赖和调度顺序 |
| 不负责内容 | 不管理全局 DAG、不管理调度暂停、不做跨节点并行控制、不制定复盘优先级 |
| 层级边界 | 按运行配置承接任务，默认 `max_spawn_depth=1`；多层时仍只执行被分配节点，不接管全局 DAG |

### 2.3 碳基（人）介入职责

| 项目 | 内容 |
| --- | --- |
| 介入对象 | 关键节点、用户确认节点、高风险异常、复盘建议 |
| 输入内容 | 人工结论、补充资料、风险判断、最终确认 |
| 反馈去向 | 主专家复盘、辅专家节点修正、Skill 权重优化、审计记录 |
| 占位字段 | `human_review_required`、`human_review_decision`、`human_review_blocking`、`human_input_summary` |

### 2.4 调度层职责

| 项目 | 内容 |
| --- | --- |
| DAG 管理 | 控制 routes 中的节点顺序、依赖关系、并行 / 串行执行 |
| 状态管理 | 处理 optional 节点、阻塞异常、暂停、恢复、用户确认 |
| 审计汇总 | 汇总每个节点、主专家、辅专家、人工介入和 Skill 的运行记录 |
| 复盘数据 | 汇总异常、动态覆盖、输出质量、人工输入和权重调整建议 |
| 不负责内容 | 不替代主专家做业务判断，不展开 Skill 内部执行细节 |

## 3. 默认 Skill 多重加载

| Skill ID | Skill 名称 | Base Weight | 默认用途 | 加载策略 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| `voc_insight` | 用户洞察 | 90 | 输入盘点 / 分析 | 高权重默认加载 | active |
| `superpowers` | 思考辅助 | 80 | 复杂判断 / 辅助复核 | 条件满足时加载 | active |
| `briefing` | 过程汇报 | 70 | 过程汇报 / 仿人汇报 | 仿人汇报触发加载 | active |

### 3.1 权重公式

```text
Skill_Weight =
    Base_Weight
    + Success_Rate * 0.4
    + Output_Quality * 0.3
    - Exception_Count * 0.2
    + Dynamic_Coverage_Frequency * -0.1
```

| 字段 | 含义 | 单位 | 示例 |
| --- | --- | --- | --- |
| `Base_Weight` | Skill 初始权重 | 0-100 分 | 90 |
| `Success_Rate` | 历史任务成功率 | %，0-100 | 92 |
| `Output_Quality` | 输出质量评分 | 0-100 分 | 85 |
| `Exception_Count` | 历史异常次数 | 次 | 3 |
| `Dynamic_Coverage_Frequency` | 被动态覆盖替代或补充的次数 | 次 | 2 |

| 权重区间 | 状态 | 处理方式 |
| --- | --- | --- |
| 80-100 | high | 默认优先加载 |
| 60-79 | medium | 条件满足时加载 |
| 40-59 | low | 辅助或观察使用 |
| 0-39 | paused | 暂停默认加载，等待复盘 |

## 4. 动态覆盖 Skill

动态覆盖 Skill 不固定列出可覆盖 Skill 名单，只记录触发条件、业务判断逻辑、处理结果和审计记录。

| 触发条件 | 判断逻辑 | 处理逻辑 | 审计记录 |
| --- | --- | --- | --- |
| 输入资料类型特殊 | 默认 Skill 是否覆盖该资料类型 | 临时加载适配 Skill 并通过真实 Agent / LLM 执行 | 资料类型、覆盖原因 |
| 业务场景跨领域 | 默认 Skill 覆盖不足 | 加载跨领域 Skill | 业务场景标签 |
| 高风险异常 | 是否影响关键输出 | 加载风险复核 Skill | 异常等级 |
| 输出格式变化 | 默认输出格式不适配 | 加载交付或格式化 Skill | 新格式要求 |
| 默认 Skill 输出不完整 | 是否影响最终交付质量 | 加载补充分析 Skill | 缺口和补充结果 |
| 人工复核提出补充 | 人工输入是否改变节点判断 | 加载补充分析或审计 Skill | 人工结论摘要 |

| 覆盖记录字段 | 类型 | 单位 / 范围 | 示例 |
| --- | --- | --- | --- |
| `override_trigger` | 文本 / 枚举 | 可动态扩展 | `human_review_adjustment` |
| `override_reason` | 文本 | 1-300 字 | 人工确认风险字段需复核 |
| `replacement_skill_id` | 文本 | 可为空 | `[dynamic_skill_id]` |
| `coverage_result` | 枚举 | success / failed / partial | success |
| `impact_on_weight` | 数字 | 分值变化 | -5 |

## 5. 执行流程可视化占位

```text
CLI 主循环
  -> 明确触发 agent_system pipeline
  -> 自动进入运行器
主专家
  -> 任务判断、节点分配、复盘优先评估
  -> 独立调用真实 Skill / Agent 执行主节点任务
辅专家
  -> 接收分配节点任务
  -> 独立调用真实 Skill / Agent 完成节点任务
调度层 / DAG
  -> 控制依赖、顺序、并行 / 串行、阻塞、暂停
碳基（人）介入
  -> 通过独立人工审批 UI 审核关键节点、确认异常、补充人工判断
输出 + 审计
  -> 写入 audit.jsonl，记录异常、Skill 使用、人工输入
复盘与权重优化
  -> 汇总主/辅专家与人工输入
  -> 主专家进行复盘优先评估
  -> 更新 Skill 权重和 pipeline 优化建议
```

箭头占位：

```text
CLI 主循环 -> 主智能体 -> 真实 Skill 执行 -> 子专家 / 子智能体 -> 真实 Skill 执行 -> 人工介入 -> 输出 + 审计 -> 复盘与权重优化
```

| 阶段 | 输入 | 输出 | 关联机制 |
| --- | --- | --- | --- |
| CLI 触发 | 用户任务、routes | flow_id、运行器入口 | 自动触发 |
| 主专家判断 | 用户任务、routes、experts、skill_weights | flow_id、节点分配、复盘优先级 | 任务判断 |
| 主专家 Skill 执行 | 输入资料、默认 Skill、私域模板标签、线上凭据状态 | 主节点输出、异常、审计点、API 调用观测 | Skill 层 / delegate_task |
| 辅专家 Skill 执行 | 分配节点、节点上下文、输出约束、线上凭据状态 | 节点结果、异常、待补项、API 调用观测 | Skill 层 / delegate_task |
| 人工介入 | 关键节点、异常、用户确认 | `human_input_summary` | 人工审批 UI / 人工复核 |
| 输出 + 审计 | 节点结果、异常、人工输入 | `audit.jsonl` 记录 | 审计检查点 |
| 复盘 | 历史任务、异常、质量分、人工输入 | `review_summary.json`、`skill_weights.json` 更新记录 | 权重公式 |

## 6. 输入字段模板

| 字段 | 类型 | 必填 | 单位 | 约束 | 枚举 / 允许值 | 示例 |
| --- | --- | --- | --- | --- | --- | --- |
| `task_id` | 文本 | 必填 | 无 | 唯一任务编号 | 动态生成 | `task_20260428_001` |
| `flow_id` | 文本 | 必填 | 无 | 必须存在于 routes | 可动态扩展 | `dashboard_flow` |
| `node_id` | 文本 | 必填 | 无 | 当前任务节点 | 来自 routes | voc_insight |
| `expert_id` | 文本 | 必填 | 无 | 主专家 ID | 来自 experts | user_analyst |
| `secondary_expert_ids` | 列表 | 可选 | 个 | 可为空 | 来自 routes / experts | `[ops_expert]` |
| `execution_owner` | 文本 / 枚举 | 必填 | 无 | 主专家 / 辅专家 / 人工 | primary_expert / secondary_expert / human | primary_expert |
| `source_materials` | 表格 / 文档 | 必填 | 份 | 至少 1 份有效资料 | 文档 / 表格 / 链接 | VOC 表 |
| `sample_size` | 数字 | 可选 | 人 / 条 | 大于 0 | 无 | 1495 |
| `output_format` | 文本 / 枚举 | 必填 | 无 | 可动态扩展 | report / table / pm_input / html | `pm_input` |
| `risk_fields` | 表格 | 可选 | 个 | 仅风险字段 | 可动态扩展 | 返修率 |
| `business_tags` | 文本 / 枚举列表 | 可选 | 个 | 可动态扩展 | VOC / 竞品 / 横评 / 售后 | VOC |
| `default_skill_weights` | JSON | 可选 | 分值 | 0-100 | Skill ID 动态扩展 | `{voc_insight: 90}` |
| `max_spawn_depth` | 数字 | 必填 | 层 | 1-3，按配置限制 | 1 / 2 / 3 | 1 |
| `online_agent_probe` | JSON | 可选 | 无 | 不包含密钥明文，仅记录状态 | credential_status / provider / model | `{credential_status: direct_key_available}` |
| `human_review_required` | 枚举 | 必填 | 无 | 是 / 否 | 是 / 否 | 是 |
| `human_review_decision` | 枚举 | 可选 | 无 | approved / blocked / missing，可扩展 | approved |
| `human_review_blocking` | 布尔 | 可选 | 无 | true / false | false |
| `human_input_summary` | 文本 | 可选 | 字 | 0-1000 字 | 人工结论或评估 | 人工确认 Top15 证据不足 |

枚举扩展规则：

| 枚举字段 | 扩展条件 | 复盘用途 |
| --- | --- | --- |
| `output_format` | 出现新的交付格式 | 分析格式覆盖频率 |
| `business_tags` | 出现新的业务标签 | 优化专家路由 |
| `risk_fields` | 出现新的风险字段 | 优化异常映射 |
| `override_trigger` | 出现新的覆盖原因 | 优化默认 Skill 列表 |
| `execution_owner` | 出现新的执行主体类型 | 优化主/辅专家分工 |
| `human_review_required` | 人工复核场景变化 | 优化人介入规则 |

## 7. 输出字段模板

| 输出物 | 字段 | 类型 | 单位 | 约束 | 示例 |
| --- | --- | --- | --- | --- | --- |
| 节点状态 | `status` | 枚举 | 无 | completed / blocked / failed / optional_failed | completed |
| 节点摘要 | `result_summary` | 文本 | 字 | 20-500 字 | 已完成用户洞察 |
| 结构化输出 | `structured_outputs` | JSON | 组 | 可包含 Top15、场景穿透、代际对比、竞品替代、风险校正、PM 输入 | `{top15_fact_pool: []}` |
| Skill 使用 | `skills_loaded` | 列表 | 个 | 至少 1 个 | `voc_insight` |
| Skill 权重 | `skill_weights` | JSON | 分值 | 0-100 | `{voc_insight: 90}` |
| 主专家执行 | `primary_expert_skill_calls` | 列表 | 次 | 可为空 | `voc_insight` |
| 辅专家执行 | `secondary_expert_skill_calls` | 列表 | 次 | 可为空 | `[ops_dashboard]` |
| 真实执行 | `real_skill_execution` | 布尔 | 无 | 必须记录真实 Agent / LLM / delegate_task 是否执行 | true |
| 执行模式 | `skill_execution_modes` | 列表 | 个 | production_delegate_task / custom_skill_executor / local_default_executor | `[production_delegate_task]` |
| 线上 API 观测 | `online_llm_api_calls` | 数字 | 次 | 大于等于 0；生产成功执行应大于 0 | 1 |
| 子智能体层级 | `max_spawn_depth` | 数字 | 层 | 1-3，必须与运行配置一致 | 2 |
| 人工介入 | `human_review_required` | 枚举 | 无 | 是 / 否 | 是 |
| 人工审批决策 | `human_review_decision` | 枚举 | 无 | approved / blocked / missing，可扩展 | approved |
| 人工阻塞标记 | `human_review_blocking` | 布尔 | 无 | true / false；true 时阻塞下游非 optional 依赖 | false |
| 人工结论 | `human_input_summary` | 文本 | 字 | 0-1000 字 | 人工确认风险需回退 |
| 异常列表 | `exceptions` | 列表 | 个 | 可为空 | `[top15_missing]` |
| 审计结果 | `audit_checks` | JSON | 布尔 / 分值 | 必须可检查 | `{top15_complete: true}` |
| 待补项 | `missing_inputs` | 表格 / 列表 | 个 | 可为空 | 缺竞品字段 |
| 复盘建议 | `review_suggestions` | 文本 / 列表 | 条 | 可为空 | 降低风险 Skill 权重 |

## 8. 人工介入节点模板

| 任务节点 | 人工介入条件 | 人工输入要求 | 反馈去向 |
| --- | --- | --- | --- |
| 输入复核 | VOC、竞品或关键资料缺失 | 补充资料或确认阻塞 | 主/辅专家复盘、审计记录 |
| 风险复核 | FRR/FFR 异常或高风险结论 | 确认是否回退、标记风险等级 | Skill 权重优化、异常映射 |
| 关键输出 | final_output 或 quality_gate 完成 | 确认输出是否可交付 | 审计、复盘摘要 |
| 动态覆盖 | 默认 Skill 输出不完整 | 确认是否启用补充 Skill | 动态覆盖记录 |
| 用户确认 | user_gate=true | 用户确认、修改意见或拒绝原因 | 调度层状态、审计日志 |

## 9. 异常映射规则

模板只定义映射规则，不生成具体统计数据。实际映射由 agent 系统基于 VOC 标签、业务标签、审计检查点和历史复盘统计生成。

| 异常事件 | 触发逻辑 | 处理规则 | 是否阻塞 | 审计字段 | 复盘触发 |
| --- | --- | --- | --- | --- | --- |
| `top15_missing` | Top15 行数 < 15 | 标记证据不足，必要时触发人工复核 | 视情况 | `top15_count` | 是 |
| `frr_ffr_anomaly` | FRR/FFR 缺失或异常 | 回退原始值，标记未校正风险，触发人工确认 | 是 | `risk_adjustment_status` | 是 |
| `competitor_missing` | 竞品字段缺失 | 标记暂无数据，不强行推断 | 否 | `competitor_coverage` | 否 |
| `voc_missing` | VOC 数据缺失 | 阻塞并提示补充 | 是 | `voc_available` | 是 |
| `pm_field_missing` | PM 输入字段缺失 | 退回补充 | 是 | `pm_field_complete` | 是 |
| `human_review_conflict` | 人工结论与系统结论冲突 | 标记需主专家复核 | 是 | `human_input_summary` | 是 |
| `[custom_exception]` | 由标签统计发现 | 按复盘规则处理 | 待定 | 动态扩展 | 待定 |

## 10. 任务管理模板

| 任务 | 目标 | 执行主体 | 默认 Skill + 权重 | 动态覆盖触发 | 人工介入 | 输入约束 | 输出要求 | 异常示例 | 审计检查点 | 私域经验引用 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 任务判断 | 明确任务类型、边界和 DAG 节点 | 主专家 | `[skill_id:weight]` | 跨领域或目标不清晰 | 否 | 业务目标存在 | 任务范围说明 | 目标不清 | 范围清晰 | `EXP-RULE-TASK-001` |
| 节点分配 | 分配主/辅专家执行节点 | 主专家 | `[skill_id:weight]` | 节点复杂或需并行 | 否 | routes 节点存在 | 节点分配表 | 专家缺失 | 分配可追溯 | `EXP-RULE-ASSIGN-001` |
| 主专家节点执行 | 执行主节点 Skill | 主专家 | `[skill_id:weight]` | 默认 Skill 输出不足 | 视情况 | 输入资料可用 | 主节点输出 | 输出缺字段 | Skill 使用已记录 | `EXP-RULE-PRIMARY-SKILL-001` |
| 辅专家节点执行 | 执行分配节点 Skill | 辅专家 | `[skill_id:weight]` | 节点异常或补充判断 | 视情况 | 节点上下文完整 | 节点结果、异常、待补项 | VOC 缺失 | 节点状态可追溯 | `EXP-RULE-SECONDARY-SKILL-001` |
| 人工复核 | 复核关键节点或异常 | 碳基（人） | 无 | 高风险或 user_gate | 是 | 待复核内容存在 | 人工结论 | 结论冲突 | 人工输入已记录 | `EXP-RULE-HUMAN-001` |
| 输出汇总 | 形成最终业务输出 | 主专家 | `[skill_id:weight]` | 输出格式变化 | 视情况 | 目标格式明确 | 最终摘要 / 报告 | PM 字段缺失 | 结构完整 | `EXP-TPL-SUMMARY-001` |
| 复盘沉淀 | 优化权重和规则 | 主专家优先评估，调度层汇总 | `[skill_id:weight]` | 重复异常或覆盖 | 需要时 | 有运行记录 | 复盘摘要 | 同类异常重复 | 有改进建议 | `EXP-TPL-REVIEW-001` |

## 11. 审计检查点

| 检查点 | 量化规则 | 结果字段 |
| --- | --- | --- |
| Top15 完整性 | 行数 = 15 | `top15_complete` |
| Top15 数量 | 0-15 | `top15_count` |
| FRR/FFR 范围 | 只允许风险字段 | `risk_adjustment_scope_valid` |
| 竞品覆盖 | 每行有本品与竞品对比 | `competitor_coverage` |
| PM 字段完整性 | 必填字段全部存在 | `pm_field_complete` |
| 主专家 Skill 记录 | 记录 Skill ID、输入、输出摘要 | `primary_skill_call_recorded` |
| 辅专家 Skill 记录 | 记录 Skill ID、节点、返回状态 | `secondary_skill_call_recorded` |
| 人工介入记录 | `human_review_required=是` 时必须有 `human_input_summary` | `human_review_recorded` |
| 人工审批通道 | `user_gate=true` 时必须有可用回调或 Gateway 输入通道 | `human_review_ui_available` |
| 人工审批决策 | 同意继续 / 确认可交付才放行；阻塞 / 退回复核必须暂停下游 | `human_review_decision`、`human_review_blocking` |
| 动态覆盖记录 | 每次覆盖都有原因和结果 | `dynamic_override_recorded` |
| Skill 使用记录 | 记录 Skill ID 与权重 | `skill_usage_recorded` |
| 真实执行记录 | 生产环境 Skill 调用必须走真实 Agent / LLM / `delegate_task` | `real_skill_execution` |
| 线上调用观测 | 生产环境成功节点应记录 API 调用次数 | `online_llm_call_observed` |

## 12. 复盘与权重优化

| 触发条件 | 说明 |
| --- | --- |
| 双周固定复盘 | 汇总任务、异常、覆盖、人工输入和权重 |
| 关键节点完成 | final_output 或 quality_gate 节点完成 |
| 异常事件 | 出现阻塞或高风险异常 |
| 动态覆盖 | 发生任何动态 Skill 覆盖 |
| 用户反馈异常 | 输出口径或任务路由需要优化 |
| 人工介入 | 人工复核改变结论、阻塞或确认交付 |

复盘摘要字段：

| 字段 | 类型 | 单位 / 范围 | 示例 |
| --- | --- | --- | --- |
| `review_period` | 文本 | 日期范围 | 2026-04-15 至 2026-04-28 |
| `task_count` | 数字 | 个 | 12 |
| `primary_skill_usage` | JSON | 次 | `{voc_insight: 10}` |
| `secondary_skill_usage` | JSON | 次 | `{ops_dashboard: 6}` |
| `dynamic_overrides` | 列表 | 次 | `[input_type_special]` |
| `success_rate` | 数字 | % | 91 |
| `average_output_quality` | 数字 | 0-100 | 86 |
| `exception_stats` | JSON | 次 | `{top15_missing: 2}` |
| `human_review_count` | 数字 | 次 | 3 |
| `human_input_summary` | 文本 / 列表 | 条 | 人工确认两项风险需回退 |
| `dynamic_coverage_frequency` | 数字 | 次 | 3 |
| `weight_adjustment_suggestions` | JSON | 分值变化 | `{voc_insight: +5}` |
| `rule_update_suggestions` | 列表 | 条 | 新增人工复核触发条件 |

## 13. 运行记录模板

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | 单次运行编号 |
| `task_id` | 文本 | 任务编号 |
| `flow_id` | 文本 | 流程编号 |
| `node_id` | 文本 | 节点编号 |
| `primary_expert_id` | 文本 | 主专家编号 |
| `secondary_expert_ids` | 列表 | 辅专家编号 |
| `execution_owner` | 文本 / 枚举 | primary_expert / secondary_expert / human |
| `default_skills` | 列表 | 默认 Skill |
| `loaded_skills` | 列表 | 实际加载 Skill |
| `primary_expert_skill_calls` | 列表 | 主专家 Skill 调用记录 |
| `secondary_expert_skill_calls` | 列表 | 辅专家 Skill 调用记录 |
| `delegate_role` | 文本 / 枚举 | leaf / orchestrator |
| `max_spawn_depth` | 数字 | 当前任务允许的子智能体层级上限 |
| `real_skill_execution` | 布尔 | Skill 是否已绑定真实 Agent / LLM / delegate_task 执行 |
| `dynamic_overrides` | 列表 | 动态覆盖记录 |
| `skill_execution_modes` | 列表 | Skill 执行模式 |
| `real_skill_execution` | 布尔 | 是否真实执行 |
| `online_llm_api_calls` | 数字 | 线上 API 调用观测次数 |
| `human_review_required` | 枚举 | 是 / 否 |
| `human_review_ui_available` | 布尔 | 是否具备人工审批输入通道 |
| `human_review_decision` | 枚举 | approved / blocked / missing |
| `human_review_blocking` | 布尔 | 是否阻塞下游 |
| `human_review_channel` | 文本 | agent_system_approval_ui / preseeded_human_input / unavailable |
| `human_input_summary` | 文本 | 人工结论或评估 |
| `audit_checks` | JSON | 审计结果 |
| `exceptions` | 列表 | 异常事件 |
| `review_triggered` | 布尔 | 是否触发复盘 |
| `next_action` | 文本 | 下一步动作 |

## 14. 私域经验引用

| 引用编号 | 类型 | 用途 | 适用任务 |
| --- | --- | --- | --- |
| `EXP-RULE-TASK-001` | 判断规则 | 判断任务类型 | 任务判断 |
| `EXP-RULE-ASSIGN-001` | 分配规则 | 主/辅专家节点分配 | 节点分配 |
| `EXP-RULE-PRIMARY-SKILL-001` | 调用规则 | 主专家 Skill 执行 | 主专家节点执行 |
| `EXP-RULE-SECONDARY-SKILL-001` | 调用规则 | 辅专家 Skill 执行 | 辅专家节点执行 |
| `EXP-RULE-HUMAN-001` | 人工规则 | 人工复核与确认 | 人工复核 |
| `EXP-RULE-AUDIT-001` | 审计规则 | 输出质量复核 | 输出复核 |
| `EXP-RULE-RISK-001` | 风险规则 | 异常处理 | 异常复核 |
| `EXP-TPL-SUMMARY-001` | 汇总模板 | 最终汇总 | 输出汇总 |
| `EXP-TPL-REVIEW-001` | 复盘模板 | 双周复盘 | 复盘沉淀 |

这里只记录模板编号或经验标签，不嵌入敏感数据、历史项目原文或内部未公开结论。

## 15. 验证要求

### 15.1 静态验证

| 验证项 | 检查方式 | 通过标准 |
| --- | --- | --- |
| 角色职责 | 扫描主专家、辅专家、Skill 层、调度层、人工介入字段 | 不出现职责混淆，辅专家不管理全局 DAG |
| 模板占位 | 扫描 `user_analyst`、`voc_insight`、`human_review_required`、`human_input_summary` 等字段 | 占位完整，可被生成器替换 |
| 异常映射 | 扫描 Top15、VOC、FRR/FFR、竞品、PM 字段异常 | 每个异常都有触发逻辑、处理规则、阻塞标记和复盘触发 |
| 输入 / 输出字段 | 扫描字段类型、单位、枚举、约束 | 字段可审计、可复盘、可动态扩展 |
| 复盘字段 | 扫描复盘触发、权重公式、私域经验引用 | 复盘信息能支撑权重更新和 pipeline 优化 |

### 15.2 运行验证

| 验证项 | 检查方式 | 通过标准 |
| --- | --- | --- |
| DAG 执行 | 运行包含依赖节点的流程 | 无依赖节点可并行，有依赖节点按顺序执行 |
| optional 节点 | 构造 optional 节点失败 | optional 失败不阻断主流程 |
| user_gate 节点 | 缺少 `human_input_summary` | 节点阻塞，下游非 optional 依赖暂停 |
| 人工审批 UI | 运行 user_gate 节点并输入审批结果 | `human_review_decision` 与 `human_input_summary` 进入节点结果、审计和复盘摘要 |
| 人工审批阻塞 | 在 user_gate 中选择阻塞或退回复核 | 当前节点为 blocked，下游非 optional 依赖暂停 |
| CLI 自动触发 | 默认聊天中发送明确 `agent_system + pipeline` 请求 | 无需手动调用脚本，直接返回闭环运行摘要 |
| 多层子智能体 | 配置 `max_spawn_depth > 1` 并构建任务包 | 任务包记录 orchestrator role，DAG 顺序不被破坏 |
| 真实 Skill 绑定 | 运行默认 Skill 节点 | 触发真实 Agent / LLM / `delegate_task`，非仅模板占位 |
| 线上凭据观测 | 生产路径运行默认 Skill 节点 | 记录 credential_status、provider、model，不泄露密钥明文 |
| 线上 API 调用观测 | 生产路径运行默认 Skill 节点 | 成功执行节点记录 `online_llm_call_observed=true` 或提供失败异常 |
| 主/辅专家 Skill 调用 | 运行含主/辅专家的节点 | `primary_expert_skill_calls` 和 `secondary_expert_skill_calls` 均有记录 |
| 异常映射 | 构造 Top15 不足、VOC 缺失等场景 | 异常进入 `exceptions`、`audit_checks` 和复盘摘要 |
| 审计和复盘 | 查看运行产物 | 写入 `audit.jsonl`、`review_summary.json`、`skill_weights.json` |
| 权重自动回写 | 完成复盘后查看权重文件 | `skill_weights.json` 自动更新并保留公式字段 |
| 私域经验 | 查看专家和 Skill 记忆文件 | 运行摘要进入对应 `MEMORY.md` |

## 16. 版本管理

| Version | Release Date | Author | Change Summary |
| --- | --- | --- | --- |
| vX.X | YYYY-MM-DD | Owner | 初始化专家层模板 |
| vX.X | YYYY-MM-DD | Owner | 新增主/辅专家群体协作规则 |
| vX.X | YYYY-MM-DD | Owner | 新增人工介入字段与复核规则 |
| vX.X | YYYY-MM-DD | Owner | 新增默认 Skill 权重公式与动态覆盖占位 |
| vX.X | YYYY-MM-DD | Owner | 更新异常映射规则和复盘字段 |
| vX.X | YYYY-MM-DD | Owner | 更新输入 / 输出字段单位及枚举占位 |
| vX.X | YYYY-MM-DD | Owner | 新增模板占位与运行闭环一致性验证 |
| vX.X | YYYY-MM-DD | Owner | 新增 CLI 自动触发、人工审批 UI、多层子智能体、真实 Skill 绑定和权重自动回写验证 |

变更摘要必须记录默认 Skill、动态覆盖、任务管理、异常映射、复盘策略、人工介入规则、审计标准和验证规则的变化。
