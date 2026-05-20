# Hermes Agent-System — Feishu/Gateway Smoke 执行手册

> **Status**: 执行前阅读  
> **Generated**: 2026-05-20  
> **Gateway smoke 进度**: 0/7 routes  
> **禁止**: 不得伪造 smoke。所有 `status=ok` 记录必须来自真实 Feishu/Gateway 执行。

---

## 前提条件

执行任何 route smoke 前，确认：

1. Gateway/Feishu 连接正常
2. Hermes agent 已部署且 ready
3. 当前 `upgrade_allowed=false`（smoke 是让它变 true 的必要条件之一）

```bash
# 确认 agent 和配置正常
python3 scripts/check_agent_system_readiness.py
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes
```

---

## Run ID 规范

每次 smoke 必须生成并记录一个唯一 `run_id`。建议格式：

```
smoke-<route_short>-<date>-<seq>
# 例如：
smoke-artifact-status-20260520-001
smoke-insight-flow-20260520-001
```

同一个 `run_id` 贯穿：Gateway smoke 记录 + run_evidence 记录 + artifact + audit log + review summary。

---

## Route 1: `artifact_status_flow`

**功能**: 查询 artifact 状态（本地文件路径或 task_id 解析）

### Feishu 触发消息样例

```
请问这个 artifact 的当前状态是什么？[artifact_path 或 task_id]
# 或明确：
检查 artifact /Users/frank/.hermes/smoke_artifacts/voc_insight.md 的状态
```

### 预期 route

`artifact_status_flow` via `artifact_resolver` + `artifact_status`

### 预期 artifact

包含 artifact 存在/不存在/状态字段的结构化输出文件

### 需要 human gate

**否**（executor_type=system，不涉及写入操作）

### 成功记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route artifact_status_flow \
  --status ok \
  --platform feishu \
  --run-id smoke-artifact-status-20260520-001 \
  --artifact-path <artifact输出路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径>
```

### 失败记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route artifact_status_flow \
  --status blocked \
  --failure-code artifact_unresolved \
  --run-id smoke-artifact-status-20260520-001
```

### 推荐 failure_code

| 情形 | failure_code |
|------|-------------|
| artifact path 无法解析 | `artifact_unresolved` |
| Gateway 未收到消息 | `trigger_miss` |
| 路由到错误 route | `route_misclassified` |
| 凭证问题 | `credential_missing` |

### 验证命令

```bash
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('completed_routes:', d['gateway_smoke']['completed_routes'])"
```

---

## Route 2: `artifact_delivery_flow`

**功能**: 交付 artifact 到指定目标（Feishu、本地、发布）

### Feishu 触发消息样例

```
请把这个报告发送给我：[artifact_path]
# 或：
交付 artifact /path/to/ops_dashboard.md 到 Feishu
```

### 预期 route

`artifact_delivery_flow` via `artifact_resolver` + `artifact_delivery`

### 预期 artifact

交付确认记录 + 发送收据

### 需要 human gate

**是**（写入/发布操作需确认目标和版本）

### 成功记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route artifact_delivery_flow \
  --status ok \
  --platform feishu \
  --run-id smoke-artifact-delivery-20260520-001 \
  --artifact-path <交付确认文件路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径>
```

### 失败记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route artifact_delivery_flow \
  --status blocked \
  --failure-code gateway_delivery_failed \
  --run-id smoke-artifact-delivery-20260520-001
```

### 推荐 failure_code

| 情形 | failure_code |
|------|-------------|
| 交付目标不可达 | `gateway_delivery_failed` |
| human gate 超时 | `human_gate_timeout` |
| human gate 拒绝 | `human_gate_rejected` |
| artifact 路径不存在 | `artifact_unresolved` |

---

## Route 3: `doc_publish_flow`

**功能**: 发布文档到指定目标（Feishu 文档、本地目录）

### Feishu 触发消息样例

```
请发布这份分析报告：[artifact_path]
把这个 markdown 发布为 Feishu 文档
```

### 预期 route

`doc_publish_flow` via `artifact_resolver` + `doc_publish`

### 预期 artifact

发布确认 + 目标 URL 或文件路径

### 需要 human gate

**是**（发布到外部目标涉及写操作）

### 成功记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route doc_publish_flow \
  --status ok \
  --platform feishu \
  --run-id smoke-doc-publish-20260520-001 \
  --artifact-path <发布确认文件路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径>
```

### 失败记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route doc_publish_flow \
  --status blocked \
  --failure-code gateway_delivery_failed \
  --run-id smoke-doc-publish-20260520-001
```

---

## Route 4: `insight_flow`

**功能**: 消费 VOC/评论/竞品/质量反馈，输出用户洞察结论

### Feishu 触发消息样例

```
请分析这批用户反馈并给出洞察结论：[VOC 数据文件路径或内联内容]
# 或上传 VOC 文件并发消息：
帮我分析一下这份用户评论数据
```

### 预期 route

`insight_flow` via `voc_insight` (delegate_task to user_analyst expert)

### 预期 artifact

`voc_insight.md` — 用户洞察结论报告（含结论、风险点、建议）

### 需要 human gate

**是**（user_gating=True；输出前需用户确认）

