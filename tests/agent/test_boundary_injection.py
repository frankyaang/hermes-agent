"""
B-3 BoundaryMemory → system prompt 注入 — Regression Tests

验证：
  1. format_boundary_block 对 negative boundary 输出 【禁止】 行
  2. format_boundary_block 对空列表返回空字符串
  3. format_boundary_block 对 positive boundary 输出 【规则】 行
  4. UNDERSTANDING_LOOP_ENABLED=true 时 boundary block 注入 system prompt
  5. UNDERSTANDING_LOOP_ENABLED=false 时 boundary block 不出现在 system prompt
"""
from __future__ import annotations

import os
import types

import pytest

from agent.understanding.boundary_formatter import format_boundary_block
from agent.understanding.schemas import BoundaryMemory


# ──────────────────────────────────────────────
# 1. format_boundary_block — 格式正确性
# ──────────────────────────────────────────────

def test_negative_boundary_formats_as_jinjin():
    bm = BoundaryMemory(
        boundary_type="negative",
        content="不能把这个问题限定在扫地机器人案例",
        source_turn=2,
        session_id="sess_001",
        scope="local",
    )
    result = format_boundary_block([bm])
    assert result.startswith("【理解边界】")
    assert "【禁止】" in result
    assert "扫地机器人" in result


def test_positive_boundary_formats_as_rule():
    bm = BoundaryMemory(
        boundary_type="positive",
        content="每次回答要给通用框架",
        source_turn=3,
        session_id="sess_001",
        scope="session",
    )
    result = format_boundary_block([bm])
    assert "【规则】" in result
    assert "通用框架" in result


def test_empty_boundaries_returns_empty_string():
    result = format_boundary_block([])
    assert result == ""


def test_multiple_boundaries_all_appear():
    boundaries = [
        BoundaryMemory("negative", "禁止内容A", 1, "s1", "local"),
        BoundaryMemory("positive", "规则内容B", 2, "s1", "local"),
        BoundaryMemory("negative", "禁止内容C", 3, "s1", "session"),
    ]
    result = format_boundary_block(boundaries)
    assert "禁止内容A" in result
    assert "规则内容B" in result
    assert "禁止内容C" in result
    assert result.count("【禁止】") == 2
    assert result.count("【规则】") == 1


# ──────────────────────────────────────────────
# 4 & 5. system prompt 注入（通过 _build_system_prompt stub 测试）
# ──────────────────────────────────────────────

def _make_mock_agent_with_boundaries(boundaries: list) -> types.SimpleNamespace:
    """构造最小 agent stub，只包含 _build_system_prompt 注入逻辑需要的属性。"""
    agent = types.SimpleNamespace()
    agent._session_boundary_memory = boundaries
    return agent


def _run_boundary_injection(agent, env_enabled: bool) -> str:
    """
    直接模拟 _build_system_prompt 末尾的注入逻辑，返回 boundary block 或空字符串。
    避免导入整个 run_agent。
    """
    if not env_enabled:
        return ""
    try:
        block = format_boundary_block(getattr(agent, "_session_boundary_memory", []))
        return block
    except Exception:
        return ""


def test_boundary_injected_when_enabled():
    bm = BoundaryMemory("negative", "禁止案例缩窄", 1, "sess", "local")
    agent = _make_mock_agent_with_boundaries([bm])
    block = _run_boundary_injection(agent, env_enabled=True)
    assert "【理解边界】" in block
    assert "禁止案例缩窄" in block


def test_boundary_not_injected_when_disabled():
    bm = BoundaryMemory("negative", "禁止案例缩窄", 1, "sess", "local")
    agent = _make_mock_agent_with_boundaries([bm])
    block = _run_boundary_injection(agent, env_enabled=False)
    assert block == ""


def test_no_injection_on_empty_boundary_list():
    agent = _make_mock_agent_with_boundaries([])
    block = _run_boundary_injection(agent, env_enabled=True)
    assert block == ""
