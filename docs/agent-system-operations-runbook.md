# Hermes Agent-System 上线门禁操作手册

本文档用于把 Agent-System 从“本地 ready”推进到“可判断是否允许升级”。它不负责扩展业务能力，也不自动安装 gstack、迁移密钥或开启生产沉淀开关。

## 当前基线

- Ready routes 固定为 7 条：`artifact_status_flow`、`artifact_delivery_flow`、`doc_publish_flow`、`insight_flow`、`dashboard_flow`、`html_flow`、`dashboard_from_artifact_flow`。
- `report_revision_flow` 必须保持 `non_ready`，直到真实修订执行器和 smoke 证据完成。
- 当前正确状态通常应是 `local_ready_not_operationally_verified`，不是 `production_ready`。
- 只有 `upgrade_allowed=true` 时才允许把 Agent-System 升级视为通过上线门禁。

## 快速检查

```bash
python3 scripts/check_agent_system_readiness.py
python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes
```

状态报告必须输出：

- `overall_status`
- `primary_blocker_status`
- `upgrade_allowed`
- `missing_evidence`
- `next_required_actions`

如果 `upgrade_allowed=false`，不要升级 Gateway 或宣称生产验证完成。

## Gateway 重启

重启前先确认当前配置和日志位置：

```bash
python3 scripts/snapshot_agent_system_production_config.py
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes
```

重启 Gateway 后，观察日志中是否出现平台连接失败、凭证失败、路由拒绝或 pending guard 阻断。日志可以通过 Hermes 自带日志命令或 `~/.hermes/logs/` 查看；不要把 token、key、Authorization header 复制到 issue 或报告里。

## 7 条真实 Feishu Smoke

每条 ready route 都必须由真实 Gateway/Feishu 入口触发一次，并记录对应证据。不要用单测、mock 或本地函数调用冒充真实 smoke。

成功后记录：

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route artifact_status_flow \
  --status ok \
  --platform feishu \
  --run-id <run_id> \
  --artifact-path <artifact_path> \
  --audit-log <audit_log_path> \
  --review-summary <review_summary_path>
```

失败或阻塞必须带标准失败码：

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route dashboard_flow \
  --status blocked \
  --failure-code human_gate_timeout \
  --run-id <run_id>
```

支持的失败码由 `agent_system/failure_taxonomy.py` 维护。记录器只记录事实，不触发任务、不伪造结果、不写 token。

## 运行证据记录

业务执行或失败可以记录到 run evidence：

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route insight_flow \
  --status ok \
  --run-id <run_id> \
  --message-id <message_id> \
  --session-id <session_id> \
  --artifact-path <artifact_path> \
  --audit-log <audit_log_path> \
  --review-summary <review_summary_path>
```

如果状态是 `failed` 或 `blocked`，必须提供 `--failure-code`。所有记录器都会 redacted 敏感字段，但操作者仍不得主动传入完整 token、key 或 Authorization header。

## 沉淀系统验证

生产门禁要求至少 50 条真实 memory events，并覆盖：

- 用户纠正
- 工具失败
- 权限不清
- 项目流程沉淀
- gstack external evidence

检查命令：

```bash
python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes
```

生产默认不自动开启沉淀写入。若要在 staging profile 采样，先显式启用 staging 环境变量，再做人工 review，最后手动写入经验卡。

## gstack 缺失处理

本轮策略是 gstack 作为专家层外部证据来源，保持 `shadow/advisory`。如果 CLI 不存在或不可用，系统必须 fail-closed：记录缺失，不阻断主流程执行，但不得把 gstack 作为 QA 门禁。

检查：

```bash
python3 -m agent_system.gstack_control.ops status
python3 -m agent_system.gstack_control.ops smoke
```

安装或吸收 gstack 前必须单独评估来源、依赖、证据、治理等级。不要让 gstack 直接写 Hermes private memory。

## 配置快照与密钥

生成 redacted 生产配置快照：

```bash
python3 scripts/snapshot_agent_system_production_config.py
```

如果输出 `config_secret_detected=true`，说明配置中存在明文密钥形态。此时：

1. 不要自动迁移，避免破坏当前运行。
2. 将密钥迁移到 `.env`、provider auth store 或凭证池。
3. 重新生成快照。
4. 重新检查状态报告。

只要存在 `config_secret_detected`，`upgrade_allowed` 必须为 `false`。

## 验收报告

生成最新验收报告：

```bash
python3 scripts/write_agent_system_acceptance_report.py --hermes-home /Users/frank/.hermes
```

报告路径：

```text
/Users/frank/.hermes/agent_system/evidence/latest_acceptance_report.json
```

报告只记录当前门禁判断。它不会自动运行 Feishu smoke、安装 gstack、迁移密钥或把状态提升为生产 ready。

## Upgrade Preflight Hard Gate（强制）

**任何 Hermes 升级动作之前，必须先运行 preflight，且 exit code 必须为 0：**

```bash
python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes
echo "preflight exit code: $?"
```

- exit code 0 → `upgrade_allowed=true`，可以继续升级流程
- exit code 1 → `upgrade_allowed=false`，**立即停止，不得执行任何升级动作**
- exit code 2 → 内部错误（status report 构建失败），同样停止

preflight 是只读操作，可以多次运行，不修改任何状态。

查看当前所有 blocker 详情：

```bash
python3 scripts/agent_system_blockers.py --hermes-home /Users/frank/.hermes
```

## 升级判断

升级前必须全部通过：

```bash
# Step 1: Upgrade Preflight（必须 exit 0，否则停止）
python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes

# Step 2: 以下检查全部通过后才继续
python3 scripts/check_agent_system_readiness.py
python3 scripts/smoke_agent_system_business_routes.py
python3 scripts/smoke_agent_system_sedimentation.py --hermes-home /tmp/hermes_sedimentation_smoke_final
python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes
python3 scripts/snapshot_agent_system_production_config.py
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes
python3 scripts/write_agent_system_acceptance_report.py --hermes-home /Users/frank/.hermes
scripts/run_tests.sh tests/agent_system/ -q
git diff --check
```

只有状态报告和验收报告同时显示：

```json
{
  "overall_status": "production_ready",
  "upgrade_allowed": true
}
```

才允许进入升级动作。

## 回滚

当前 fork 分支和 tag 是升级前恢复点。若升级后出现不可接受问题：

1. 停止 Gateway。
2. 切回已推送的 snapshot 分支或 tag。
3. 恢复 `/Users/frank/.hermes` 中对应备份的配置和 evidence 文件。
4. 重新运行状态报告，确认 `upgrade_allowed` 的真实值。

不要用 `git reset --hard` 覆盖用户未确认的本地修改。
