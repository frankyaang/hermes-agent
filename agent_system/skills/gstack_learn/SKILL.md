# 经验提炼

- English name: `gstack_learn`
- Type: `sedimentation`
- Methodology source: `~/.hermes/skills/gstack-learn/SKILL.md`
- gstack commands: `learn`
- Hermes layer: `sedimentation`

从任务历史中提炼可复用经验，写入 Hermes 经验卡片。

## 方法论（来源：gstack learn）

调用此技能时，读取 `~/.hermes/skills/gstack-learn/SKILL.md` 中的认知方法论。

输出通过 Hermes 沉淀管道：经验草稿 → staging → 人工审核 → experience_card。

核心步骤：
1. 识别可复用模式——哪些决策/方法有推广价值
2. 提炼为结构化经验——标题/背景/做法/效果/适用场景
3. 提交 staging——等待人工确认写入 experience_card
4. 不直接写 expert_mem——遵守 Hermes ACL 约束

## Memory

私域经验记录在 `skill_mem/MEMORY.md`。
