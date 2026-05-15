# Pipeline 规格

## Data Analysis Pipeline

目标：只产事实，不抢结论。

| 步骤 | 输入 | 处理 | 输出 |
|---|---|---|---|
| 1. Source Intake | 输入目录 | 扫描文件、hash、角色识别 | `source_registry.json` |
| 2. Change Boundary | `change_brief.json`、用户说明 | 明确对象、区域、关键词、排除项 | `change_brief_used.json` |
| 3. User Evidence | DOCX/MD/TXT | 抽取用户画像、场景、痛点、价值主张 | `user_evidence.json` |
| 4. Metric Normalize | 前后 XLSX | 字段映射、数值类型统一 | 内存清洗表 |
| 5. Metric Bridge | 清洗表 | 按区域、SKU、渠道计算前后差异 | `metric_bridge.csv` |
| 6. Attribution | bridge + change brief | 标注直接相关、组合相关、不可归因 | `attribution_table.csv` |
| 7. Summary Facts | bridge | 计算总盘、新增 SKU、价格带事实 | `metric_summary.json` |

## Insight Pipeline

目标：把事实转成经营判断。

| 步骤 | 输入 | 判断问题 | 输出 |
|---|---|---|---|
| 1. Value Hypotheses | change brief | 变更理论上创造什么价值 | 价值假设 |
| 2. Evidence Match | facts + user evidence | 每个假设是否有证据 | `evidence_matrix.json` |
| 3. User Value | 用户证据 + 配置差异 | 是否命中真实场景 | 用户价值判断 |
| 4. Market Value | 价格带 + 竞品 | 是否防守/进攻有效 | 竞争卡位判断 |
| 5. Financial Value | metric summary | 是否创造净收入/毛利 | 财务判断 |
| 6. Portfolio Risk | attribution table | 是否伤害主力 SKU | 组合风险判断 |
| 7. Decision Grade | 全部证据 | 认可/条件认可/试点/不认可 | `decision_card.md` |
| 8. Operating Plan | 风险和机会 | 谁在何时管什么指标 | `5w2h_action_plan.md` |

## Agent 拆分建议

独立 Skill 不依赖 `agent_system`，但如果后续接入 Hermes 运行器，建议：

- Planner Agent：生成 `change_brief`、归因边界、Pipeline DAG 和审计规则。
- Execution Agent：运行脚本，产出事实表、指标桥、证据矩阵草稿。
- Audit Agent：检查证据覆盖、公式一致性、归因越界和结论强度。

核心原则：Planner 管边界，Execution 管事实，Audit 管可信度。
