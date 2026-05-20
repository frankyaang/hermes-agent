# 发布交付

- English name: `gstack_ship`
- Type: `deployment`
- Advisory: `true`
- Methodology source: `~/.hermes/skills/gstack-ship/SKILL.md`
- gstack commands: `ship`, `land-and-deploy`, `canary`

完整发布流程、金丝雀发布、落地验证。

## 方法论（来源：gstack ship/land-and-deploy/canary）

调用此技能时，读取 `~/.hermes/skills/gstack-ship/SKILL.md` 中的认知方法论，
使用 Hermes 的工具集执行。

核心流程：
1. 预发布检查——分支状态、测试通过、依赖锁定
2. 发布执行——选择合适的发布策略（full/canary）
3. 落地验证——流量监控、错误率、关键指标
4. 回滚准备——失败条件明确，回滚路径可执行

## Memory

私域经验记录在 `skill_mem/MEMORY.md`。
