# 性能基准测试

- English name: `gstack_benchmark`
- Type: `evaluation`
- Advisory: `true`
- Methodology source: `~/.hermes/skills/gstack-benchmark/SKILL.md`
- gstack commands: `benchmark`, `benchmark-models`

性能基准评估：多模型对比、指标采集、性能回归检查。

## 方法论（来源：gstack benchmark/benchmark-models）

调用此技能时，读取 `~/.hermes/skills/gstack-benchmark/SKILL.md` 中的认知方法论，
使用 Hermes 工具集执行。

核心步骤：
1. 定义基准指标——延迟、吞吐量、质量分、成本
2. 设计对比组——baseline vs. 候选方案
3. 执行测量——多次采样，排除抖动
4. 结论输出——指标对比表、推荐结论、回归风险评估

## Memory

私域经验记录在 `skill_mem/MEMORY.md`。
