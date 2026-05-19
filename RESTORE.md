# RESTORE — Sedimentation Runtime Wiring 回滚指令

生成时间: 2026-05-19  
适用轮次: Round 13 + Round 14 (Contract Layer + Runtime Wiring) + 验收收口

## 当前状态

| 项目 | 值 |
|------|-----|
| local HEAD | 55582309a（Round 14 docs） |
| fork remote HEAD | **55582309a**（push 已完成 2026-05-19） |
| branch | snapshot/hermes-local-20260514-224006 |
| acceptance closure commit | 待提交（pending_capture fix + smoke + docs） |

## 恢复点

| 轮次 | commit | 描述 |
|------|--------|------|
| Round 13 | a39cd44cf | 合同测试骨架（S1-S12），14个新文件，feature flags OFF |
| Round 14 | 6db73843d | Runtime 接线：run_agent/knowledge_tool/cli_bridge/runtime/memory_manager |
| Round 14 post | 371e5cbf5 | knowledge_staging_ops tool entry point（Gate 3 CLI） |
| Round 14 post | 9e89318ca | knowledge_staging_ops 14 tests |
| Round 14 post | d31354694 | experience_card trigger_check prompt injection wired |
| Round 14 post | 55582309a | docs: PLANS.md + RESTORE.md post-Round14 completions |
| 验收收口 | TBD | 验收收口：pending fix + smoke + docs（本次提交） |
| Round 12 | db570d1f8 | Weekly Flow + Quality Gate（恢复到此可回到 Round 12） |

## 快速回滚到 Round 12 状态

```bash
git reset --hard db570d1f8  # 警告：丢弃 Round 13+14 所有修改
scripts/run_tests.sh
```

## 选择性回滚 Round 14（保留 Round 13 合同层）

```bash
# 恢复 runtime 接线修改
git checkout a39cd44cf -- \
  run_agent.py \
  agent/memory_manager.py \
  agent/session_capture.py \
  tools/knowledge_tool.py \
  agent_system/cli_bridge.py \
  agent_system/runtime.py \
  agent_system/sedimentation/feature_flags.py \
  agent_system/sedimentation/gstack_bridge.py \
  agent_system/gstack_control/config.py \
  agent/staging_store.py \
  agent/pending_capture.py

# 删除 Round 14 新增测试
rm -f \
  tests/agent/test_session_capture_runtime.py \
  tests/agent/test_knowledge_tool_sedimentation.py \
  tests/agent/test_staging_ops.py \
  tests/agent/test_usage_hint_readback.py \
  tests/agent_system/test_experience_layer_runtime.py \
  tests/agent_system/test_gstack_bridge_control.py

scripts/run_tests.sh
```

## 新建文件（删除即完全回滚）

```bash
# Phase 2: 8个核心模块
rm -f agent/memory_event.py
rm -f agent/memory_relations.py
rm -f agent/staging_store.py
rm -f agent/usage_hint.py
rm -f agent/experience_card.py
rm -f agent/project_process_store.py
rm -f agent/memory_dispatcher.py
rm -f agent/session_capture.py

# Phase 5-6: sedimentation 子系统
rm -rf agent_system/sedimentation/

# Phase 1: 治理契约文档
rm -f docs/architecture/sedimentation-governance.md

# 测试文件
rm -f tests/agent/test_sedimentation_governance.py
```

## 最小修改文件（需 git checkout 恢复）

```bash
# Phase 4: usage_hint 回读路径修改
git checkout agent/memory_manager.py
git checkout tools/knowledge_tool.py

# Phase 6: runtime hook
git checkout agent_system/runtime.py
git checkout agent_system/cli_bridge.py
```

## 验证回滚

```bash
scripts/run_tests.sh
```

## 不影响的已有文件

- run_agent.py（quality gate 在 Round 12 已集成，本轮不动）
- agent_system/weekly/（Round 12 产出）
- agent_system/quality/（Round 12 产出）
- agent_system/gstack_control/（Round 11 产出）
- readiness_manifest.json（测试全部通过前不改）
