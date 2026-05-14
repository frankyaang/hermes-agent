# ops_dashboard 节点结果｜user_analyst × voc_insight：张欢重要沟通雷达提醒暂停运营看板

## 1. 节点执行信息
- **task_id**: `dashboard_flow:ops_dashboard`
- **flow_id / node_id**: `dashboard_flow` / `ops_dashboard`
- **节点名称**: 运营看板
- **执行身份**: `user_analyst`（secondary expert）
- **调用 Skill**: `voc_insight`
- **requested_skill_id**: `ops_dashboard`
- **生成时间**: 2026-05-11T14:23:05+08:00
- **输入材料数**: 1
- **输出类型**: 产品运营报告与 Dashboard 结构
- **执行状态**: `completed_with_user_pause_verified`

## 2. 节点结论
用户原话 **“暂停重要沟通雷达的提醒”** 已被识别为明确的提醒暂停 / opt-out 信号。结合上游 `voc_insight` 与 `ops_dashboard` 结果，本轮不是“没有重要沟通事项”，而是：在张欢本人 Feishu `user_access_token` 缺失的权限缺口下，重要沟通雷达无法产出可行动事项，继续多次日内提醒会变成低价值打扰。

当前运营状态已核验：`张欢-重要沟通雷达` 定时任务 `6bb4cce497f8` 为 `state=paused`、`enabled=false`。本节点没有再次执行 pause 副作用，只做用户洞察复核、看板化沉淀和父流程可消费的结构化交付。

## 3. 输入信号与用户洞察
| 维度 | 判断 |
| --- | --- |
| 用户原话 | 暂停重要沟通雷达的提醒 |
| 意图分类 | `pause_recurring_reminder` / `monitoring_control_intent` |
| 用户核心诉求 | 停止无实质增量的高频提醒，而不是继续接收 OAuth 缺口解释 |
| 体验断点 | 权限缺失导致雷达无法输出事项，提醒本身成为噪声 |
| 产品含义 | 零数据权限缺口应从“定时提醒”降级为“静默健康状态 + 可恢复入口” |
| 信任边界 | 不越权读取、不伪造事项、不反复打扰 |

关键用户洞察：**提醒类 Agent 在无数据能力时，用户首先评估的是提醒是否有行动价值；当提醒只重复暴露权限缺口，就应优先尊重暂停选择，而不是继续推动授权。**

## 4. 看板化核心指标
| 指标 | 当前值 | 运营解释 |
| --- | ---: | --- |
| 目标 job_id | `6bb4cce497f8` | 用户点名的“重要沟通雷达”任务 |
| 任务名称 | 张欢-重要沟通雷达 | 本次暂停范围仅限该雷达 |
| 调度计划 | `0 10,14,17,21 * * 1-5` | 工作日 10/14/17/21 点；暂停后不再触发提醒 |
| 当前状态 | `paused` | 已符合用户暂停要求 |
| enabled | `false` | 后续不会按原节奏发送提醒 |
| paused_at | `2026-05-11T14:16:39.821372+08:00` | 已由前序 ops_dashboard 执行动作完成 |
| 张欢 UAT 状态 | `has_token=false / status=missing` | 仍不具备读取私域历史的前置条件 |
| 可读私域来源 | 0 | 不代表真实无消息，只代表未获授权不可读 |
| 私域历史读取 | 0 | 本节点未读取，也不应越权读取 |
| app/bot fallback | 未使用 | 符合 person-scoped UAT 边界 |
| token/secret/code 暴露 | 0 | 本报告不输出任何敏感凭证 |
| 邻近周报任务 | `81b57c7a99c4` 仍 `scheduled/enabled=true` | 用户未要求暂停周度工作复盘，不扩大影响范围 |

## 5. Dashboard 信息架构
### 5.1 运营状态摘要卡
| 卡片 | 字段 | 当前展示 |
| --- | --- | --- |
| 提醒状态 | 雷达是否启用、最近暂停时间、恢复入口 | 已暂停；恢复需用户明确说“恢复重要沟通雷达” |
| 权限健康 | UAT 状态、可读来源数、阻塞原因 | UAT missing；可读来源 0；阻塞原因为本人授权缺失 |
| 用户反馈 | 最近一次控制指令、处理状态 | 用户要求暂停；已核验暂停生效 |
| 影响范围 | 被暂停任务、未变更任务 | 仅重要沟通雷达；周度工作复盘未变更 |

