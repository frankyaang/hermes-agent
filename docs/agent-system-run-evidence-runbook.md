# Hermes Agent-System — Run Evidence 操作手册

> **Status**: 参考文档  
> **Generated**: 2026-05-20  
> **当前 run_evidence 数量**: 0  
> **用途**: 记录真实 Gateway/Feishu 任务执行证据，不得伪造

---

## 概述

Run evidence 是比 Gateway smoke 更详细的执行记录。每条 run evidence 包括：

- `run_id` — 唯一任务标识
- `message_id` — Feishu 消息 ID
- `session_id` — Hermes session 标识
- `artifact_path` — 输出产物路径
- `audit_log` — 质量门禁日志路径
- `review_summary` — human gate 审核摘要路径
- `human_gate` — human gate 决策记录
- `memory_event_ids` — 本次任务产生的 MemoryEvent ID 列表
- `staging_ids` — 进入 staging 的记录 ID 列表

Run evidence count 是 `upgrade_allowed=true` 的必要条件之一。

---

## run_id 如何生成或定位

### 方式 1：使用 Feishu Gateway 分配的 task_id

Feishu Gateway 在任务分发时会生成唯一 `task_id`。查找位置：

- Gateway 日志：`~/.hermes/logs/gateway.log`（或平台指定路径）
- Feishu webhook 回调中的 `task_id` 字段
- Hermes 任务分发器输出中的 `run_id` 字段

### 方式 2：手动生成（仅用于 drill/smoke）

```bash
# 生成一个时间戳+序号格式的 run_id
date +%Y%m%d-%H%M%S
# 输出示例：20260520-143022
# 建议格式：<route_short>-<date>-<seq>
# 例如：insight-20260520-001
```

> **重要**：同一个 run_id 必须贯穿从触发到记录的整个链路。不同任务不能共用 run_id。

---

## message_id 如何绑定

`message_id` 是 Feishu 消息的唯一标识，用于将 Gateway smoke 和 run evidence 与具体 Feishu 消息关联。

获取方式：
- Feishu Bot API 回调事件中的 `event.message.message_id` 字段
- Feishu 开放平台消息列表 API 返回的 `msg_id`

格式示例：`om_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

如果使用其他平台（非 Feishu），用平台对应的消息 ID 字段。

---

## session_id 如何绑定

`session_id` 是 Hermes 内部 session 标识，用于关联 MemoryEvent 和任务执行。

获取方式：
- Hermes run_agent.py 启动时生成的 `session_id`（UUID 格式）
- `~/.hermes/memory_events/events.jsonl` 中对应任务的 `session_id` 字段
- Hermes 日志中的 `session_id=<uuid>` 行

---

## artifact、audit log、review summary 如何定位

| 文件 | 典型路径 | 说明 |
|------|---------|------|
| artifact | `~/.hermes/smoke_artifacts/<skill>.md` | 技能输出文件 |
| artifact | `<task_work_dir>/output/<skill>.md` | 任务工作目录 |
| audit_log | `<task_work_dir>/audit/audit.log` | 核查日志 |
| review_summary | `<task_work_dir>/review/review_summary.md` | human gate 审核摘要 |

**注意**：路径必须是真实存在的文件。不要使用占位符路径。

---

## 失败时如何选择 failure_code

| 情形 | failure_code |
|------|-------------|
| Feishu 消息未触发正确路由 | `trigger_miss` |
| 路由判断错误（指向错误 route） | `route_misclassified` |
| 凭证/API key 失效 | `credential_missing` |
| 模型/提供商限流 | `provider_rate_limited` |
| 模型/提供商找不到 | `provider_not_found` |
| artifact 路径无法解析 | `artifact_unresolved` |
| human gate 超时 | `human_gate_timeout` |
| human gate 被用户拒绝 | `human_gate_rejected` |
| delegate_task 输出不符合合同 | `delegate_contract_violation` |
| memory ACL 拒绝写入 | `memory_acl_denied` |
| Gateway 交付失败 | `gateway_delivery_failed` |
| 成本预算超限 | `cost_budget_exceeded` |
| gstack CLI 不可用 | `gstack_cli_missing` |
| 外部依赖不可用 | `external_dependency_unavailable` |

---

## 如何检查 run_evidence.count

```bash
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('run_evidence_count:', d['run_evidence']['count'])"

# 直接查看文件
wc -l /Users/frank/.hermes/agent_system/evidence/run_evidence.jsonl 2>/dev/null || echo "文件不存在"
```

---

## 记录模板

### 成功任务

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route <route> \
  --status ok \
  --run-id <run_id> \
  --message-id <message_id> \
  --session-id <session_id> \
  --artifact-path <artifact_path> \
  --audit-log <audit_log_path> \
  --review-summary <review_summary_path>
```

### 失败任务

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route <route> \
  --status failed \
  --failure-code <failure_code> \
  --run-id <run_id> \
  --message-id <message_id> \
  --session-id <session_id>
```

### 被阻断任务（human gate / 依赖缺失）

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route <route> \
  --status blocked \
  --failure-code <failure_code> \
  --run-id <run_id> \
  --message-id <message_id> \
  --session-id <session_id>
```

### 包含 human gate 决策的任务

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route <route> \
  --status ok \
  --run-id <run_id> \
  --message-id <message_id> \
  --session-id <session_id> \
  --artifact-path <artifact_path> \
  --audit-log <audit_log_path> \
  --review-summary <review_summary_path> \
  --human-gate-json '{"decision":"approved","approver":"user","timestamp":"2026-05-20T14:30:00Z"}'
```

### 包含 MemoryEvent 和 staging 关联的任务

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route <route> \
  --status ok \
  --run-id <run_id> \
  --message-id <message_id> \
  --session-id <session_id> \
  --artifact-path <artifact_path> \
  --memory-event-id <event_id_1> \
  --memory-event-id <event_id_2> \
  --staging-id <staging_id_1>
```

---

## 验证记录是否成功

```bash
# 查看最新写入的 run evidence
tail -1 /Users/frank/.hermes/agent_system/evidence/run_evidence.jsonl | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('route:', d.get('route')); \
  print('status:', d.get('status')); \
  print('run_id:', d.get('run_id'))"

# 检查总数
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('run_evidence_count:', d['run_evidence']['count'])"
```

---

## 禁止事项

- ❌ 不得在 status=ok 的记录中使用占位符路径（`<artifact_path>` 等）
- ❌ 不得对同一个真实任务记录多次（幂等检查：run_id 应唯一）
- ❌ 不得把本地 smoke（非 Feishu 触发）当成 `platform=feishu` 记录
- ❌ failure_code 必须使用规定的 taxonomy 值，不得使用自定义字符串
- ❌ 不得打印 token、key、Authorization header（这些字段会被 redact，无需手动处理）
