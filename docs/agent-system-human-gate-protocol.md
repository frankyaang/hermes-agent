# Hermes Agent-System 人工门禁协议

本文档定义需要人工确认时的记录规则、拒绝/超时处理和 Feishu pending guard 行为。它和 `agent-system-operations-runbook.md` 配套使用。

## 适用场景

以下情况必须进入人工门禁：

- 任务会写入、发布或覆盖用户可见产物。
- 任务需要读取或引用敏感业务上下文。
- route 的输入不完整，可能导致错误路由或错误产物。
- `dashboard_from_artifact_flow` 需要确认 artifact 来源、版本和发布目标。
- Gateway/Feishu 会话中存在多个候选 run，需要绑定明确 `run_id`。
- gstack、外部专家或沉淀系统的建议可能影响 QA 门禁或长期 memory。

## 审批前确认

执行前必须确认：

- `route`
- `run_id`
- `message_id` 或会话来源
- 输入 artifact 或需求来源
- 输出目标
- 是否允许发布到 Feishu
- 是否允许写入 memory staging
- 是否涉及外部专家证据

如果这些字段缺失，状态应记录为 `blocked`，失败码优先使用：

- `human_gate_timeout`
- `human_gate_rejected`
- `route_misclassified`
- `artifact_unresolved`
- `memory_acl_denied`

## Run ID 绑定

每次真实 Gateway/Feishu smoke 都必须绑定一个稳定 `run_id`。同一个 `run_id` 贯穿：

- Gateway smoke evidence
- run evidence
- artifact path
- audit log
- review summary
- memory event 或 staging id

如果无法确认 `run_id`，不要把本次结果计为真实 smoke。

## 拒绝与超时

用户拒绝：

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route <route> \
  --status blocked \
  --failure-code human_gate_rejected \
  --run-id <run_id>
```

用户超时：

```bash
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route <route> \
  --status blocked \
  --failure-code human_gate_timeout \
  --run-id <run_id>
```

拒绝或超时不是系统成功，不能计为 route smoke 通过。

## 审批记录位置

审批事实至少要能在以下位置之一被追溯：

- `/Users/frank/.hermes/agent_system/evidence/run_evidence.jsonl`
- `/Users/frank/.hermes/agent_system/evidence/gateway_smoke.json`
- 对应 run 的 audit log
- 对应 review summary
- memory staging 记录

记录中不得包含 access token、refresh token、API key、Authorization header 或 Bearer token。

## Feishu Pending Guard

当 Agent 正在执行或等待审批时，Feishu 后续消息不得绕过 pending guard 直接进入新执行链。控制类消息应被识别并原地处理：

- approve
- deny
- stop
- status
- queue

如果 pending guard 导致消息排队，需要在 evidence 中记录阻塞原因和最终处理结果。不要把排队消息误当成新需求。

## dashboard_from_artifact_flow

该 route 已允许作为 ready route，但真实执行仍需要人工确认：

1. artifact 来源是否明确。
2. artifact 是否存在且可读取。
3. dashboard 输出目录是否安全。
4. 是否允许发布或仅生成本地 artifact。
5. 审计记录和 review summary 是否生成。

只有上述确认完成，且真实 Gateway/Feishu smoke 成功，才可记录为 `status=ok`。

## gstack 外部专家证据

gstack 当前只能作为专家层外部证据来源，初期保持 `shadow/advisory`。人工门禁需要确认：

- gstack 输出是否标记为 `external_expert_evidence`
- 来源、依赖、证据、治理等级是否可追溯
- 是否只进入 staging 或 evidence，不直接写 private memory
- 是否未获得阻断主流程的权限

如果 gstack CLI 不可用，记录缺失证据，不要安装或伪造输出。

## 升级前人工确认

升级前操作者必须确认：

- 7 条 ready route 均有真实 Gateway/Feishu smoke。
- memory events 至少 50 条且覆盖要求齐全。
- gstack external evidence 已存在，或明确保持 shadow-only 且不宣称 production ready。
- redacted config snapshot 存在且没有 `config_secret_detected`。
- acceptance report 存在且 `upgrade_allowed=true`。

任一项不满足，结论必须保持 `upgrade_allowed=false`。
