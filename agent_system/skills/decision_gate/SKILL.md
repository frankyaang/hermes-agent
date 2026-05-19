# 决策准入

- English name: `decision_gate`
- 中文名：决策准入
- Type: `evaluation`
- Default pipeline: `weekly_flow`
- Private memory: `false`

接收 `issue_extractor` 输出的 `List[Issue]`，对每条议题进行纯函数路由，产出 `DecisionRoute` 映射表。

## 路由结果（互斥）

| 路由 | 条件 |
|---|---|
| `decision_agenda` | `recommended_option` 存在 + `acceptance_criteria` 存在 + 无伪闭环 |
| `need_more_info` | `recommended_option` 为 `null` 或 `acceptance_criteria` 为 `null` |
| `fake_closure_detected` | 检测到伪闭环语言（7 类 FAKE_CLOSURE_PATTERNS） |
| `async_pre_read` | `urgency=low` 且选项数 > 3 |

## 伪闭环模式（FAKE_CLOSURE_PATTERNS）

覆盖 7 类：持续跟进、产品线配合一下、会后再看、原则上认可、先试试看、尽快推动落实、持续跟进

## 核心 Invariant

- `fake_closure_detected` 优先级高于 `need_more_info`
- `invalid_decision_agenda_rate` 必须 = 0.00（缺字段的议题不得进入 decision_agenda）

## Pipeline

作为 `weekly_flow` 的 step 2，依赖 `issue_extractor`，输出传入 `execution_contract`（step 3）。

## Memory

无私域经验（`private_memory: false`），评估逻辑为纯函数，无副作用。
