"""Usage Hint Readback Tests

Verifies that:
1. build_memory_context_block() wraps content with usage_hint when USAGE_HINT_INJECTION_ENABLED=ON
2. The hint is absent when flag is OFF
3. hint_for_knowledge() returns correct hints for different doc types
"""
from __future__ import annotations

import pytest


def test_build_memory_context_block_with_hint_flag_on(monkeypatch):
    """USAGE_HINT_INJECTION_ENABLED=ON → block contains [usage_hint:]."""
    monkeypatch.setenv("USAGE_HINT_INJECTION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)

    from agent.memory_manager import build_memory_context_block

    result = build_memory_context_block("这是一段记忆内容。")

    assert "[usage_hint:" in result, "hint must be present when flag is ON"
    assert "project_material_usable" in result
    assert "这是一段记忆内容。" in result, "original content must not be modified"


def test_build_memory_context_block_no_hint_flag_off(monkeypatch):
    """USAGE_HINT_INJECTION_ENABLED=OFF → no usage_hint in block."""
    monkeypatch.delenv("USAGE_HINT_INJECTION_ENABLED", raising=False)

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)

    from agent.memory_manager import build_memory_context_block

    result = build_memory_context_block("这是一段记忆内容。")

    assert "[usage_hint:" not in result, "hint must be absent when flag is OFF"
    assert "这是一段记忆内容。" in result


def test_build_memory_context_block_empty_input():
    """Empty input must return empty string regardless of flag."""
    from agent.memory_manager import build_memory_context_block

    assert build_memory_context_block("") == ""
    assert build_memory_context_block("   ") == ""


def test_hint_for_knowledge_deprecated(monkeypatch):
    from agent.usage_hint import hint_for_knowledge
    doc = {"confidence": "deprecated", "knowledge_type": "business_fact"}
    assert hint_for_knowledge(doc) == "old_version_background"


def test_hint_for_knowledge_financial(monkeypatch):
    from agent.usage_hint import hint_for_knowledge
    doc = {"confidence": "high", "knowledge_type": "financial_kpi"}
    assert hint_for_knowledge(doc) == "do_not_forward_source"


def test_hint_for_knowledge_draft(monkeypatch):
    from agent.usage_hint import hint_for_knowledge
    doc = {"confidence": "draft", "knowledge_type": "business_fact"}
    assert hint_for_knowledge(doc) == "needs_source_check"


def test_hint_for_knowledge_normal(monkeypatch):
    from agent.usage_hint import hint_for_knowledge
    from agent.usage_hint import USAGE_HINTS
    doc = {"confidence": "high", "knowledge_type": "business_fact"}
    hint = hint_for_knowledge(doc)
    assert hint in USAGE_HINTS


def test_wrap_with_hint_structure():
    from agent.usage_hint import wrap_with_hint
    content = "some content here"
    hint = "project_material_usable"
    result = wrap_with_hint(content, hint)
    assert result.startswith(f"[usage_hint: {hint}]")
    assert content in result


def test_memory_context_block_preserves_fence_structure(monkeypatch):
    """Block must always start with <memory-context> tag regardless of flag."""
    monkeypatch.setenv("USAGE_HINT_INJECTION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)

    from agent.memory_manager import build_memory_context_block

    result = build_memory_context_block("内容")
    assert result.startswith("<memory-context>")
    assert result.endswith("</memory-context>")
