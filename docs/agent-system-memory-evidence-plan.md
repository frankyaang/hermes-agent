# Hermes Agent-System — Memory Evidence 闭环计划

> **Status**: 执行计划  
> **Generated**: 2026-05-20  
> **当前 memory_events**: 5 (required: 50)  
> **目标**: 积累 ≥50 真实 MemoryEvent，覆盖所有必要 source_type 和 risk_flag

---

## 当前状态

```bash
python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes
```

| 检查项 | 当前状态 | 目标 |
|--------|---------|------|
| `min_50_real_events` | ❌ false (5/50) | 50 条真实事件 |
| `covers_user_correction` | ✅ true | 至少 1 条 user_correction 事件 |
| `covers_tool_failure` | ✅ true | 至少 1 条 tool_failure 事件 |
| `covers_permission_unclear` | ✅ true | 至少 1 条 permission_unclear 事件 |
| `covers_project_process` | ✅ true | 至少 1 条 project_process 路由 |
| `covers_gstack_external_evidence` | ❌ false | 至少 1 条 source_uri 含 `hermes://gstack/` |

**已覆盖 5/6 类型检查**；主要缺口是总量（5/50）和 gstack 外部证据。

---

## 事件来源分类

### A. 只能来自真实任务的事件

以下事件**不能伪造**，必须来自真实 Feishu/Gateway 任务执行：

| source_type | 触发场景 | 典型来源 |
|-------------|---------|---------|
| `session` | 真实 Feishu 会话开始，SESSION_CAPTURE_AUTO_ENABLED=true | run_agent.py capture_turn() |
| `tool_result` | 工具执行成功返回结果 | knowledge_tool, cli_bridge |
| `write_failure` | knowledge_tool 写入失败，触发 dispatch_tool_failure() | knowledge_tool |
| `document` | 文档类内容进入沉淀链 | memory_dispatcher |

### B. 需要用户纠正样本的事件

以下事件需要用户在真实对话中明确纠正之前的结论：

| risk_flag | 触发场景 | 如何产生 |
|-----------|---------|---------|
| `user_correction` | 用户说"不对，应该是..."或"我之前说错了" | 用户在 Feishu 中纠正 Hermes 的结论 |

**当前状态**: `covers_user_correction=true`（已有 1 条，够用）

### C. 来自工具失败的事件

| risk_flag | 触发场景 | 如何产生 |
|-----------|---------|---------|
| `tool_failure` | knowledge_tool 或 cli_bridge 写入失败 | dispatch_tool_failure() 自动触发 |

**当前状态**: `covers_tool_failure=true`（已有 2 条）

启用方式：任何 knowledge 写入失败都会自动触发。不需要手动操作。

### D. 来自权限不清的事件

| risk_flag | 触发场景 | 如何产生 |
|-----------|---------|---------|
| `permission_unclear` | cli_bridge 检测到 permission_denied，或内容来自权限未明确的来源 | cli_bridge._auto_sedate_knowledge() |

**当前状态**: `covers_permission_unclear=true`（已有 2 条）

### E. 来自项目流程的事件

| destination | 触发场景 | 如何产生 |
|-------------|---------|---------|
| `project_process` | MemoryEvent 包含 project_hint 且 recommended_destination=project_process | dispatch_event() 路由结果 |

**当前状态**: `covers_project_process=true`（已有 3 条 project_process 记录）

### F. 来自 gstack 外部证据的事件（当前缺失）

| source_uri 前缀 | 触发场景 | 如何产生 |
|-----------------|---------|---------|
| `hermes://gstack/` | gstack phase 完成，结果经 gstack_bridge.route_gstack_result() 路由 | 需要 gstack CLI 安装 + GSTACK_SEDIMENTATION_ENABLED=true |

**当前状态**: `covers_gstack_external_evidence=false`

**为什么不能伪造**：`check_agent_system_operational_evidence.py` 直接读取 `events.jsonl` 并检查 `source_uri` 字段是否包含 `hermes://gstack/`。手动写入虽然技术可行，但违反 hard rule："不伪造 memory events"。

**如何解决**：
- Option A：安装 gstack（见 `docs/agent-system-gstack-decision-request.md`）
- Option B：接受这个 blocker 持续存在（upgrade_allowed 保持 false）

---

## 积累 50 条真实事件的计划

### 前提条件

开启 session capture（仅在 staging 环境）：

```bash
export SESSION_CAPTURE_AUTO_ENABLED=true
```

这样每次 Feishu/Gateway 任务都会自动发出 MemoryEvent。

### 事件积累路径

| 路径 | 每次任务预计产生事件数 | 注意 |
|------|---------------------|------|
| 7 条 Gateway smoke（每条约 2-3 个事件）| ~14-21 | 需要真实 Feishu 执行 |
| 正常运营任务（每天数条）| ~5-10/天 | SESSION_CAPTURE_AUTO_ENABLED=true |
| knowledge 写入尝试（含失败）| ~1-3/任务 | 自动触发 |

预计达到 50 条：完成 7 条 Gateway smoke + 约 2-3 周正常运营。

### 验证命令

```bash
# 实时检查事件数量和覆盖情况
python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes

# 查看事件 source_type 分布（不打印内容）
python3 -c "
import json
from pathlib import Path
events = [json.loads(l) for l in Path('/Users/frank/.hermes/memory_events/events.jsonl').read_text().splitlines() if l.strip()]
from collections import Counter
print('total:', len(events))
print('by source_type:', dict(Counter(e.get('source_type','?') for e in events)))
risk = Counter(f for e in events for f in (e.get('risk_flags') or []))
print('by risk_flag:', dict(risk))
"
```

---

## 为什么不能伪造事件

1. **系统完整性**：`events.jsonl` 是 MemoryDispatcher 的流水账；伪造会破坏审计链
2. **ACL 约束**：所有写入经过 `experience_layer.write_to_layer()` ACL；直接写文件绕过 ACL
3. **验收标准**：operational evidence check 验证的是"真实运营中产生的事件"，不是填充数据
4. **Hard rule**：计划明确规定"不伪造 memory events"

---

## 里程碑

| 里程碑 | 目标 | 验证方式 |
|--------|------|---------|
| M1 | 完成 7 条 Gateway smoke | `gateway_smoke_routes_complete=true` |
| M2 | 积累 25 条事件 | `event_count >= 25` |
| M3 | 积累 50 条事件 | `min_50_real_events=true` |
| M4 | gstack 证据（可选）| `covers_gstack_external_evidence=true` |
| M5 | 全部检查通过 | `status=ready` |

---

## 最终验证命令

```bash
python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('overall_status:', d['overall_status']); \
  print('upgrade_allowed:', d['upgrade_allowed'])"
```
