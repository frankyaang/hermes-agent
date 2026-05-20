# Hermes Agent-System — gstack 决策请求

> **Status**: Awaiting user decision  
> **Generated**: 2026-05-20  
> **Trigger**: `gstack_cli_missing=true` + `gstack_external_evidence_missing=true`  
> **Action required**: 用户必须选择 Option A 或 Option B；Claude Code 不会自动安装 gstack。

---

## 当前 gstack 状态

```bash
python3 -m agent_system.gstack_control.ops status
```

| 字段 | 当前值 |
|------|--------|
| `enabled` | false |
| `mode` | disabled |
| `adapter_available` | false |
| `kill_switch` | true |
| `blocked_reason` | gstack CLI not found at PATH |

gstack 当前处于 **shadow/advisory/fail-closed** 模式。

- Hermes 所有业务路由不依赖 gstack 执行
- gstack 输出不进入 Hermes 任何存储路径
- `GSTACK_SEDIMENTATION_ENABLED=false`（默认 OFF）

---

## 两个选项

---

### Option A：安装并验证 gstack

**适用场景**：需要 gstack 外部专家证据，计划让 gstack review/lesson/fact 输出进入 Hermes 沉淀链。

#### 要求说明

| 条件 | 要求 |
|------|------|
| 安装路径 | 必须放在用户 PATH 中，建议 `/usr/local/bin/gstack` 或 `~/.local/bin/gstack` |
| Claude/Codex skills 影响 | gstack 本身与 Claude Code skills 无直接冲突；但 GSTACK_SEDIMENTATION_ENABLED=true 会让 gstack 输出经过 MemoryDispatcher |
| shadow/advisory 模式 | `allow_blocking=false` + `kill_switch=true` 保持 gstack 不阻断主流程 |
| 禁止直接写 Hermes private memory | gstack 所有输出必须经过 `gstack_bridge.route()` → `MemoryDispatcher` → ACL，**不允许 gstack 直接调用 `_append_memory_line()` 或写 system_mem/expert_mem/skill_mem** |
| 如何产出 external_expert_evidence | gstack phase 完成后，结果经 `gstack_bridge.route_gstack_result()` 路由，source_uri 以 `hermes://gstack/` 开头，这样 `covers_gstack_external_evidence=true` |

#### 安装后 smoke 命令

```bash
# 确认 gstack CLI 可用
gstack --version

# 运行 gstack smoke（Hermes 侧验证）
python3 -m agent_system.gstack_control.ops smoke

# 检查 adapter_available
python3 -m agent_system.gstack_control.ops status | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('adapter_available:', d['adapter_available'])"
```

#### 开启 gstack sedimentation（安装且 smoke 通过后）

```bash
# 仅在 staging 环境开启，不在本地直接改全局配置
export GSTACK_SEDIMENTATION_ENABLED=true

# 验证 feature flag
python3 -c "
from agent_system.sedimentation.feature_flags import GSTACK_SEDIMENTATION_ENABLED
print('GSTACK_SEDIMENTATION_ENABLED:', GSTACK_SEDIMENTATION_ENABLED)
"
```

#### 回滚方式

```bash
# 1. 关闭 feature flag
export GSTACK_SEDIMENTATION_ENABLED=false
# 或在 gstack config 中设置：
python3 -c "
from agent_system.gstack_control.config import load_gstack_config
cfg = load_gstack_config()
cfg['kill_switch'] = True
# 保存 cfg（路径取决于 config loader）
"

# 2. 若需要彻底移除 gstack CLI
which gstack
rm $(which gstack)  # 或从 PATH 中移除

# 3. 验证恢复到 shadow-only
python3 -m agent_system.gstack_control.ops status | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('adapter_available:', d['adapter_available'])"
```

#### 完成标准

- `adapter_available=true`
- `python3 -m agent_system.gstack_control.ops smoke` 不再报 `gstack CLI not found`
- 至少 1 条 `source_uri` 包含 `hermes://gstack/` 的 MemoryEvent 写入 `events.jsonl`
- `covers_gstack_external_evidence=true`

---

### Option B：保持 gstack disabled/shadow-only

**适用场景**：暂不需要 gstack 外部专家证据，或 gstack 安装成本/风险过高。

#### 含义

| 条件 | 后果 |
|------|------|
| gstack 继续不安装 | `gstack_cli_missing` 保持为 blocker |
| `gstack_external_evidence_missing` 保持 true | 此 blocker 不消除 |
| `upgrade_allowed` 保持 false | 这两个 blocker 存在时不能升级 |
| Hermes 主流程不受影响 | 7 条 ready routes 正常工作，只是不能升级 |

#### 不需要任何操作

保持 Option B 不需要执行任何命令。当前状态就是 shadow-only。

#### 如何将 Option B 明确记录

```bash
# 可选：在 run evidence 中记录 gstack shadow-only 决策（需要真实 run_id）
python3 scripts/record_run_evidence.py \
  --hermes-home /Users/frank/.hermes \
  --platform feishu \
  --route artifact_status_flow \
  --status blocked \
  --failure-code gstack_cli_missing \
  --run-id "gstack-decision-2026-05-20" \
  --session-id "user-decision"
```

---

## 验证命令（两个选项通用）

```bash
# 查看当前 gstack blocker 详情
python3 scripts/agent_system_blockers.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  [print(json.dumps(b, indent=2, ensure_ascii=False)) \
   for b in d['blockers'] if 'gstack' in b['blocker_code']]"

# 查看完整状态
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('upgrade_allowed:', d['upgrade_allowed']); \
  print('gstack:', d['gstack'])"
```

---

## 当前不能升级

无论选择哪个 Option，**当前 `upgrade_allowed=false`**，还有其他 blockers 未解决：

```bash
python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes
```

gstack blockers 只是总 blocker 列表的一部分。
