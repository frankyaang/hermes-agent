# voc_insight 节点结果 — 张欢重要沟通雷达权限缺口

## 1. 节点执行信息
- **task_id**: `dashboard_flow:voc_insight`
- **flow_id / node_id**: `dashboard_flow` / `voc_insight`
- **执行身份**: `user_analyst`（primary expert）
- **调用 Skill**: `voc_insight`
- **执行时间**: 2026-05-11T14:01:43+08:00
- **执行状态**: `completed_with_permission_gap`

## 2. 本次实际完成
1. 读取并校验 Agent System 本地 `voc_insight` Skill 定义、空 pipeline 与私域经验。
2. 按 `feishu-chat-history-audit` / `feishu-work-monitoring-cron` 私域边界，复核张欢本人 OAuth 状态。
3. 读取监控配置 `~/.hermes/data/zhanghuan_work_watch_config.json`，确认数据主体为张欢、监控时区为 Asia/Shanghai、私域策略要求本人 UAT。
4. 运行 `~/.hermes/scripts/feishu_user_oauth.py status --person 张欢 --json`，确认 `has_token=false` / `status=missing`。
5. 未使用 app/bot fallback，未读取任何私域历史消息，未展开暂不可见来源长列表。
6. 生成张欢 OAuth 授权链接，用于下一步补齐本人 user_access_token。

## 3. 用户洞察结论
当前无法形成张欢重要沟通/VOC洞察：未找到张欢本人 `user_access_token`，历史读取已按私域策略停止；下一步需由张欢完成飞书 OAuth 授权后再恢复雷达与用户洞察分析。

## 4. 数据与权限状态
| 项目 | 结果 |
| --- | --- |
| 数据主体 | 张欢 |
| 时间窗口 | 2026-05-11 09:45:26 CST → 2026-05-11 14:00:31 CST |
| 可读来源 | 0 |
| 消息数 / 新消息数 | 0 / 0 |
| 高优候选 | 0 |
| 张欢 user_access_token | missing |
| app/bot fallback | 未使用 |
| 私域历史读取 | 已停止 |

## 5. 下一步
- 请张欢打开授权链接完成 OAuth：<https://open.feishu.cn/open-apis/authen/v1/index?app_id=cli_a9f04f3ad279dbcc&redirect_uri=https%3A%2F%2Fopen.feishu.cn&state=603n0UDpZYteOJX4aravF44YdKsm52Jp>
- 授权完成后，只需回传最终重定向 URL 或 `code=...`；不要发送任何 token、secret 或 refresh_token。

## 6. 审计检查
| 检查项 | 结果 |
| --- | --- |
| local `voc_insight` skill loaded | ✅ |
| pipeline checked | ✅（空 pipeline，按外部方法论与任务上下文执行） |
| private memory checked | ✅ |
| config checked | ✅ |
| OAuth status checked | ✅ |
| 未越权读取私域历史 | ✅ |
| 未输出 token/secret/code | ✅ |
| 未展开不可见来源长列表 | ✅ |

## 7. 关联文件
- 节点结果 Markdown：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/voc_insight_node_result_20260511T140143_radar_oauth_block.md`
- 节点结果 JSON：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/voc_insight_node_result_20260511T140143_radar_oauth_block.json`