### 成功记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route insight_flow \
  --status ok \
  --platform feishu \
  --run-id smoke-insight-20260520-001 \
  --artifact-path <voc_insight.md路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径>
```

### 失败记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route insight_flow \
  --status blocked \
  --failure-code delegate_contract_violation \
  --run-id smoke-insight-20260520-001
```

### 推荐 failure_code

| 情形 | failure_code |
|------|-------------|
| delegate_task 返回格式不符 | `delegate_contract_violation` |
| 凭证/模型不可用 | `credential_missing` |
| human gate 超时 | `human_gate_timeout` |
| human gate 拒绝 | `human_gate_rejected` |
| 触发失败 | `trigger_miss` |

---

## Route 5: `dashboard_flow`

**功能**: 消费 VOC + 运营数据，输出产品运营报告和 Dashboard 结构

### Feishu 触发消息样例

```
请基于这批数据生成运营看板：[输入文件路径]
帮我做一份产品运营 Dashboard
```

### 预期 route

`dashboard_flow` via `voc_insight` → `ops_dashboard` (delegate_task to ops_expert)

### 预期 artifact

`ops_dashboard.md` — 产品运营报告（含 KPI、趋势、建议、Dashboard 信息架构）

### 需要 human gate

**是**（user_gating=True；ops_dashboard 节点需确认）

### 成功记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route dashboard_flow \
  --status ok \
  --platform feishu \
  --run-id smoke-dashboard-20260520-001 \
  --artifact-path <ops_dashboard.md路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径>
```

### 失败记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route dashboard_flow \
  --status blocked \
  --failure-code delegate_contract_violation \
  --run-id smoke-dashboard-20260520-001
```

---

## Route 6: `html_flow`

**功能**: VOC → 运营看板 → HTML/PDF 渲染，最终输出可部署的 HTML

### Feishu 触发消息样例

```
请把这份运营分析输出为 HTML 报告：[输入文件路径]
帮我生成一份可以分享的 HTML 看板
```

### 预期 route

`html_flow` via `voc_insight` → `ops_dashboard` → `dashboard_html` (render_expert) → `audit` (可选)

### 预期 artifact

`dashboard_html.html` 或 `dashboard_html.pdf` — 渲染完成的看板

### 需要 human gate

**否**（dashboard_html 节点 user_gating=False；但上游 ops_dashboard 节点需确认）

### 成功记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route html_flow \
  --status ok \
  --platform feishu \
  --run-id smoke-html-20260520-001 \
  --artifact-path <dashboard_html.html路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径>
```

### 失败记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route html_flow \
  --status blocked \
  --failure-code delegate_contract_violation \
  --run-id smoke-html-20260520-001
```

---

## Route 7: `dashboard_from_artifact_flow`

**功能**: 从已有 artifact 直接生成 Dashboard（跳过 VOC 分析阶段）

**⚠️ 特殊要求**: 此 route 需要用户确认 artifact 来源、版本和发布目标。

### Feishu 触发消息样例

```
请用这份已有报告生成 Dashboard：[artifact_path]
基于 /path/to/existing_report.md 生成运营看板
```

### 预期 route

`dashboard_from_artifact_flow` via `artifact_resolver` → `ops_dashboard`

### 预期 artifact

`ops_dashboard.md` — 基于已有 artifact 的运营看板

### 需要 human gate

**是**（需要确认 artifact 来源和版本；多 run_id 场景必须明确绑定）

### 成功记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route dashboard_from_artifact_flow \
  --status ok \
  --platform feishu \
  --run-id smoke-dash-artifact-20260520-001 \
  --artifact-path <ops_dashboard.md路径> \
  --audit-log <audit_log路径> \
  --review-summary <review_summary路径>
```

### 失败记录命令

```bash
python3 scripts/record_gateway_smoke_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --route dashboard_from_artifact_flow \
  --status blocked \
  --failure-code artifact_unresolved \
  --run-id smoke-dash-artifact-20260520-001
```

### 推荐 failure_code

| 情形 | failure_code |
|------|-------------|
| artifact 来源不明 | `artifact_unresolved` |
| 用户拒绝确认 artifact 版本 | `human_gate_rejected` |
| 确认超时 | `human_gate_timeout` |
| 路由判断错误 | `route_misclassified` |

---

## 完成后验证

所有 7 条 route 记录后运行：

```bash
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('gateway_smoke_completed:', d['gateway_smoke']['completed_count'], '/', d['gateway_smoke']['required_count']); \
  print('completed_routes:', d['gateway_smoke']['completed_routes'])"

python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes
```

当 `gateway_smoke_completed=7` 且 `gateway_smoke_routes_complete=true` 时，`gateway_smoke_missing` blocker 消除。

---

## 禁止事项

- ❌ 不得伪造 smoke 记录（status=ok 只能来自真实 Feishu 执行）
- ❌ 不得在 artifact_path、audit_log、review_summary 中放入占位符路径（必须是真实文件）
- ❌ 不得在一次 Feishu 消息中同时记录多个 route（每条 route 需要独立 run_id）
- ❌ 不得绕过 human gate（需要 human gate 的 route 必须有用户确认记录）
