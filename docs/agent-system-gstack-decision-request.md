# Hermes Agent-System — gstack 专家层设计关系

> **Status**: 设计说明（非待决策文档）
> **Updated**: 2026-05-20
> **核心结论**: gstack 是专家资产来源，不是外部 CLI 依赖；Hermes production_ready 不依赖 gstack CLI 安装

---

## gstack × Hermes 设计关系

| 角色 | 说明 |
|------|------|
| **gstack** | 外部专家资产 / 专家方法库 / 角色模式来源 |
| **Hermes** | 调度、执行、记忆、治理、门禁的主系统 |

### 三种专家类型

| 类型 | 说明 |
|------|------|
| **native expert** | Hermes 原生专家，无外部依赖 |
| **absorbed expert** | 来源于 gstack，但已被 Hermes 吸收、注册、治理 |
| **external runtime expert** | 依赖外部 CLI 执行 — **不是我们的目标** |

### 当前 gstack 状态

```bash
python3 -m agent_system.gstack_control.ops status
```

| 字段 | 当前值 | 含义 |
|------|--------|------|
| `enabled` | false | gstack 模块未激活 |
| `adapter_available` | false | gstack CLI 未安装 |
| `mode` | disabled | 纯 shadow/advisory 模式 |
| `blocking` | false | 不阻断主流程 |

gstack 当前处于 **shadow/advisory/fail-closed** 模式。所有 7 条 ready routes 正常工作，不依赖 gstack。

---

## 门禁模型（已修正）

| gstack 状态 | 对 upgrade_allowed 的影响 |
|-------------|--------------------------|
| gstack CLI 缺失 | **advisory warning — 不阻断升级** |
| gstack external evidence 缺失 | **integration_backlog — 不阻断升级** |
| gstack phases non_ready | 仅记录，blocking=false |

`Hermes production_ready 不依赖 gstack CLI 是否安装。`

---

## 专家层资产吸收路径（正确方向）

### 吸收 vs. 安装

| 方式 | 说明 | 推荐 |
|------|------|------|
| **吸收专家模式** | 把 gstack 专家角色/方法论纳入 Hermes expert layer，由 Hermes 治理 | ✅ 推荐 |
| **安装 gstack CLI** | 让 gstack 作为外部 runtime 运行，Hermes 调用其 CLI | ❌ 非目标 |

### 吸收工作流（integration_backlog）

1. 识别 gstack 中有价值的专家模式（plan_eng_review / review / qa）
2. 以 `absorbed_expert` 形式注册到 Hermes manifest（`absorption_status: candidate → reviewed → approved`）
3. 由 Hermes 调度和治理，不依赖外部 CLI
4. 若未来需要 gstack 外部证据：通过 `gstack_bridge.route_gstack_result()` 接入，受 ACL 保护

### 禁止事项

- ❌ 不自动安装 gstack CLI
- ❌ 不配置独立 gstack API key
- ❌ 不让 gstack 直接写 system_mem / expert_mem / skill_mem
- ❌ 不创建 gstack shared memory
- ❌ 不把 gstack 当成生产门禁（它是 advisory）

---

## 当前 gstack 在 blockers 中的位置

```bash
# 查看 advisory_warnings（不是 blockers）
python3 scripts/agent_system_blockers.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('advisory_count:', d['advisory_count']); \
  [print(json.dumps(w, indent=2, ensure_ascii=False)) \
   for w in d['advisory_warnings']]"

# 查看完整状态
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('upgrade_allowed:', d['upgrade_allowed']); \
  print('gstack:', d['gstack']['mode']); \
  print('advisory_warnings:', len(d.get('advisory_warnings', [])))"
```

---

## 真正的生产 blockers

gstack 不是 blocker。当前真正的升级门禁是：

```bash
python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes
```

真实 blockers（按优先级）：
1. **gateway_smoke_missing** [critical] — 7 条 ready routes 需要真实 Feishu/Gateway smoke
2. **config_secret_detected** [critical] — 配置中存在明文密钥
3. **insufficient_memory_events** [high] — memory events 低于 50 条
4. **human_gate_not_drilled** [high] — human gate drill 未完成

这些才是需要解决的真实 blockers。gstack 是 integration_backlog，不影响升级判断。
