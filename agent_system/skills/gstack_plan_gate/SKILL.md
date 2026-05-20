# 规划门禁

- English name: `gstack_plan_gate`
- Type: `advisory_gate`
- Advisory: `true`（non-blocking，optional）
- Methodology source: `~/.hermes/skills/gstack-plan-eng-review/SKILL.md`
- gstack commands: `office-hours`, `plan-eng-review`, `plan-ceo-review`, `autoplan`, `plan-design-review`, `plan-devex-review`
- Hermes layer: `scheduler`（pipeline 启动前的 advisory 检查）

Pipeline 启动前的 advisory 规划审查：从工程/产品/设计视角检查任务计划。

## 方法论（来源：gstack planning 系列）

调用此技能时，根据任务类型选择对应的 gstack 方法论文件：
- 工程评审 → `~/.hermes/skills/gstack-plan-eng-review/SKILL.md`
- CEO/产品视角 → `~/.hermes/skills/gstack-plan-ceo-review/SKILL.md`
- 设计评审 → `~/.hermes/skills/gstack-plan-design-review/SKILL.md`
- 开发者体验 → `~/.hermes/skills/gstack-plan-devex-review/SKILL.md`
- 自动规划分解 → `~/.hermes/skills/gstack-autoplan/SKILL.md`
- 开放性战略咨询 → `~/.hermes/skills/gstack-office-hours/SKILL.md`

结果为 advisory only——提供建议，不阻断 pipeline 执行。

## 调度层接入

注册在 `routes.json` 中 `step: "pre_advisory"`，`optional: true`。
在以下 pipelines 中激活：
- `artifact_delivery_flow`（交付前规划审查）
- `doc_publish_flow`（发布前规划审查）

## Memory

私域经验记录在 `skill_mem/MEMORY.md`。
