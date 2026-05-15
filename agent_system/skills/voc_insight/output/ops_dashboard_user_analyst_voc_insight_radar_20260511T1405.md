# ops_dashboard 节点｜user_analyst × voc_insight 权限缺口看板

> 生成时间：2026-05-11 14:05:56 CST  
> 数据窗口：2026-05-11 09:45:26 → 2026-05-11 14:00:31 CST  
> 执行身份：`user_analyst`（secondary expert）  
> 调用 Skill：`voc_insight`（用户洞察）  
> 节点：`dashboard_flow:ops_dashboard` / 运营看板

## 0. 节点结论

当前无法形成张欢重要沟通/VOC运营看板：未找到张欢本人 Feishu `user_access_token`，私域历史读取已按硬门禁停止，未使用 app/bot fallback。

## 1. 用户洞察判断

这不是“本轮没有重要事项”的业务结论，而是“数据不可读”的权限缺口结论。由于可读来源为 0、消息数为 0、高优候选为 0，任何关于沟通主题、风险、待办、用户/VOC洞察的判断都不能成立。

## 2. 数据可用性

| 指标 | 当前状态 |
| --- | --- |
| 数据主体 | 张欢 |
| 权限策略 | 必须使用张欢本人 `user_access_token` |
| OAuth 状态 | `has_token=false` / `status=missing` |
| 可读来源 | 0 |
| 消息数 / 新消息数 | 0 / 0 |
| 高优候选 | 0 |
| app/bot fallback | 未使用 |
| 私域历史读取 | 已停止 |

## 3. 看板结构（授权恢复后填充）

### 3.1 摘要卡

| 卡片 | 指标 |
| --- | --- |
| 今日新增高优事项 | 新增 P0/P1 数量、未闭环数量 |
| 重点人员触发 | 重要人员发起/被@/被提及次数 |
| 重点群组活跃 | 高优群新增消息、风险词命中 |
| 行动闭环 | 待办、负责人、截止时间、当前状态 |
| 权限健康 | UAT状态、可读来源数、失败来源数 |

### 3.2 高优事项表

| 来源 | 时间 | 涉及人 | 事项 | 建议动作 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 授权后填充 | 授权后填充 | 授权后填充 | 授权后填充 | 授权后填充 | 授权后填充 |

### 3.3 持续跟进表

| 来源 | 最新时间 | 主题 | 风险/阻塞 | 下一步 | 负责人 |
| --- | --- | --- | --- | --- | --- |
| 授权后填充 | 授权后填充 | 授权后填充 | 授权后填充 | 授权后填充 | 授权后填充 |

## 4. 行动优先级

| 优先级 | 行动 | 目的 |
| --- | --- | --- |
| P0 | 张欢完成 Feishu OAuth 本人授权 | 补齐私域读取前置条件 |
| P1 | 授权完成后重跑重要沟通雷达 | 生成真实高优事项与看板数据 |
| P2 | 建立 UAT 状态巡检 | 避免后续定时任务反复产生零数据 |

授权链接：<https://open.feishu.cn/open-apis/authen/v1/index?app_id=cli_a9f04f3ad279dbcc&redirect_uri=https%3A%2F%2Fopen.feishu.cn&state=rFkXScmpju4axI5RChbVtd1y4zpEnG0i>

授权完成后只需回传最终重定向 URL 或 `code=...`；不要发送任何 token、secret 或 refresh_token。

## 5. 审计检查

| 检查项 | 结果 |
| --- | --- |
| 本地 `voc_insight` Skill 定义已读取 | ✅ |
| `user_analyst` 专家边界已读取 | ✅ |
| 张欢监控配置已读取 | ✅ |
| OAuth 状态已复核 | ✅：`status=missing` |
| 未越权读取私域历史 | ✅ |
| 未输出 token/secret/code | ✅ |
| 未展开不可见来源长列表 | ✅ |

## 6. 关联文件

- 本节点结果 Markdown：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/ops_dashboard_user_analyst_voc_insight_radar_20260511T1405.md`
- 本节点结果 JSON：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/ops_dashboard_user_analyst_voc_insight_radar_20260511T1405.json`
- 上游 `voc_insight` 权限缺口文件：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/voc_insight_node_result_20260511T140143_radar_oauth_block.md`
- ops_expert 看板侧结论：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/voc_insight_ops_expert_radar_20260511T1400.md`
