# Sedimentation Governance Architecture

> Version: 1.1 | Date: 2026-05-19 | Status: Implemented (Round 13 + Round 14)

## Overview

所有候选沉淀内容（私聊、PBI、用户纠正、工具失败、gstack 输出）经由统一入口
`MemoryEvent` 进入系统，由 `MemoryDispatcher` 按 10 条规则路由到 5 个目标之一。
不确定内容进入 `StagingStore`，永不被静默丢弃。

## 数据流图

```
任意内容来源
    ↓
MemoryEvent(id, source_type, risk_flags, recommended_destination, ...)
    ↓
MemoryDispatcher.dispatch_event(event) → DispatchResult
    ├─ personal_memory   ← 用户偏好、私下判断（已确认 scope）
    ├─ project_process   ← PBI、版本计划（有 project_hint）
    ├─ knowledge         ← 来源清楚、可复用事实
    ├─ experience_card   ← 结构化行动卡（触发+判断+禁止）
    └─ staging           ← 条件不足（不丢失，等待下一步）

所有回读路径:
    任何存储 → wrap_with_hint(content, hint) → prompt
```

## 10条分流规则（优先级从高到低）

| 优先级 | 条件 | 目标 | next_action |
|--------|------|------|-------------|
| 1 | identity_missing 或 project_uncertain | staging | needs_user_confirmation |
| 2a | private_chat + dest=project_process | staging | needs_user_confirmation |
| 2b | private_chat + 无 project_hint | staging | wait_for_source |
| 3 | tool_failure | staging | retry_write |
| 4 | user_correction + 无 scope | staging | needs_user_confirmation |
| 5 | permission_unclear 或 stale_version | staging | needs_project_mapping |
| 6 | user_correction + 有 scope | personal_memory | — |
| 7 | recommended=experience_card | experience_card | — |
| 8 | recommended=project_process | project_process | — |
| 9 | recommended=knowledge | knowledge | — |
| 10 | 默认 | personal_memory | — |

## 5个 risk_flags

| flag | 触发场景 |
|------|---------|
| private_chat | 内容来自私聊会话 |
| project_uncertain | 项目归属不清 |
| permission_unclear | 权限范围不清 |
| stale_version | 可能是旧版本内容 |
| user_correction | 用户纠正了之前的内容 |
| tool_failure | 工具写入失败 |
| identity_missing | 说话者/来源身份不清 |

## StagingStore next_action 状态机

```
write_staging → next_action:
    wait_for_source        ← 来源不明，等待确认
    needs_user_confirmation ← 需要用户确认归属/范围
    needs_project_mapping  ← 需要项目映射
    retry_write            ← 权限问题解决后重试
    archive_as_reference   ← 归档参考，不主动推进
```

## 6类 UsageHint（所有回读内容必须携带）

| hint | 含义 |
|------|------|
| private_reference_only | 仅私人参考，不可转发 |
| project_material_usable | 项目材料，可在项目范围使用 |
| old_version_background | 旧版本背景，仅参考 |
| needs_source_check | 来源待确认，使用前核实 |
| do_not_forward_source | 内容可用但来源不可对外透露 |
| action_rule_for_next_task | 下次任务的行动规则（ExperienceCard） |

## 三层经验写入 ACL

```
system_mem:  仅 caller_id="hermes_main" 可写
expert_mem:  仅 caller_id 与 expert_id 匹配可写
skill_mem:   仅 caller_id 与 skill_id 匹配可写

gstack 任何输出 → 必须走 candidate → dispatcher → ACL 审核
gstack 不可直接写 system_mem / expert_mem / skill_mem
```

## gstack 专家层路由规则

| output_type | destination | 说明 |
|-------------|-------------|------|
| review | audit_evidence | 只记录，不进 expert_mem |
| fact | knowledge_candidate | 走 dispatcher，不直接写 |
| lesson | expert_mem_candidate | 需 dispatcher 审核，不直接写 |
| playbook | skill_asset | 结构化资产，不直接写 skill_mem |
| action_rule | experience_card_candidate | ExperienceCard 候选 |
| uncertain | staging | needs_project_mapping |

**feature flag**: `GSTACK_SEDIMENTATION_ENABLED`（默认 false）

## 存储布局

```
{HERMES_HOME}/
├── memory_events/events.jsonl         ← MemoryEvent 流水（统一入口）
├── staging/staging.jsonl              ← 暂存区（不确定内容）
├── memory_relations/relations.jsonl   ← 强关系图
├── project_process/records.jsonl      ← 项目流程记录
├── experience_cards/cards.jsonl       ← 结构化行动卡
└── knowledge/pending_captures.jsonl   ← 已有，pending 重放
```

## 关键模块

| 模块 | 职责 |
|------|------|
| `agent/memory_event.py` | MemoryEvent 创建、写入、读取 |
| `agent/memory_dispatcher.py` | 10规则5目的地分流 |
| `agent/staging_store.py` | StagingEntry + next_action |
| `agent/usage_hint.py` | 6类 hint，wrap_with_hint() |
| `agent/experience_card.py` | ExperienceCard，DAVID_CARD |
| `agent/project_process_store.py` | 项目流程写入 |
| `agent/memory_relations.py` | 10种强关系记录 |
| `agent/session_capture.py` | 会话风险探测 |
| `agent_system/sedimentation/feature_flags.py` | 全部默认 OFF |
| `agent_system/sedimentation/experience_layer.py` | 三层 ACL |
| `agent_system/sedimentation/gstack_bridge.py` | gstack → 沉淀链 |

## 硬性禁止

- KnowledgeCandidate 不是总入口（只是 payload）
- 私聊不直接进 knowledge 或 project_process
- gstack 不直接写 system_mem / expert_mem / skill_mem
- audit/evidence 不等于 expert_mem
- 运行日志不等于经验
- 所有路径必须经过 get_hermes_home()，禁止硬编码

## Round 14 Runtime Wiring Evidence（2026-05-19）

| 组件 | 状态 | runtime 触发点 |
|------|------|----------------|
| memory_event + dispatcher | wired | session_capture / knowledge_tool / cli_bridge |
| staging_store ops | wired | knowledge_staging_ops tool + approve/reject/archive |
| session_capture | wired | run_agent.py SESSION_CAPTURE_AUTO_ENABLED gate |
| usage_hint | wired | memory_manager + knowledge_query（flag OFF by default） |
| experience_layer ACL | wired | runtime._append_private_memory 非破坏性包装 |
| experience_card injection | wired | run_agent.py trigger_check+render_card，ephemeral 注入 |
| gstack_bridge | wired | route_gstack_result（GSTACK_SEDIMENTATION_ENABLED gate） |

**Smoke Evidence（acceptance closure 2026-05-19）：**
- memory_events/events.jsonl: 2 行（session + write_failure）
- staging/staging.jsonl: 15 行（14 retry_write + 1 needs_user_confirmation）
- pending_captures.jsonl: 14 行，terminal_state=migrated_to_staging（14/14）
- project_process/records.jsonl: 1 行（smoke 触发验证）
- experience_cards/cards.jsonl: 不存在（设计正确——ephemeral 注入，无 runtime write）

**升级判断：wired 但不 production_ready。剩余 blocker：**
1. 无真实流量 smoke（SESSION_CAPTURE_AUTO_ENABLED=OFF）
2. gstack CLI 未安装（phases non_ready）
3. routes production_ready=0
