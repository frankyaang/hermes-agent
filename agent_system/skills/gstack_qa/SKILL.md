# 质量门禁

- English name: `gstack_qa`
- Type: `quality_gate`
- Advisory: `true`（不阻断主流程）
- Methodology source: `~/.hermes/skills/gstack-qa/SKILL.md`
- gstack commands: `qa`, `qa-only`

发布前质量验证：功能测试覆盖、边界用例、回归检查、SQL 安全性。

## 方法论（来源：gstack qa）

调用此技能时，读取 `~/.hermes/skills/gstack-qa/SKILL.md` 中的认知方法论，
使用 Hermes 的工具集执行（不依赖 gstack CLI binary）。

核心检查清单：
1. 功能路径覆盖——主流程、失败路径、边界值
2. 数据安全——SQL 注入、权限校验、输入过滤
3. 回归风险——与现有功能的交互影响
4. 输出质量——响应格式、错误信息、日志可读性

## Memory

私域经验记录在 `skill_mem/MEMORY.md`，用于沉淀该 Skill 自己的 QA 经验。
