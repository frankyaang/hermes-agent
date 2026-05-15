# 输入数据契约

## 必需输入

| 输入 | 格式 | 用途 | 最低要求 |
|---|---|---|---|
| 变更说明 | 文本或 `change_brief.json` | 定义本次只评估什么 | 变更对象、区域、目标 SKU 或功能 |
| 变更前量价渠 | `.xlsx` | 建立基准盘 | 至少包含产品子版本、区域、渠道、销量、ASP、收入、成本、毛利 |
| 变更后量价渠 | `.xlsx` | 建立变更盘 | 字段口径需与变更前可映射 |
| 用户/场景资料 | `.docx`、`.md`、`.txt` | 判断用户价值 | 能说明目标用户、场景、痛点或价值主张 |

## 可选增强输入

| 输入 | 用途 |
|---|---|
| 产品配置图或配置表 | 形成高/中/低配、前后配置差异 |
| 竞品价格/规格 | 判断价格带卡位和防守/进攻价值 |
| BOM 分项 | 解释成本变化来源 |
| 渠道费用率/投放数据 | 判断渠道 ROI 和费用压力 |
| 售后/客诉数据 | 判断配置削减后的服务风险 |
| 库存/产能数据 | 判断执行可行性 |

## 推荐 `change_brief.json`

```json
{
  "change_name": "中国区新增中配版",
  "change_type": ["SKU", "配置", "价格"],
  "target_region": "中国",
  "focus_change_keywords": ["中配"],
  "baseline_scope": "变更前中国区同系列量价渠",
  "competitor_price": 3598,
  "decision_constraints": [
    "价格使用国补后口径",
    "只归因新增中配相关影响",
    "行动计划使用经营级5W2H"
  ]
}
```

## Excel 字段映射

脚本默认识别以下中文字段：

| 标准字段 | 默认表头 |
|---|---|
| product_version | 产品版本 |
| product_subversion | 产品子版本 |
| region | 销售区域 |
| channel | 渠道 |
| msrp | 建议市场零售价 (CNY) |
| channel_units | 渠道销量 |
| asp | ASP |
| net_sales_unit | Net Sales |
| channel_revenue | 渠道销售收入 |
| target_cost_unit | 目标成本 (含税) (CNY) |
| channel_cost | 渠道销售成本 |
| channel_gross_margin | 渠道毛利额 |

如字段名不同，先在分析中说明映射关系，再运行脚本或修改输入表头。

## 归因边界

必须先声明三类变化：

- `directly_related`：新增 SKU、目标配置或明确由本次变更触发的变化。
- `portfolio_related`：同系列受价格阶梯或组合调整影响的变化。
- `not_attributed`：同期自然更新、海外区域变化、渠道口径调整或未被变更说明覆盖的变化。

没有归因边界时，默认只能输出 `条件认可` 或 `补数后再决策`，不能直接输出强认可。
