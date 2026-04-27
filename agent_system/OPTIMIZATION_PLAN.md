# Agent 系统优化方案（产品运营 Dashboard 修正版）

## 1. 核心优化逻辑

产品运营 Dashboard 的最终业务内容由 `ops_dashboard（运营看板）` 输出，不再追加通用 `final_report（最终报告）` 节点。

正确责任链：

```text
ops_expert（运营专家）
-> ops_dashboard（运营看板）
-> 产品运营报告与Dashboard结构
```

如果用户需要 HTML/PDF，再追加：

```text
dashboard_html（看板渲染）
```

这样可以保持：

- 报告内容由报告生成类 Skill 负责。
- 页面呈现由渲染类 Skill 负责。
- 专家层负责判断、复核和编排。
- 调度层负责流程选择和质量门禁。

## 2. 主流程

### `insight_flow（洞察流程）`

适用于用户只需要分析结论：

```text
voc_insight（用户洞察）
-> briefing（过程汇报，可选）
```

最终输出来自 `voc_insight（用户洞察）`。

### `dashboard_flow（看板流程）`

适用于用户需要产品运营 Dashboard：

```text
voc_insight（用户洞察）
-> ops_dashboard（运营看板）
-> briefing（过程汇报，可选）
```

最终输出来自 `ops_dashboard（运营看板）`。

### `html_flow（网页流程）`

适用于用户需要 HTML/PDF：

```text
voc_insight（用户洞察）
-> ops_dashboard（运营看板）
-> dashboard_html（看板渲染）
-> audit（核查，可选）
```

最终输出来自 `dashboard_html（看板渲染）`。

## 3. 辅助能力

`superpowers（思考辅助）`：

- 由专家层按需调用。
- 作用于任务理解、分析框架选择、Dashboard 结构设计、专家冲突复核和交付质量检查。
- 不进入主 Pipeline，不替代主专家或主 Skill。

`briefing（过程汇报）`：

- 由调度层在关键节点完成后按需触发。
- 输入必须包含来源节点、中文名、状态、关键输出、风险和下一步。
- 作为共享能力服务所有节点，不为每个 Skill 单独复制。

`audit（核查）`：

- 交付前或用户查询时触发。
- 检查结论一致性、字段完整性、流程状态、用户守门和审计日志。

## 4. 质量门禁

`ops_dashboard（运营看板）` 必须满足：

- 消费 `voc_insight（用户洞察）` 的上游结论。
- 不擅自改写用户洞察结论。
- 生成产品运营视角的指标、风险、机会、优先级和建议动作。
- 保留关键表格字段。
- 明确区分报告内容和 HTML/PDF 呈现。
- 给 `dashboard_html（看板渲染）` 提供结构化输入。
- 在审计日志中同时记录英文名和中文名。

`dashboard_html（看板渲染）` 必须满足：

- 只消费 `ops_dashboard（运营看板）` 的结构化输出。
- 不重新生成报告结论。
- 不改变运营建议。
- 输出 HTML/PDF 或可视化页面布局。

## 5. 后续执行建议

- 继续保持 `skills/domain/product-ops-dashboard`、`robot-product-voc-survey-insight`、`voc-dashboard-html` 源技能稳定。
- 后续若要做共享内核迁移，应作为第二阶段单独计划，不能混入本次接入式重构。
- 任何新增报告类型都应新增对应报告生成 Skill，而不是复活通用 `final_report（最终报告）`。
