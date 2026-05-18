# RFC-gstack-final-decision-package-v0

**Status:** ACCEPTED  
**Date:** 2026-05-18  
**Round:** 10 (Final Decision / Implementation Handoff)  
**Author:** Claude Code (Sonnet 4.6)

---

## Executive Summary

本 RFC 是 Hermes Agent System × garrytan/gstack 九轮设计迭代的最终收束文档。结论是：**允许进入 MVP skeleton 实现**，将 gstack 的 SDLC phase 概念（plan_eng_review / review / qa）作为只读协议层引入 `agent_system/gstack_control/`，Hermes runtime / Gateway / 审计 / memory / readiness gate 保持完全不变。

---

## Final Recommendation

**建议：GO — 进入 MVP Skeleton 实现。**

MVP skeleton 是一个隔离的协议层，在 `feature_flags.enabled=False`（默认）时对 Hermes 行为零影响，回滚路径简单且可验证。全量 gstack 集成（真实 CLI、browser daemon、GBrain）不在本 RFC 范围内，需要独立 RFC 批准。

---

## Go / No-Go Decision

**决定：GO（有条件）**

| 条件 | 状态 |
|------|------|
| implementation boundary 清晰 | ✅ |
| feature flag 默认关闭 | ✅（在 feature_flags.py 中硬编码）|
| blocking 默认禁止 | ✅（allow_blocking=False）|
| 路径安全（无裸 ~/.gstack）| ✅（强制 get_hermes_home()）|
| metrics 脱敏机制 | ✅（metrics_redaction.py）|
| readiness gate 不被绕过 | ✅（三个 phase 条目均 production_ready=false）|
| 回滚路径文档化 | ✅（rollback.py + evidence_report.py）|
| Gateway 不变 | ✅（gateway/* 禁止修改）|
| 用户 config 不变 | ✅（~/.hermes/config.yaml 禁止修改）|
| scripts/run_tests.sh 覆盖 | ✅（实现时建立测试）|

---

## Why MVP Skeleton Is Safe

1. **零运行时影响**：`feature_flags.enabled=False` 时所有 gstack_control 模块延迟导入，不执行任何代码，Hermes 现有行为不变。
2. **隔离边界硬编码**：gstack_control 不持有对 Gateway / runtime / cli_bridge / capability_readiness 的写引用。
3. **回滚简单**：`rm -rf agent_system/gstack_control/ && git checkout agent_system/readiness_manifest.json` 完整回滚，无数据库/配置残留。
4. **现有测试框架可复用**：`tests/conftest.py` 的 HERMES_HOME 隔离 + 凭据清除直接覆盖新模块。
5. **readiness gate 已有基础**：`capability_readiness.py` 的 ReadinessResult 状态机（ready/non_ready/unknown）可直接被 gstack phase 条目复用，无需修改。

---

## Why Full gstack Integration Is Not Yet Safe

1. **真实 CLI 未验证**：gstack 真实 CLI 行为未在 Hermes sandbox 下运行和验证。
2. **browser daemon 状态隔离未建立**：browser daemon 与 `tools/browser_tool.py` 的 check_fn 约束的交互未分析。
3. **GBrain 权限边界不兼容**：GBrain 的权限模型与 Hermes 审计链的集成路径未设计。
4. **advisory/blocking 误报率基准为零**：shadow mode 收集基准数据之前，不能安全启用 advisory。
5. **readiness_manifest 无生产就绪基线**：当前 8 个 route 全为 unknown/non_ready，建立 gstack phase 的生产就绪标准之前条件不成熟。

---

## Architecture Boundary

```
┌─────────────────────────────────────────────────────────────┐
│                     HERMES RUNTIME (不变)                    │
│  Gateway │ Router │ Audit │ Cache │ Memory │ Readiness Gate  │
│  runtime.py │ cli_bridge.py │ capability_readiness.py        │
│  hermes_constants.py │ hermes_logging.py │ toolsets.py       │
│  tools/browser_tool.py │ tools/delegate_tool.py              │
└─────────────────────────────┬───────────────────────────────┘
                              │ 只读引用（不写回）
                              ▼
┌─────────────────────────────────────────────────────────────┐
│         agent_system/gstack_control/ (新建，隔离)            │
│                                                              │
│  feature_flags.py ──► 全部默认 OFF                           │
│  specs.py ──► protocol.yaml dataclass 表示                   │
│  state_machine.py ──► low/medium/high → disabled/shadow/advisory│
│  phase_registry.py ──► plan_eng_review/review/qa 元数据      │
│  route_policy.py ──► 只读建议映射                            │
│  performance_budget.py │ roi_controller.py ──► 脱敏预算      │
│  dry_run.py │ replay.py ──► 模拟执行                         │
│  metrics_redaction.py │ metrics_writer.py ──► 脱敏写入       │
│  observability.py │ evidence_report.py │ rollback.py          │
└─────────────────────────────┬───────────────────────────────┘
                              │ 登记条目（production_ready=false）
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  agent_system/readiness_manifest.json                        │
│  新增: gstack.plan_eng_review / gstack.review / gstack.qa   │
│  全部: state=non_ready, production_ready=false, blocking=false│
└─────────────────────────────────────────────────────────────┘
```

### 严格禁止的架构决策

- gstack_control 写入 Gateway 任何组件
- gstack_control 调用真实 gstack CLI
- gstack_control 写入 `~/.gstack`（字面路径）
- gstack_control 启用 browser daemon
- gstack_control 连接 GBrain
- gstack_control 修改 `~/.hermes/config.yaml`
- gstack_control 修改 `hermes_constants.py` / `hermes_logging.py` / `capability_readiness.py`

---

## Implementation Boundary

### 允许新建的文件

```
agent_system/gstack_control/__init__.py
agent_system/gstack_control/protocol.yaml
agent_system/gstack_control/specs.py
agent_system/gstack_control/state_machine.py
agent_system/gstack_control/phase_registry.py
agent_system/gstack_control/route_policy.py
agent_system/gstack_control/performance_budget.py
agent_system/gstack_control/roi_controller.py
agent_system/gstack_control/dry_run.py
agent_system/gstack_control/replay.py
agent_system/gstack_control/feature_flags.py
agent_system/gstack_control/metrics_redaction.py
agent_system/gstack_control/metrics_writer.py
agent_system/gstack_control/observability.py
agent_system/gstack_control/evidence_report.py
agent_system/gstack_control/rollback.py
agent_system/tests/agent_system/test_gstack_control_*.py
docs/rfcs/RFC-gstack-final-decision-package-v0.md（本文件）
```

### 允许修改的现有文件

```
agent_system/readiness_manifest.json（仅追加三个 phase 条目）
PLANS.md（仅追加本轮条目）
```

### 禁止修改的文件

```
gateway/*
~/.hermes/config.yaml
hermes_cli/main.py（无单独批准不得动）
hermes_cli/config.py
hermes_constants.py
hermes_logging.py
tools/browser_tool.py
tools/delegate_tool.py
toolsets.py
agent_system/runtime.py
agent_system/cli_bridge.py
agent_system/capability_readiness.py
```

---

## Validation Boundary

### 验收标准（全部必须通过）

| 验收项 | 预期行为 | 验证命令 |
|--------|---------|---------|
| 默认关闭 | Hermes 行为不变 | `scripts/run_tests.sh` |
| low risk | mode=disabled | 单元测试 |
| medium risk | mode=shadow | 单元测试 |
| high risk | mode=advisory | 单元测试 |
| blocking | 永不默认返回 | 断言 allow_blocking=False |
| unknown readiness | 不进入 production | capability_readiness 测试 |
| non_ready readiness | 不进入 production | capability_readiness 测试 |
| metrics 脱敏 | token/cookie/Bearer 不落盘 | metrics_redaction 单元测试 |
| 路径安全 | 无裸 ~/.gstack 字符串 | `grep -r "~/.gstack" agent_system/gstack_control/ \| wc -l` = 0 |
| 无真实 gstack | 不调用 gstack CLI | mock 断言 |
| 无 browser daemon | browser_daemon=False | 配置断言 |
| Gateway 未变 | gateway/* 无修改 | `git diff gateway/` 为空 |
| 用户 config 未变 | config.yaml 无写入 | 测试 HERMES_HOME 隔离验证 |

---

## Rollback Boundary

### 完整回滚步骤

```bash
# 步骤 1：禁用 feature flag（如已启用）
# 在代码中确认 enabled=False

# 步骤 2：确认 Gateway 未变
git diff gateway/  # 必须为空

# 步骤 3：确认用户 config 未变
# ~/.hermes/config.yaml 时间戳不变

# 步骤 4：删除 gstack_control 模块
rm -rf agent_system/gstack_control/

# 步骤 5：恢复 readiness_manifest
git checkout agent_system/readiness_manifest.json

# 步骤 6：清理 metrics 文件（如有）
rm -rf "$HERMES_HOME/gstack_control/"

# 步骤 7：删除测试文件
rm -rf agent_system/tests/agent_system/test_gstack_control_*.py

# 步骤 8：验证基线恢复
scripts/run_tests.sh

# 步骤 9：生成 rollback evidence（由 rollback.py 产出）
python -c "from agent_system.gstack_control.rollback import generate_rollback_evidence; generate_rollback_evidence()"
```

### 回滚触发条件

- metrics 脱敏失败（有 token/cookie 落盘迹象）
- 出现裸 `~/.gstack` 路径写入
- Gateway 被意外修改
- 用户 config 被修改
- blocking 被意外默认启用
- `scripts/run_tests.sh` 失败率 > 0

---

## Residual Risks

| 风险 | 等级 | 缓解 |
|------|------|------|
| skeleton 实现超出 MVP 边界 | 中 | 严格限定允许文件列表 |
| metrics 脱敏导致 ROI 数据失真 | 低 | 脱敏测试覆盖边界情况 |
| readiness gate 被误用（non_ready 进生产）| 低 | 现有 capability_readiness 逻辑已阻止 |
| 新 import 影响 prompt cache | 低 | gstack_control 延迟导入，flag=false 时零副作用 |
| 后续接真实 browser backend | 高 | MVP 明确禁止，需独立 RFC |
| 后续接 GBrain | 高 | MVP 明确禁止，需独立 RFC |
| advisory/blocking 误报 | 中 | shadow mode 先收集基准，再评估 |
| 测试覆盖率不足 | 中 | scripts/run_tests.sh 必须覆盖所有新模块 |

---

## Explicit Non-goals

本 RFC 明确**不包含**以下内容，实现时不得扩展至此：

- 调用真实 gstack CLI
- 启用 browser daemon
- 连接 GBrain
- 启用 telemetry / proactive mode / continuous checkpoint
- 修改 Gateway
- 修改用户 `~/.hermes/config.yaml`
- 将任何 gstack phase 设为 production_ready=true
- 实现 blocking 模式（allow_blocking 默认 False，MVP 不提供升级路径）
- ship / canary / deploy 真实流程
- agent 直接调用 $B 绕过 browser_tool

---

## Next Implementation Prompt

以下指令可直接用于第 11 轮实现：

```
实现任务：Hermes × gstack MVP Skeleton（Round 11）

工作目录：/Users/frank/.hermes/hermes-agent-official/

硬约束（全程遵守，不得以任何理由违反）：

【文件边界】只允许新建/修改以下文件，不得触碰其他文件：
  agent_system/gstack_control/__init__.py
  agent_system/gstack_control/protocol.yaml
  agent_system/gstack_control/specs.py
  agent_system/gstack_control/state_machine.py
  agent_system/gstack_control/phase_registry.py
  agent_system/gstack_control/route_policy.py
  agent_system/gstack_control/performance_budget.py
  agent_system/gstack_control/roi_controller.py
  agent_system/gstack_control/dry_run.py
  agent_system/gstack_control/replay.py
  agent_system/gstack_control/feature_flags.py
  agent_system/gstack_control/metrics_redaction.py
  agent_system/gstack_control/metrics_writer.py
  agent_system/gstack_control/observability.py
  agent_system/gstack_control/evidence_report.py
  agent_system/gstack_control/rollback.py
  agent_system/readiness_manifest.json（仅追加三条）
  agent_system/tests/agent_system/test_gstack_control_*.py（新建）

【默认行为】
  enabled=False, mode=disabled, allow_blocking=False
  use_real_gstack=False, browser_daemon=False, gbrain=False
  telemetry=False, proactive_mode=False, continuous_checkpoint=False

【路径规范】
  所有路径通过 from hermes_constants import get_hermes_home
  禁止裸写 ~/.gstack 字符串

【脱敏规范】
  metrics_redaction.py 过滤：token/cookie/Authorization/Bearer/refresh_token

【readiness_manifest 追加】
  gstack.plan_eng_review / gstack.review / gstack.qa
  全部：state=non_ready, production_ready=false, blocking=false

【state_machine 规范】
  low → disabled | medium → shadow | high → advisory | blocking 永不默认

【验收】scripts/run_tests.sh 0 失败
```
