"""
IssueExtractor Runtime Tests

验证 issue_extractor 的 runtime 行为：
  1. llm_call_fn=None 时使用默认路径（不抛 RuntimeError）
  2. 默认路径：anthropic 不可用时 fallback 返回空列表
  3. 有效 JSON 输出 → 返回正确 Issue 列表
  4. 无效 JSON → 空列表（安全降级）
  5. 非数组 JSON → 空列表
  6. schema 验证失败的 item 被跳过
  7. recommended_option / owner_candidate 原文无明文 → null（不推断）
  8. acceptance_criteria 缺失 → None（不推断）
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent_system.skills.issue_extractor.skill import extract_issues


# ──────────────────────────────────────────────────────────────────────────────
# 1. llm_call_fn=None 时使用默认路径（不再抛 RuntimeError）
# ──────────────────────────────────────────────────────────────────────────────

def test_no_llm_call_fn_does_not_raise():
    """默认路径存在：不抛 RuntimeError，即使 anthropic 不可用也返回空列表。"""
    with patch("agent_system.skills.issue_extractor.skill._make_default_llm_call") as mock_make:
        mock_make.return_value = lambda p: "[]"
        result = extract_issues("周报原材料", source_ref="weekly_test")
    assert isinstance(result, list)


# ──────────────────────────────────────────────────────────────────────────────
# 2. 默认路径：anthropic 不可用时 fallback 返回空列表
# ──────────────────────────────────────────────────────────────────────────────

def test_default_llm_call_fallback_when_anthropic_unavailable():
    """_make_default_llm_call 在 Anthropic 初始化失败时返回 noop（→ 空列表）。"""
    from agent_system.skills.issue_extractor.skill import _make_default_llm_call

    with patch("anthropic.Anthropic", side_effect=Exception("API key not found")):
        fn = _make_default_llm_call()

    result = fn("任意 prompt")
    assert result == "[]"


# ──────────────────────────────────────────────────────────────────────────────
# 3. 有效 JSON 输出 → 返回正确 Issue 列表
# ──────────────────────────────────────────────────────────────────────────────

def test_valid_json_returns_issue_list():
    llm_output = json.dumps([
        {
            "title": "X11 海外配件定价策略",
            "background": "当前配件利润率低于目标 5pp",
            "source_ref": "weekly_2026_w20",
            "urgency": "high",
            "options": ["方案A：维持现价", "方案B：涨价 8%"],
            "recommended_option": "方案B：涨价 8%，捆绑促销",
            "owner_candidate": "张三",
            "acceptance_criteria": "Q3 配件毛利率达到 35%",
        }
    ])

    result = extract_issues("原材料", llm_call_fn=lambda p: llm_output)
    assert len(result) == 1
    assert result[0].title == "X11 海外配件定价策略"
    assert result[0].recommended_option == "方案B：涨价 8%，捆绑促销"
    assert result[0].owner_candidate == "张三"
    assert result[0].acceptance_criteria == "Q3 配件毛利率达到 35%"


# ──────────────────────────────────────────────────────────────────────────────
# 4. 无效 JSON → 空列表
# ──────────────────────────────────────────────────────────────────────────────

def test_invalid_json_returns_empty_list():
    result = extract_issues("原材料", llm_call_fn=lambda p: "not valid json {{")
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# 5. 非数组 JSON → 空列表
# ──────────────────────────────────────────────────────────────────────────────

def test_non_array_json_returns_empty_list():
    result = extract_issues("原材料", llm_call_fn=lambda p: '{"key": "value"}')
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# 6. schema 验证失败的 item 被跳过，其余正常
# ──────────────────────────────────────────────────────────────────────────────

def test_schema_invalid_item_skipped_others_kept():
    llm_output = json.dumps([
        {"title": ""},   # 空 title → 验证失败
        {"title": "合法议题", "background": "背景", "source_ref": "w20",
         "urgency": "high", "options": [], "recommended_option": None,
         "owner_candidate": None, "acceptance_criteria": None},
    ])
    result = extract_issues("原材料", llm_call_fn=lambda p: llm_output)
    assert len(result) == 1
    assert result[0].title == "合法议题"


# ──────────────────────────────────────────────────────────────────────────────
# 7. recommended_option / owner_candidate 原文无明文 → null（不推断）
# ──────────────────────────────────────────────────────────────────────────────

def test_null_fields_not_inferred():
    llm_output = json.dumps([{
        "title": "库存积压议题",
        "background": "配件库存积压",
        "source_ref": "w20",
        "urgency": "medium",
        "options": [],
        "recommended_option": None,
        "owner_candidate": None,
        "acceptance_criteria": None,
    }])
    result = extract_issues("原材料", llm_call_fn=lambda p: llm_output)
    assert len(result) == 1
    assert result[0].recommended_option is None
    assert result[0].owner_candidate is None
    assert result[0].acceptance_criteria is None


# ──────────────────────────────────────────────────────────────────────────────
# 8. 空原材料 → LLM 返回空数组 → 空列表
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_material_returns_empty_list():
    result = extract_issues("", llm_call_fn=lambda p: "[]")
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# 9. _make_default_llm_call 应通过 hermes_llm_provider（P0-2 RED）
# ──────────────────────────────────────────────────────────────────────────────

def test_default_llm_call_uses_hermes_provider():
    """_make_default_llm_call 必须委托给 hermes_llm_provider.make_hermes_llm_call。
    RED：hermes_llm_provider 模块不存在时 ImportError → FAIL。
    """
    from agent_system.providers.hermes_llm_provider import make_hermes_llm_call  # FAIL until P0-2
    assert callable(make_hermes_llm_call)


# ──────────────────────────────────────────────────────────────────────────────
# 10. hermes_llm_provider 尊重 HERMES_SKILL_LLM_MODEL env var（P0-2 RED）
# ──────────────────────────────────────────────────────────────────────────────

def test_hermes_provider_respects_model_env_var(monkeypatch):
    """make_hermes_llm_call 使用 HERMES_SKILL_LLM_MODEL env var 作为 model。
    RED：hermes_llm_provider 不存在时 ImportError → FAIL。
    """
    from agent_system.providers.hermes_llm_provider import make_hermes_llm_call
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("HERMES_SKILL_LLM_MODEL", "claude-opus-test-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text="[]")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_resp

    with patch("anthropic.Anthropic", return_value=mock_client):
        fn = make_hermes_llm_call()
        fn("test prompt")

    call_kwargs = mock_client.messages.create.call_args
    used_model = call_kwargs[1].get("model") or call_kwargs[0][0] if call_kwargs[0] else None
    if used_model is None and call_kwargs[1]:
        used_model = call_kwargs[1].get("model")
    assert used_model == "claude-opus-test-model", (
        f"应使用 HERMES_SKILL_LLM_MODEL=claude-opus-test-model，实际 model={used_model}"
    )
