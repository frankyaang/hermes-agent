# ops_dashboard 节点结果 — 张欢重要沟通雷达暂停后的运营看板

## 1. 节点执行信息
- **task_id**: `dashboard_flow:ops_dashboard`
- **flow_id / node_id**: `dashboard_flow` / `ops_dashboard`
- **执行身份**: `ops_expert`（primary expert）
- **调用 Skill**: `ops_dashboard`（运营看板）
- **生成时间**: 2026-05-11T14:23:03+08:00
- **输入材料数**: 1
- **上游依赖**: `voc_insight` 已完成
- **输出类型**: 产品运营报告与 Dashboard 结构
- **执行状态**: `completed_final_dashboard_with_pause_verified`

## 2. 最终节点结论
用户回复 **“暂停重要沟通雷达的提醒”** 是明确的提醒控制 / opt-out 指令。由于上一轮“张欢-重要沟通雷达”处于 Feishu 私域权限缺口状态，继续按工作日多次推送零数据或授权提醒会形成低价值打扰。

本节点将上游用户洞察转成运营看板结论：**保持 `张欢-重要沟通雷达` 暂停，不读取新的私域历史，不使用 app/bot fallback；待张欢本人 OAuth 授权恢复并由用户确认后，再考虑恢复提醒。**

面向用户的一句话：**已确认重要沟通雷达提醒处于暂停状态；周度工作复盘没有被同步暂停。**

## 3. 输入与证据边界
| 项目 | 结论 |
| --- | --- |
| 用户原话 | 暂停重要沟通雷达的提醒 |
| 被引用任务 | `张欢-重要沟通雷达` / `job_id=6bb4cce497f8` |
| 上游洞察 | 权限缺口状态下的重复提醒会变成噪声；应保持暂停 |
| 张欢 UAT 状态 | `has_token=false` / `status=missing` |
| 私域历史读取 | 未读取 |
| app/bot fallback | 未使用 |
| 业务事项判断 | 不能把“未读取”解释为“真实无消息 / 无事项” |

## 4. 当前运营状态看板
| 指标 | 当前值 | 运营含义 |
| --- | --- | --- |
| 目标 job_id | `6bb4cce497f8` | 已定位到用户点名的雷达任务 |
| 任务名称 | 张欢-重要沟通雷达 | 本次唯一操作/核验对象 |
| 调度节奏 | `0 10,14,17,21 * * 1-5` | 原本为工作日多次提醒 |
| enabled | `false` | 不会继续按原节奏触发提醒 |
| state | `paused` | 当前处于暂停状态 |
| paused_at | `2026-05-11T14:16:39.821372+08:00` | 暂停动作已生效 |
| last_status | `ok` | 最近一次 cron 运行本身完成，但业务结果是权限缺口 |
| 相关周报任务 | `81b57c7a99c4` / `scheduled` / `enabled=true` | 未被本次暂停扩大影响 |
| 张欢 UAT | `missing` | 雷达业务数据仍不可读 |
| token/secret/code 暴露 | 0 | 本节点未输出敏感凭据 |

## 5. Dashboard 信息架构
### 5.1 顶部状态卡
- **雷达状态**: Paused
- **提醒策略**: 已暂停高频提醒
- **权限状态**: 张欢本人 UAT 缺失
- **恢复条件**: UAT 恢复 + 用户确认恢复提醒

### 5.2 数据就绪区
| 组件 | 字段 |
| --- | --- |
| 权限状态 | `has_token`、`status`、授权主体、检查时间 |
| 可读来源 | 可读来源数、不可读来源数、不可读原因 |
| 采集结果 | 读取消息数、新消息数、高优候选数 |
| 合规标识 | 是否使用 fallback、是否输出敏感凭据、是否越权读取 |

当前值应显示为：UAT missing、可读私域来源 0、消息未读取、fallback 未使用。

### 5.3 提醒控制区
| 组件 | 字段 |
| --- | --- |
| 任务状态 | job_id、name、enabled、state、paused_at、next_run_at 元数据 |
| 影响范围 | 被暂停任务、未受影响任务 |
| 用户意图 | pause_recurring_reminder / opt_out |
| 操作记录 | list → pause/verify（本轮为 verify-only，因为状态已暂停） |

### 5.4 恢复路径区
1. 张欢本人完成 Feishu OAuth 授权，状态变为 `has_token=true`。
2. 重新跑一次只读健康检查，确认可读来源 > 0。
3. 向用户确认是否恢复“重要沟通雷达”，并确认频率。
4. 通过 cron resume 恢复目标 job，并再次 list 验证 `state=scheduled` / `enabled=true`。

### 5.5 审计区
保留以下审计卡：未读取私域历史、未用 app/bot fallback、未扩大暂停范围、未泄露 token/secret/code、结果文件路径。

## 6. 行动优先级
| 优先级 | 行动 | 当前状态 | 完成标准 |
| --- | --- | --- | --- |
| P0 | 保持 `张欢-重要沟通雷达` 暂停 | 已完成/已验证 | cronjob list 显示 `state=paused` / `enabled=false` |
| P0 | 停止该雷达的零数据/授权缺口高频提醒 | 已完成/已验证 | 原工作日多次提醒不再触发 |
| P0 | 不用 app/bot fallback 替代张欢本人 UAT | 已遵守 | 不读取不在授权范围内的私域历史 |
| P1 | 将权限缺口转为低频状态型待办 | 建议 | 仅在用户询问、授权变化或例会健康检查时提示 |
| P1 | 授权恢复后先询问再恢复提醒 | 建议 | 不因 token 恢复自动恢复高频通知 |
| P2 | 在提醒产品中加入“暂停/恢复/降频”入口 | 建议 | 后续用户不必用自然语言打断 cron 任务 |
| P2 | 区分雷达与周报的生命周期控制 | 已验证/建议固化 | 本次仅暂停雷达，周报仍 scheduled |

## 7. 监测与例会看板建议
- **日常**: 暂停期间不做高频雷达推送。
- **状态健康检查**: 可在周度复盘或用户主动询问时展示一次权限状态，而不是每日多次提醒。
- **恢复前检查**: 只检查授权与可读来源，不读取或总结未授权私域内容。
- **例会呈现**: 将本项放入“自动化提醒生命周期”看板，状态为 `Paused by user`，阻塞项为 `张欢 UAT missing`，下一动作是 `等待授权或用户恢复指令`。

## 8. 关联输入与输出文件
- 上游 `voc_insight` 暂停洞察：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/voc_insight_node_result_20260511T141656_pause_radar_reminder.md`
- 上轮 `ops_dashboard` 暂停执行产物：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/voc_insight_ops_expert_radar_pause_20260511T1416.md`
- 上轮权限缺口看板：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/ops_dashboard_node_result_20260511T140605_radar_oauth_block.md`
- 本节点 Markdown：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/ops_dashboard_node_result_20260511T142303_radar_pause_final.md`
- 本节点 JSON：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/ops_dashboard_node_result_20260511T142303_radar_pause_final.json`

## 9. 审计检查
| 检查项 | 结果 |
| --- | --- |
| 本地 `ops_dashboard` Skill 已读取 | ✅ |
| 上游 `voc_insight` 结果已复核 | ✅ |
| cronjob 最新状态已核验 | ✅ |
| 目标雷达任务已暂停 | ✅ |
| 相邻周报任务未被暂停 | ✅ |
| 张欢 UAT 状态已复核 | ✅ |
| 未读取新的飞书私域历史 | ✅ |
| 未使用 app/bot fallback | ✅ |
| 未输出 token/secret/code | ✅ |
| Markdown 与 JSON 结果已写入 | ✅ |
