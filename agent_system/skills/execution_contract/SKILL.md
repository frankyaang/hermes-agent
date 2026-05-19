# 执行合同

- English name: `execution_contract`
- 中文名：执行合同
- Type: `delivery`
- Default pipeline: `weekly_flow`
- Private memory: `false`

接收路由为 `decision_agenda` 的议题，生成 `DecisionCard` JSON，通过现有 `artifact_delivery` skill 发送到飞书群；等待负责人回复「确认」后，通过 Feishu gateway 回调将 `confirmed_by_human` 置为 `True`，生成完整 `ExecutionContract`。

## 核心约束

- **初始 `confirmed_by_human=False`**：系统禁止静默将其设为 `True`，必须等待人工回调
- **Commitment 完整性**：`owner`、`action`、`deadline`、`acceptance_criteria` 任一为 `null` → 标记 `incomplete=True`，不计入闭环
- **不处理 fake_closure**：路由为 `fake_closure_detected` 的议题不得生成 ExecutionContract

## DecisionCard 格式

```json
{
  "issue_id": "<uuid>",
  "title": "<议题标题>",
  "chosen_option": "<选定方案>",
  "owner": "<负责人>",
  "deadline": "<截止日期>",
  "acceptance_criteria": "<验收标准>",
  "confirmed_by_human": false
}
```

## 飞书回调流程

1. DecisionCard 通过 `artifact_delivery` 发送到飞书群
2. 负责人在飞书回复「确认」
3. Feishu gateway 回调更新 `confirmed_by_human=True`
4. 生成完整 `ExecutionContract`

## Pipeline

作为 `weekly_flow` 的 step 3，依赖 `decision_gate`，`final_output: true`。
