# dashboard_flow 过程汇报 — 张欢重要沟通雷达权限缺口

> **流程**: `dashboard_flow`（产品运营看板流程）  
> **Run ID**: `Run_dashboard_flow_20260511T060034`  
> **汇报节点**: `briefing`（过程汇报）  
> **执行身份**: `system`  
> **生成时间**: 2026-05-11 14:09 CST  
> **数据窗口**: 2026-05-11 09:45:26 CST → 2026-05-11 14:00:31 CST

---

## 一、流程执行概览

| 项目 | 内容 |
|---|---|
| 流程名称 | dashboard_flow — 张欢重要沟通雷达 |
| 执行链路 | `voc_insight` → `ops_dashboard` → **`briefing`（本节点）** |
| 上游节点状态 | `voc_insight` 已完成；`ops_dashboard` 已完成 |
| 核心结论 | 张欢本人 Feishu `user_access_token` 缺失，私域历史读取按硬门禁停止 |
| 权限边界 | 未使用 app/bot fallback；未读取、推断或总结不可见私域消息 |
| 数据结果 | 可读来源 0；消息数 0；新消息数 0；高优候选 0 |
| 业务判断 | 这不是“本轮无重要事项”，而是“数据不可读，无法判定” |

---

## 二、上游节点摘要

### 2.1 `voc_insight`（用户洞察）

| 维度 | user_analyst（主专家） | ops_expert（次专家） |
|---|---|---|
| 调用 Skill | `voc_insight` | `ops_dashboard`（动态覆盖） |
| 状态 | completed | completed |
| API 调用 | 13 | 9 |
| 执行时长 | 241.78s | 148.25s |
| Token | input 935,653 / output 9,156 | input 601,654 / output 5,370 |
| 关键结论 | 未找到张欢本人 `user_access_token`，已停止私域历史读取 | 同步确认 UAT 缺失，生成授权恢复路径 |
| 产出 | 纯文本结论；权限缺口节点文件 | `voc_insight_ops_expert_radar_20260511T1400.md` |

**动态覆盖说明**：`ops_expert` 不直接加载 `voc_insight`，按专家技能范围规则动态替换为 `ops_dashboard`，覆盖成功。

### 2.2 `ops_dashboard`（运营看板）

| 维度 | ops_expert（主专家） | user_analyst（次专家） |
|---|---|---|
| 调用 Skill | `ops_dashboard` | `voc_insight`（动态覆盖） |
| 状态 | completed | completed |
| API 调用 | 16 | 13 |
| 执行时长 | 239.73s | 250.91s |
| Token | input 1,161,827 / output 7,701 | input 1,074,211 / output 8,745 |
| 关键结论 | 当前无法生成实质性运营事项看板；需先完成张欢本人 OAuth | 零数据代表权限缺口，不代表真实无新增 |
| 产出 | `ops_dashboard_node_result_20260511T140605_radar_oauth_block.md/json` | `ops_dashboard_user_analyst_voc_insight_radar_20260511T1405.md/json` |

**动态覆盖说明**：`user_analyst` 不直接加载 `ops_dashboard`，按专家技能范围规则动态替换为 `voc_insight`，覆盖成功。

---

## 三、过程质量评估

| 维度 | 评估 | 说明 |
|---|---:|---|
| 权限合规 | 95/100 | 全链路遵守张欢本人 UAT 硬门禁，未使用 app/bot fallback |
| 数据充分性 | 0/100 | 可读来源为 0，无法支撑任何沟通/VOC/运营事项判断 |
| 洞察深度 | N/A | 无可读数据，不能评价业务洞察深度 |
| 多专家协同 | 90/100 | 两个节点、四个专家调用均给出一致的权限缺口判断和恢复路径 |
| 产出完整性 | 90/100 | 已形成权限缺口结论、用户可见一句话、结构化节点结果与本过程汇报 |
| 审计透明度 | 90/100 | 记录了数据窗口、权限边界、动态覆盖、文件路径和下一步 |

---

## 四、异常与边界

- **无业务数据异常**：本轮没有读取到消息，是因为张欢本人 `user_access_token` 缺失，并不表示真实没有重要沟通。
- **无越权读取**：已按私域策略停止历史读取；没有使用 app/tenant/bot 可见范围替代个人授权。
- **轻微工具适配问题**：本节点复核时发现 `feishu_user_oauth.py status` 不支持 `--json` 参数；已改用 `~/.hermes/scripts/feishu_user_oauth.py status --person 张欢` 完成核验，返回 `has_token=false` / `status=missing`。
- **不展开不可见来源**：用户可见输出只保留授权缺口与下一步，不输出 14 个暂不可见来源长列表。

---

## 五、用户可见输出建议

当前未找到张欢本人 Feishu `user_access_token`，私域历史读取已停止；请张欢打开 OAuth 授权链接完成本人授权后，下轮雷达再恢复读取：https://open.feishu.cn/open-apis/authen/v1/index?app_id=cli_a9f04f3ad279dbcc&redirect_uri=https%3A%2F%2Fopen.feishu.cn&state=mPwKHFjj_SBAM75VJraAsgKJPvNDntLm

---

## 六、产出清单

| 序号 | 文件路径 | 说明 |
|---|---|---|
| 1 | `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/voc_insight_node_result_20260511T140143_radar_oauth_block.md` | `voc_insight` 主专家节点结果 |
| 2 | `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/voc_insight_ops_expert_radar_20260511T1400.md` | `voc_insight` 次专家运营结论 |
| 3 | `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/ops_dashboard_node_result_20260511T140605_radar_oauth_block.md` | `ops_dashboard` 主专家节点结果 |
| 4 | `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/voc_insight/output/ops_dashboard_user_analyst_voc_insight_radar_20260511T1405.md` | `ops_dashboard` 次专家节点结果 |
| 5 | `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/dashboard_flow_briefing_20260511T1409_radar_oauth_block.md` | 本过程汇报 |

---

## 七、审计记录

| 项目 | 内容 |
|---|---|
| 任务 ID | `dashboard_flow:briefing` |
| Skill | `briefing`（过程汇报） |
| 输入类型 | 产品运营报告与 Dashboard 结构 |
| 输出类型 | 过程汇报（非最终输出节点） |
| 依赖节点 | `ops_dashboard` 已完成 |
| 人工审核 | 不需要；审核通道 unavailable |
| 当前 OAuth 状态 | `has_token=false` / `status=missing` |
| 建议下一步 | 张欢完成 Feishu OAuth 后重跑重要沟通雷达 |

---

*本汇报由 briefing Skill 基于上游节点输出与本节点权限复核自动生成。*
