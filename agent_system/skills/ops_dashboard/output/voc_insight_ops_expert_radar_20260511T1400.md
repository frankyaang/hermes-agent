# voc_insight 节点｜ops_expert × ops_dashboard 结论

> 生成时间：2026-05-11 14:01:49 CST  
> 数据窗口：2026-05-11 09:45:26 → 2026-05-11 14:00:31 CST  
> 执行身份：ops_expert  
> 调用 Skill：ops_dashboard（运营看板）  
> 节点：dashboard_flow:voc_insight / 用户洞察

## 节点结论

本轮重要沟通雷达未读取任何私域历史消息：张欢本人 `user_access_token` 缺失（status=`missing`），按私域硬门禁策略已停止读取，不使用 app/bot fallback。

## 用户可见输出

当前未找到张欢本人 Feishu `user_access_token`，私域历史读取已停止；请张欢打开 OAuth 授权链接完成本人授权后，下轮雷达再恢复读取：https://open.feishu.cn/open-apis/authen/v1/index?app_id=cli_a9f04f3ad279dbcc&redirect_uri=https%3A%2F%2Fopen.feishu.cn&state=awF8x6KhqXc2w8PvlDQQXcFPeSK1k9z0

## 证据与校验

- 预运行脚本输出：消息数 0；新消息数 0；高优候选 0；可读来源 0。
- OAuth 状态命令：`~/.hermes/scripts/feishu_user_oauth.py status --person 张欢` 返回 `has_token=false`、`status=missing`。
- 配置文件：`/Users/frank/.hermes/data/zhanghuan_work_watch_config.json` 已包含张欢 `open_id`，可生成授权链接。
- 授权链接生成命令：`~/.hermes/scripts/feishu_user_oauth.py auth-url --name 张欢 --open-id ou_41f5b653687f6b86e309f537f5aa4a83 --json`。

## 文件

- 本节点结论：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/voc_insight_ops_expert_radar_20260511T1400.md`
- 历史零数据看板：`/Users/frank/.hermes/hermes-agent-official/agent_system/skills/ops_dashboard/output/ops_dashboard_20260511_张欢重要沟通雷达.md`
