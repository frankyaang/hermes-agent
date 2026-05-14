## [LRN-20260511-001] correction

**Logged**: 2026-05-11T09:59:47Z
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
VOC 分析技能必须区分分析逻辑和显示逻辑，不能把 dashboard/report 的章节结构误当成分析推导流程。

### Details
用户指出：显示逻辑只是为了让人看得更清楚；分析逻辑才是一步一步如何得到内容。该提醒不是要求只关注分析、不关注展示，而是要求明确两者可能不同，不能默认同构。此前复盘中把“用户任务翻译、Top15 风险穿透、代际对比、竞品对打”等报告展示模块混入分析流程，容易导致技能把结论展示顺序误当成结论生成顺序。

### Suggested Action
后续设计 VOC 相关技能时，应同时保留分析与展示两个能力面，但显式区分其输入输出和依赖关系：评论结构化抽取、指标聚合、Top 指标选择属于事实/指标层；用户任务解释、风险定性、代际判断、竞品替代逻辑属于结论层；HTML、dashboard、PPT、文档排版属于显示层。展示层可以重组结论以便阅读，但不能反过来定义分析推导顺序。

### Metadata
- Source: user_feedback
- Related Files: /Users/frank/Desktop/cross_brand_voc_dashboard_2026-04-10(1).html
- Tags: voc-analysis, skill-design, display-vs-analysis, hermes-agent

---
