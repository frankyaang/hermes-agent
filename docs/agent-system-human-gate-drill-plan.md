# Hermes Agent-System — Human Gate Drill 计划

> **Status**: 执行计划  
> **Generated**: 2026-05-20  
> **用途**: 在真实 Feishu/Gateway 环境中演练 human gate 场景，产出 run evidence  
> **禁止**: 不得伪造 drill 结果；每个场景必须有真实 Feishu 消息触发

---

## 概述

Human gate 是 Hermes Agent-System 的关键安全机制。以下场景必须在真实环境中演练并记录证据，才能让 human_gate_not_drilled blocker 消除。

---

## 场景 1：Approve（正常审批通过）

### 触发方式

1. 向 Feishu Bot 发送触发 `insight_flow` 或 `dashboard_flow` 的消息
2. Hermes 产出洞察结论或运营看板草稿
3. 用户在 Feishu 中明确回复"确认" / "通过" / "发布"

### 预期行为

- Hermes 继续执行，产出最终 artifact
- human gate 记录 `decision=approved`
- artifact 写入指定路径

### 证据记录命令

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route insight_flow \
  --status ok \
  --run-id drill-approve-<date>-001 \
  --message-id <feishu_message_id> \
  --session-id <hermes_session_id> \
  --artifact-path <voc_insight.md路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径> \
  --human-gate-json '{"decision":"approved","approver":"user","scenario":"drill_approve"}'
```

### 通过标准

- `status=ok`
- `human_gate.decision=approved`
- artifact 文件真实存在
- run_evidence.count 增加 1

---

## 场景 2：Deny（用户拒绝）

### 触发方式

1. 向 Feishu Bot 发送触发 `dashboard_flow` 的消息
2. Hermes 产出运营看板草稿
3. 用户回复"不对" / "拒绝" / "取消"

### 预期行为

- Hermes 停止当前 route 执行
- 不发布任何 artifact 到外部目标
- 记录 `failure_code=human_gate_rejected`

### 证据记录命令

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route dashboard_flow \
  --status blocked \
  --failure-code human_gate_rejected \
  --run-id drill-deny-<date>-001 \
  --message-id <feishu_message_id> \
  --session-id <hermes_session_id> \
  --human-gate-json '{"decision":"rejected","approver":"user","scenario":"drill_deny"}'
```

### 通过标准

- `status=blocked`
- `failure_code=human_gate_rejected`
- 无 artifact 被发布到外部目标

---

## 场景 3：Timeout（human gate 超时）

### 触发方式

1. 触发需要 human gate 的 route（如 `doc_publish_flow`）
2. **不回复** Feishu 中的确认请求，等待超时
3. Hermes 自动超时处理

### 预期行为

- Hermes 在 timeout 阈值后停止等待
- 记录 `failure_code=human_gate_timeout`
- 不执行发布操作

### 证据记录命令

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route doc_publish_flow \
  --status blocked \
  --failure-code human_gate_timeout \
  --run-id drill-timeout-<date>-001 \
  --message-id <feishu_message_id> \
  --session-id <hermes_session_id> \
  --human-gate-json '{"decision":"timeout","scenario":"drill_timeout","waited_seconds":300}'
```

### 通过标准

- `status=blocked`
- `failure_code=human_gate_timeout`
- Hermes 未在超时后继续执行

---

## 场景 4：Pending Guard（阻断挂起）

### 触发方式

1. 触发 `dashboard_from_artifact_flow`
2. 提供一个状态模糊的 artifact（如来源不明的文件路径）
3. Hermes 检测到 artifact 状态未确认，进入 pending guard

### 预期行为

- Hermes 不继续执行 ops_dashboard
- 向 Feishu 返回 pending 状态提示
- 等待用户提供更多信息

### 证据记录命令

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route dashboard_from_artifact_flow \
  --status blocked \
  --failure-code artifact_unresolved \
  --run-id drill-pending-<date>-001 \
  --message-id <feishu_message_id> \
  --session-id <hermes_session_id> \
  --human-gate-json '{"decision":"pending","scenario":"drill_pending_guard","reason":"artifact_source_unconfirmed"}'
```

### 通过标准

- `status=blocked`
- `failure_code=artifact_unresolved`
- Hermes 不执行后续 ops_dashboard 步骤

---

## 场景 5：`dashboard_from_artifact_flow` Artifact 来源确认

### 触发方式

1. 向 Feishu Bot 发送含多个候选 artifact 路径的消息
2. Hermes 要求确认正确的 artifact 版本和来源
3. 用户明确指定使用哪个文件，并确认版本

### 预期行为

- Hermes 等待用户确认 artifact 版本
- 用户确认后，使用指定文件执行 ops_dashboard
- 记录 `artifact_confirmed=true`

### 证据记录命令

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route dashboard_from_artifact_flow \
  --status ok \
  --run-id drill-artifact-confirm-<date>-001 \
  --message-id <feishu_message_id> \
  --session-id <hermes_session_id> \
  --artifact-path <confirmed_artifact路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径> \
  --human-gate-json '{"decision":"approved","artifact_confirmed":true,"confirmed_version":"v1.2","scenario":"drill_artifact_confirm"}'
```

### 通过标准

- `status=ok`
- `human_gate.artifact_confirmed=true`
- artifact_path 为用户明确确认的文件

---

## 场景 6：多 run_id 绑定（复杂场景）

### 触发方式

1. 同一 Feishu 会话中触发多个任务（如先 `insight_flow` 再 `dashboard_flow`）
2. 每个任务产生独立的 run_id

### 要求

- 每个 run_id 独立绑定到各自的 message_id 和 session_id
- 不允许不同任务共用同一个 run_id

### 证据记录命令

```bash
# 第一个任务
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route insight_flow \
  --status ok \
  --run-id drill-multi-insight-<date>-001 \
  --message-id <message_id_1> \
  --session-id <session_id_1> \
  --artifact-path <voc_insight.md路径>

# 第二个任务（独立 run_id）
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route dashboard_flow \
  --status ok \
  --run-id drill-multi-dashboard-<date>-001 \
  --message-id <message_id_2> \
  --session-id <session_id_1> \
  --artifact-path <ops_dashboard.md路径>
```

### 通过标准

- 两条 run evidence 有不同 run_id
- 两条记录都绑定了正确的 message_id
- run_evidence.count 增加 2

---

## 所有场景完成后验证

```bash
# 检查 run evidence 总数
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('run_evidence_count:', d['run_evidence']['count'])"

# 查看最近的 run evidence 记录
tail -6 /Users/frank/.hermes/agent_system/evidence/run_evidence.jsonl 2>/dev/null | \
  python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    print(f\"  route={d.get('route')} status={d.get('status')} human_gate_decision={d.get('human_gate',{}).get('decision','N/A')}\")"

# 运行完整 preflight
python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes
```

---

## 禁止事项

- ❌ 不得伪造 drill 结果（drill 记录必须来自真实 Feishu 触发）
- ❌ 不得在同一条 run evidence 中混合多个 route 的结果
- ❌ `status=ok` 的 drill 记录必须有真实 artifact_path（不是占位符）
- ❌ 不得把 drill 记录当成真实 smoke（两者需分开管理，drill 在 human_gate.scenario 字段中标注）
- ❌ 不得在 human_gate_json 中包含任何 token、key 或 secret 值
