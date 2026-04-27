# Agent 系统建设文档（产品运营 Dashboard 修正版）

## 1. 项目结构

- 根目录：`agent_system`
- `scheduler`：调度层，负责流程选择、节点监督、异常处理和决策日志。
- `experts`：专家层，负责判断任务、选择 Skill、主辅复核和交付编排。
- `skills`：Skill 层，负责具体分析、报告生成、渲染、过程汇报和核查。
- `memory`：用户偏好、对话记忆和个体差异化模块。
- `audit`：生成物日志、质量门禁和复盘追踪模块。
- `tests`：测试用例占位。

所有正式能力都使用简洁英文名和简洁中文名，格式为 `english_id（中文名）`。

## 2. Skill 层能力

| 英文名 | 中文名 | 类型 | 职责 |
| --- | --- | --- | --- |
| `voc_insight` | 用户洞察 | `analysis` | 分析 VOC、评论、竞品和质量反馈 |
| `ops_dashboard` | 运营看板 | `report_generation` | 生成产品运营报告和 Dashboard 结构 |
| `dashboard_html` | 看板渲染 | `ui_render` | 渲染 HTML/PDF，不改写业务内容 |
| `superpowers` | 思考辅助 | `analysis_assist` | 辅助专家判断和复核 |
| `briefing` | 过程汇报 | `status_report` | 关键节点完成后的自然语言汇报 |
| `audit` | 核查 | `audit` | 检查结论、字段、流程和日志 |

关键规则：

- `ops_dashboard（运营看板）` 是产品运营 Dashboard 场景的最终业务内容输出者。
- 不再设置通用 `final_report（最终报告）` Skill。
- `dashboard_html（看板渲染）` 只做呈现，不重新生成报告结论。
- `superpowers（思考辅助）` 是专家辅助能力，不进入主 Pipeline。
- `briefing（过程汇报）` 是共享过程能力，不为每个 Skill 复制一份。

初始化入口：

- `init_skills.py`

## 3. Expert 层能力

| 英文名 | 中文名 | 主技能 | 职责 |
| --- | --- | --- | --- |
| `user_analyst` | 用户分析专家 | `voc_insight（用户洞察）` | 负责用户洞察和 VOC 分析 |
| `ops_expert` | 运营专家 | `ops_dashboard（运营看板）` | 负责产品运营报告和 Dashboard 交付 |
| `render_expert` | 渲染专家 | `dashboard_html（看板渲染）` | 负责 HTML/PDF 呈现质量 |
| `audit_expert` | 核查专家 | `audit（核查）` | 负责交付前质量检查 |

专家层只做判断、选择、复核和编排，不拆改原始 Hermes skill 的内部逻辑。

初始化入口：

- `init_experts.py`

## 4. Scheduler 层能力

调度者：

- `main_scheduler（主调度器）`

标准流程：

### `insight_flow（洞察流程）`

适用于用户只要分析结论：

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

最终输出来自 `dashboard_html（看板渲染）`，核查结果作为质量门禁和日志依据。

初始化入口：

- `init_scheduler.py`

## 5. 用户和记忆模块

用户偏好建议字段：

- `preferred_skills`：如 `voc_insight`、`ops_dashboard`、`briefing`。
- `output_style`：输出粒度，如 `concise`、`medium`、`detailed`。
- `report_format`：输出形态，如 `insight`、`dashboard`、`html`。

使用方式：

- 用户只要洞察时走 `insight_flow（洞察流程）`。
- 用户偏好或请求包含 Dashboard、看板、HTML、PDF、可视化时，进入 `dashboard_flow（看板流程）` 或 `html_flow（网页流程）`。
- 专家和 Skill 可读取用户偏好，但不能跨用户读取私域记忆。

初始化入口：

- `init_memory.py`
- `init_multi_user_memory.py`

## 6. 核查模块

`ops_dashboard（运营看板）` 的质量门禁：

- 是否使用了 `voc_insight（用户洞察）` 的上游结论。
- 是否擅自改写用户洞察结论。
- 是否生成产品运营视角的指标、风险、机会和动作。
- 是否保留关键表格字段。
- 是否清楚区分报告内容和页面渲染。
- 是否给 `dashboard_html（看板渲染）` 提供结构化输入。
- 审计日志是否同时记录英文名和中文名。

初始化入口：

- `init_audit.py`

## 7. 备注

- 原始 Hermes skill 路径保留为能力来源，不作为标准架构主名称。
- `product-ops-dashboard` 对应 `ops_dashboard（运营看板）`。
- `robot-product-voc-survey-insight` 对应 `voc_insight（用户洞察）`。
- `voc-dashboard-html` 对应 `dashboard_html（看板渲染）`。
- 架构图见 `ARCHITECTURE.md`，优化说明见 `OPTIMIZATION_PLAN.md`。
