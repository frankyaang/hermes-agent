# Product Ops Dashboard Asset Harness

Canonical ID：`product-ops-dashboard`
Formal Agent Name：`ProductOpsDashboard`
中文名：`产品运营Dashboard`
方法别名：`看用户`
用途：以“看用户”方法为事实底座，生成机器人产品用户洞察主报告，并按需桥接成产品运营 Dashboard 成品。

## 治理头

- 输入契约：标准化机器人分析参数、竞品范围、质量输入与 Dashboard 交付意图
- 输出契约：默认双交付 `main_report（主报告） + dashboard_html（Dashboard 成品）`
- human gate 策略：`allow_proxy_but_mark_directional_only`
- recovery 策略：主报告先于 Dashboard；主报告未通过时不继续成品渲染

## Role

`product-ops-dashboard` 是机器人产品分析与 Dashboard 组装资产。

它负责：

- 读取标准化机器人分析参数
- 生成主报告、专题稿、附录与任务板
- 把主报告收成 Dashboard 信息架构
- 在需要时桥接 `voc-dashboard-html`

## Output Rule

必须至少能索引到：

- `main_report`
- `artifact_manifest`

如果用户要求 Dashboard 成品，还应索引到：

- `dashboard_html`
- `dashboard_manifest`
- `dashboard_audit`

## Validation Focus

- 主报告是否仍满足“像一个会做产品的人在读用户”
- Dashboard 是否直接消费主报告，而不是二次改写
- `voc-dashboard-html` 桥接是否明确
