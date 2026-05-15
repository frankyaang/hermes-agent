---
name: evaluate-change-value
description: Evaluate product, SKU, configuration, pricing, channel, cost, region, or feature changes with evidence-grounded user, market, financial, attribution, and audit analysis. Use when Codex needs to decide whether to approve a business/product change, compare before/after volume-price-channel spreadsheets, quantify revenue/margin/cannibalization impact, build an evidence matrix, or produce a decision card and operating 5W2H action plan from DOCX/XLSX/configuration/competitor inputs.
---

# 变更价值评估

把产品或经营变更评估成可复核的决策包。默认回答：这次变更是否值得认可、为什么、风险在哪里、后续如何管。

## 快速路径

1. 先锁定变更对象和归因边界，不把同期自然变化都归因给本次变更。
2. 判断变更类型：`SKU`、`配置`、`价格`、`渠道`、`成本`、`区域`、`功能`。
3. 有 DOCX/XLSX 等文件时，优先运行脚本生成事实底座：
   ```bash
   python scripts/run_evaluation.py --input-dir <source_folder> --output-dir <output_folder> --case-name <case_name>
   ```
4. 读取脚本输出的 `metric_bridge.csv`、`attribution_table.csv`、`evidence_matrix.json`、`audit_report.json`，再写经营判断。
5. 最终交付必须包含：`decision_card.md`、`metric_bridge.csv`、`attribution_table.csv`、`evidence_matrix.json`、`audit_report.json`、`5w2h_action_plan.md`。

## 什么时候读 references

- 输入字段、最小数据要求不清楚：读 `references/input_contract.md`。
- 要解释 Data Analysis Pipeline 和 Insight Pipeline：读 `references/pipeline_spec.md`。
- 要生成标准交付物：读 `references/output_contract.md`。
- 要判断是否阻塞、降级或条件认可：读 `references/audit_rules.md`。
- 要参考莎士比亚 T90 golden case：读 `references/case_shakespeare_t90.md`。

## 默认判断框架

固定使用这条链：

`变更定义 -> 归因边界 -> 价值假设 -> 数据事实 -> 证据矩阵 -> 风险审计 -> 决策分级 -> 5W2H`

决策分级只使用：

- `认可`：净价值为正，关键风险可控，证据完整。
- `条件认可`：净价值为正，但毛利率、蚕食、渠道费用、供应链或售后风险需要管控。
- `试点观察`：方向有价值，但关键输入缺失或不确定性高。
- `不认可`：财务或组合净价值为负，或风险超过可控范围。
- `补数后再决策`：缺少前后口径、销量、成本、毛利或归因边界。

## 数据分析原则

- 先输出事实表，再输出观点。
- 每个关键结论必须回挂到来源、指标或明确假设。
- 同期发生的价格、渠道、成本、区域变化，不能默认归因给本次变更。
- 毛利额增长但毛利率下降时，默认至少为 `条件认可`，需要经营管控。
- 新增低价 SKU 带来增量时，必须检查主力 SKU 和高端 SKU 的蚕食风险。

## 脚本

- `scripts/extract_sources.py`：扫描输入目录，抽取 DOCX/XLSX 元数据、用户证据和来源清单。
- `scripts/build_metric_bridge.py`：读取变更前/后量价渠表，输出指标桥和归因表。
- `scripts/build_evidence_matrix.py`：把价值假设、用户证据、财务事实和竞争信息绑定成证据矩阵。
- `scripts/validate_decision_pack.py`：检查交付物完整性、公式、证据覆盖和阻塞项。
- `scripts/run_evaluation.py`：串联上述脚本并生成标准决策包。

脚本负责事实和结构化草稿，最终经营语言由 Codex 基于输出文件完成。不要让脚本硬写不可复核的业务判断。

## 输入目录建议

输入目录可以包含：

- 用户研究 DOCX。
- 变更前量价渠 XLSX。
- 变更后量价渠 XLSX。
- 产品配置截图或配置说明。
- `change_brief.json`，用于声明目标区域、新增 SKU、竞品价、决策约束。

`change_brief.json` 示例：

```json
{
  "change_name": "中国区新增中配版",
  "target_region": "中国",
  "focus_change_keywords": ["中配"],
  "competitor_price": 3598,
  "decision_constraints": ["价格使用国补后口径", "5W2H 不写营销动作"]
}
```

## 输出写法

最终回答优先按这个顺序写：

1. `结论`：认可 / 条件认可 / 试点观察 / 不认可 / 补数后再决策。
2. `为什么`：用户价值、竞争价值、财务价值、组合风险。
3. `关键数字`：销量、收入、毛利、毛利率、ASP、成本、SKU/渠道变化。
4. `风险`：内部蚕食、毛利率下滑、渠道费用、库存、供应链、售后。
5. `下一步`：经营级 5W2H，带指标和预警线。

避免写成营销话术。这个 Skill 的目标是经营决策，不是广告包装。
