# RESTORE — Sedimentation Governance Backbone 回滚指令

生成时间: 2026-05-19  
适用轮次: Round 13 (Sedimentation Governance Backbone + gstack 专家层接入)

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
