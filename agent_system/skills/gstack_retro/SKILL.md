# 复盘沉淀

- English name: `gstack_retro`
- Type: `sedimentation`
- Advisory: `false`
- Methodology source: `~/.hermes/skills/gstack-retro/SKILL.md`
- gstack commands: `retro`
- Hermes layer: `sedimentation`（对接经验卡片写入）

项目/迭代复盘：总结经验、识别改进点、写入 Hermes 沉淀层。

## 方法论（来源：gstack retro）

调用此技能时，读取 `~/.hermes/skills/gstack-retro/SKILL.md` 中的认知方法论。

输出通过 Hermes 沉淀管道写入（staging → 人工审核 → experience_card），
不直接写 expert_mem 或 system_mem。

核心结构：
1. 发生了什么——事实记录，不含评判
2. 为什么会这样——根因分析
3. 下次怎么做——具体可执行的改进点
4. 写入沉淀——触发 gstack_learn 或直接写入 experience_card

## Memory

私域经验记录在 `skill_mem/MEMORY.md`。
