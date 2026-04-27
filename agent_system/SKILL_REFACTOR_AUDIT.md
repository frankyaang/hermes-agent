# 产品运营 Dashboard 技能重构审计

## 1. 当前结论

本阶段采用“接入式重构”，不拆改三个 domain skill 的内部脚本：

- `robot-product-voc-survey-insight` → `voc_insight（用户洞察）`
- `product-ops-dashboard` → `ops_dashboard（运营看板）`
- `voc-dashboard-html` → `dashboard_html（看板渲染）`

重构重点是把已有能力资产纳入 `agent_system` 的 Skill、Expert 和 Scheduler 标准架构，由专家层和调度层负责调用逻辑。

## 2. 职责归类

| 标准英文名 | 中文名 | 类型 | 来源 |
| --- | --- | --- | --- |
| `voc_insight` | 用户洞察 | `analysis` | `robot-product-voc-survey-insight` |
| `ops_dashboard` | 运营看板 | `report_generation` | `product-ops-dashboard` |
| `dashboard_html` | 看板渲染 | `ui_render` | `voc-dashboard-html` |
| `superpowers` | 思考辅助 | `analysis_assist` | Superpowers |
| `briefing` | 过程汇报 | `status_report` | 通用过程汇报能力 |
| `audit` | 核查 | `audit` | 核查模块 |

## 3. 产品运营 Dashboard 边界

`ops_dashboard（运营看板）` 是产品运营 Dashboard 场景里的最终业务内容输出者。它负责：

- 产品运营主报告。
- Dashboard 信息架构。
- 关键指标表格。
- 用户洞察到运营动作的映射。
- 风险、机会、优先级和建议动作。
- 可交给渲染层的结构化看板内容。

它不负责：

- HTML/PDF 渲染。
- 改写 `voc_insight（用户洞察）` 的上游结论。
- 作为通用最终报告打包器服务所有业务场景。

## 4. 渲染边界

`dashboard_html（看板渲染）` 只做呈现：

- 消费 `ops_dashboard（运营看板）` 的结构化输出。
- 生成 HTML、PDF 或可视化页面布局。
- 不重新判断结论。
- 不改写运营建议。

## 5. 专家与调度规则

专家：

- `user_analyst（用户分析专家）` 主调 `voc_insight（用户洞察）`。
- `ops_expert（运营专家）` 主调 `ops_dashboard（运营看板）`。
- `render_expert（渲染专家）` 主调 `dashboard_html（看板渲染）`。
- `audit_expert（核查专家）` 主调 `audit（核查）`。

流程：

- `insight_flow（洞察流程）`：`voc_insight（用户洞察）`。
- `dashboard_flow（看板流程）`：`voc_insight（用户洞察） -> ops_dashboard（运营看板）`。
- `html_flow（网页流程）`：`voc_insight（用户洞察） -> ops_dashboard（运营看板） -> dashboard_html（看板渲染）`。

辅助能力：

- `superpowers（思考辅助）` 由专家按需调用，不进入主流程。
- `briefing（过程汇报）` 由调度层按关键节点触发，不为每个 Skill 复制。
- `audit（核查）` 在交付前或用户查询时触发。

## 6. 核查标准

`ops_dashboard（运营看板）` 的核查重点：

- 是否使用了 `voc_insight（用户洞察）` 的上游结论。
- 是否擅自改写用户洞察结论。
- 是否生成产品运营视角的指标、风险、机会和动作。
- 是否保留关键表格字段。
- 是否清楚区分报告内容和页面渲染。
- 是否给 `dashboard_html（看板渲染）` 提供结构化输入。
- 是否在审计日志中记录英文名和中文名。

## 7. 暂缓事项

共享内核迁移、脚本去重和 wrapper 兼容属于第二阶段工作。本阶段不创建 `robot-product-insight-core`，不移动生产脚本，避免影响现有 Hermes skill 的可运行性。
