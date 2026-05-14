# ops_dashboard 节点结果 — 张欢重要沟通雷达运营看板

## 1. 节点执行信息
- **task_id**: `dashboard_flow:ops_dashboard`
- **flow_id / node_id**: `dashboard_flow` / `ops_dashboard`
- **执行身份**: `ops_expert`（primary expert）
- **调用 Skill**: `ops_dashboard`（运营看板）
- **生成时间**: 2026-05-11 14:05:55 CST
- **数据窗口**: 2026-05-11 09:45:26 CST → 2026-05-11 14:00:31 CST
- **执行状态**: `completed_with_permission_gap`

## 2. 核心结论
当前无法生成实质性运营事项看板：未找到张欢本人 Feishu `user_access_token`，按私域硬门禁已停止历史读取；本轮未使用 app/bot fallback，未读取任何私域消息，因此没有可判定的新增高优事项。

## 3. 用户可见输出（一句话）
当前未找到张欢本人 Feishu `user_access_token`，私域历史读取已停止；请张欢打开 OAuth 授权链接完成本人授权后，下轮雷达再恢复读取：https://open.feishu.cn/open-apis/authen/v1/index?app_id=cli_a9f04f3ad279dbcc&redirect_uri=https%3A%2F%2Fopen.feishu.cn&state=ZDRG1Zh64PzbWiIf9MIoycjnRudsr9WU

## 4. 关键指标表
| 指标 | 当前值 | 判断 |
| --- | ---: | --- |
| 张欢 user_access_token | missing | P0 阻塞 |
| 可读来源 | 0 | 不具备看板数据底座 |
| 配置监控来源数 | 14 | 全部因 UAT 缺失未纳入读取 |
| 消息数 | 0 | 未读取，不代表真实无消息 |
| 新消息数 | 0 | 未读取，不代表真实无新增 |
| 高优候选 | 0 | 无可判定事项 |
| app/bot fallback | 未使用 | 符合私域边界 |
| token/secret/code 暴露 | 0 | 合规 |

## 5. Dashboard 信息架构（权限恢复后填充）
1. **授权状态卡**：UAT 状态、最后成功读取时间、可读来源数、阻塞原因。
2. **重要沟通队列**：需要立即处理、需要持续跟进、低优记录归档。
3. **来源覆盖看板**：自我记录/重点群/纪要助手的读取状态、活跃度、覆盖缺口。
4. **事项闭环表**：来源、时间、涉及人、事项、建议动作、负责人、截止时间、当前状态。
5. **运营风险区**：延期、阻塞、跨团队依赖、决策未闭环、用户/VOC 风险信号。
6. **例会输入区**：本轮可带入周会/双周会的主题、需拍板问题、需补充信息源。

## 6. 行动优先级
| 优先级 | 动作 | 负责人/对象 | 完成标准 |
| --- | --- | --- | --- |
| P0 | 完成张欢本人飞书 OAuth 授权 | 张欢 | `~/.hermes/scripts/feishu_user_oauth.py status --person 张欢` 返回 `has_token=true` |
| P0 | 授权后重新运行重要沟通雷达 | 香农AI助手 | 可读来源 > 0，并产出新增高优事项判断 |
| P1 | 保留当前 14 个来源配置并做读取健康检查 | 香农AI助手 | 每轮输出来源覆盖数和阻塞原因摘要 |
| P2 | 将高优事项沉淀为周会/双周会看板字段 | ops_dashboard | 形成固定字段：来源/时间/涉及人/事项/建议动作/状态 |

## 7. 权限边界与审计
- 数据主体：张欢。
- OAuth 状态命令：`~/.hermes/scripts/feishu_user_oauth.py status --person 张欢` 返回 `has_token=false`、`status=missing`。
- 本轮没有使用 app/tenant/bot-visible fallback。
- 本轮没有读取、推断或总结不可见飞书私域消息。
- 未输出任何 token、secret、refresh_token 或授权 code。
- 未展开不可见来源长列表；仅保留数量级状态用于运营看板判断。

## 8. 关联输入与输出
- 上游节点结果：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/voc_insight_node_result_20260511T140143_radar_oauth_block.md`
- 历史零数据看板模板：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/ops_dashboard_20260511_张欢重要沟通雷达.md`
- 本节点结果 Markdown：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/ops_dashboard_node_result_20260511T140605_radar_oauth_block.md`
- 本节点结构化 JSON：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/ops_dashboard_node_result_20260511T140605_radar_oauth_block.json`