### 5.2 权限缺口健康区
| 模块 | 看板字段 | 触发逻辑 |
| --- | --- | --- |
| UAT 状态 | has_token/status/last_checked | 每次雷达运行前先检查 |
| 数据可读性 | readable_sources/messages/new_messages | UAT 缺失时统一标为不可读，不写成无事项 |
| 合规边界 | fallback_used/private_history_read/secret_exposed | 任何 fallback 必须有明确授权 |
| 恢复条件 | has_token=true、可读来源>0、用户确认恢复频率 | 三项同时满足才恢复高频提醒 |

### 5.3 提醒降噪区
| 场景 | 看板动作 | 运营目标 |
| --- | --- | --- |
| 权限缺失首次出现 | 一次性说明原因与恢复路径 | 给出明确下一步 |
| 权限缺失重复出现 | 转为静默健康状态 | 避免重复打扰 |
| 用户明确暂停 | 暂停指定 cron job 并验证状态 | 尊重用户控制权 |
| 授权恢复 | 先询问是否恢复提醒及频率 | 防止技术恢复后自动重启高频通知 |

### 5.4 未来事项看板（授权且恢复后填充）
| 表区 | 字段 |
| --- | --- |
| 高优事项队列 | 来源、时间、涉及人、事项、风险、建议动作、负责人、截止时间、状态 |
| 持续跟进队列 | 主题、最新进展、阻塞点、下次跟进时间、闭环状态 |
| 来源覆盖表 | 配置来源、可读状态、最近读取时间、失败原因、是否需要补授权 |
| 例会输入区 | 可带入周会/双周会的主题、需拍板问题、需补充材料 |

## 6. 行动优先级
| 优先级 | 动作 | 状态 | 完成标准 |
| --- | --- | --- | --- |
| P0 | 保持 `张欢-重要沟通雷达` 暂停 | 已核验 | `state=paused` 且 `enabled=false` |
| P0 | 不继续推送该雷达的授权/零数据提醒 | 已生效 | 后续原工作日多时点提醒不再触发 |
| P0 | 不使用 app/bot fallback 替代张欢本人 UAT | 已遵守 | `app_bot_fallback_used=false` |
| P1 | 将权限缺口改为低频健康状态 | 建议 | 只在用户询问、授权状态变化或恢复请求时提示 |
| P1 | 授权恢复后先询问是否恢复提醒和频率 | 建议 | 用户确认后再 resume 指定 job |
| P2 | 在所有监控型任务输出中增加“暂停/恢复提醒”控制项 | 建议 | 降低用户用自然语言打断自动化的成本 |
| P2 | 沉淀零数据提醒降噪规则 | 建议 | 形成“首次说明 + 后续静默 + 显式恢复入口”的标准策略 |

## 7. 权限边界与审计
- 本节点未读取新的飞书私域历史。
- 本节点未展开不可见来源列表。
- 本节点未使用 app/bot fallback。
- 本节点未输出 token、secret、refresh_token 或 OAuth code。
- 本节点未暂停或修改 `张欢-周度工作复盘` 等邻近任务。
- 本节点将“暂停提醒”作为用户体验/VOC 信号处理：当系统没有可行动业务输出时，通知节奏本身就是产品体验的一部分。

## 8. 父流程可消费结论
```json
{
  "node_status": "completed_with_user_pause_verified",
  "final_output": true,
  "user_intent": "pause_recurring_reminder",
  "target_job_id": "6bb4cce497f8",
  "target_job_state": "paused",
  "target_job_enabled": false,
  "unchanged_neighbor_job_id": "81b57c7a99c4",
  "permission_gap": "zhanghuan_user_access_token_missing",
  "private_history_read": false,
  "recommended_next_action": "保持暂停；仅在张欢完成OAuth授权且用户确认恢复后再resume重要沟通雷达。"
}
```

## 9. 关联输入、输出与经验文件
- 上游用户洞察结果：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/voc_insight_node_result_20260511T141656_pause_radar_reminder.md`
- 上游看板执行结果：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/voc_insight_ops_expert_radar_pause_20260511T1416.md`
- 本节点 Markdown：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/ops_dashboard_user_analyst_voc_insight_radar_pause_20260511T142305.md`
- 本节点 JSON：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/ops_dashboard_user_analyst_voc_insight_radar_pause_20260511T142305.json`
- 专家级经验追加：`/Users/frank/.hermes/hermes-agent-official/agent_system/experts/user_analyst/expert_mem/MEMORY.md`
- Skill级经验追加：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/skill_mem/MEMORY.md`
