# 主调度器

- English name: `main_scheduler`
- 中文名：主调度器
- Exception handling: `default_strategy`
- Decision logging: `true`

负责洞察流程、看板流程和网页流程的任务分配、监督、异常处理和决策日志

## Supervised Modules

- `experts`（专家层）
- `skills`（技能层）

## Routes

Pipeline 节点、约束和监督关系记录在 `routes.json`。

## Decision Log

调度决策记录在 `decision_log.md`。
