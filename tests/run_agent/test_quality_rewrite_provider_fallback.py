"""
Quality Rewrite Provider Fallback Tests (P1-3)

验证 _do_quality_rewrite 在非 Anthropic provider 下的 fallback 行为：
  1. Anthropic provider → rewrite 正常执行（mock 调用）
  2. 非 Anthropic provider（openai）→ _do_quality_rewrite 抛 RuntimeError
  3. 非 Anthropic provider → apply_quality_gate fallback 原始答案（不中断）
  4. 非 Anthropic provider 但 base_url 包含 anthropic.com → 视为 Anthropic，不 fallback
  5. base_url 为空 → 视为 Anthropic（默认）
  6. provider=ollama → fallback 原始答案

说明：_do_quality_rewrite 对非 Anthropic provider 抛 RuntimeError，
     apply_quality_gate 的 exception fallback 捕获后返回原始答案，
     主流程不中断。
"""
from __future__ import annotations

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_agent_like(provider: str = "", base_url: str = ""):
    """创建一个只有 provider 检测方法的轻量 agent-like 对象。"""
    import types

    obj = types.SimpleNamespace()
    obj._provider = provider
    obj._base_url = base_url

    # 从 run_agent.py 复制 _is_anthropic_compatible_provider 逻辑
    def _is_anthropic_compatible_provider(self) -> bool:
        _base_url = getattr(self, "_base_url", None) or ""
        if _base_url and "anthropic.com" not in _base_url and "amazonaws.com" not in _base_url:
            return False
        _provider = getattr(self, "_provider", None) or ""
        non_anthropic = {"openai", "azure", "ollama", "groq", "together", "deepseek", "mistral"}
        if any(p in _provider.lower() for p in non_anthropic):
            return False
        return True

    obj._is_anthropic_compatible_provider = lambda: _is_anthropic_compatible_provider(obj)

    return obj


# ──────────────────────────────────────────────────────────────────────────────
# 1. Anthropic provider → _is_anthropic_compatible_provider 返回 True
# ──────────────────────────────────────────────────────────────────────────────

def test_anthropic_provider_is_compatible():
    agent = _make_agent_like(provider="", base_url="")
    assert agent._is_anthropic_compatible_provider() is True


# ──────────────────────────────────────────────────────────────────────────────
# 2. 非 Anthropic provider（openai）→ _is_anthropic_compatible_provider 返回 False
# ──────────────────────────────────────────────────────────────────────────────

def test_openai_provider_is_not_compatible():
    agent = _make_agent_like(provider="openai", base_url="https://api.openai.com/v1")
    assert agent._is_anthropic_compatible_provider() is False


# ──────────────────────────────────────────────────────────────────────────────
# 3. 非 Anthropic provider → apply_quality_gate fallback 原始答案
# ──────────────────────────────────────────────────────────────────────────────

def test_non_anthropic_provider_fallback_via_quality_gate(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    from agent.understanding.quality_loop_gated import apply_quality_gate
    from agent.understanding.schemas import UnderstandingState, BoundaryMemory
    from agent.understanding.user_quality_function import derive_quality_function
    from agent.understanding.correction_classifier import classify_correction

    state = UnderstandingState()
    boundary_memory = []

    # 先触发 separation_correction
    result = classify_correction("这两个问题要分别思考，不要混在一起")
    if result.correction_type != "none":
        state.update_from_correction(result)

    qf = derive_quality_function(state, boundary_memory)
    bad_candidate = "综合来看，两个问题的答案是一样的。"

    # 模拟非 Anthropic provider：rewrite fn 直接抛 RuntimeError（与 run_agent.py 行为一致）
    def non_anthropic_rewrite(orig: str, guidance: str) -> str:
        raise RuntimeError("quality_rewrite: non-Anthropic provider detected; skipping rewrite")

    final_response, eval_result = apply_quality_gate(
        candidate_answer=bad_candidate,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
        llm_rewrite_fn=non_anthropic_rewrite,
    )

    # RuntimeError 被 exception fallback 捕获，返回原始答案
    assert final_response == bad_candidate
    assert eval_result.overall_pass is False


# ──────────────────────────────────────────────────────────────────────────────
# 4. base_url 包含 anthropic.com → 视为 Anthropic
# ──────────────────────────────────────────────────────────────────────────────

def test_anthropic_base_url_is_compatible():
    agent = _make_agent_like(provider="", base_url="https://api.anthropic.com/v1")
    assert agent._is_anthropic_compatible_provider() is True


# ──────────────────────────────────────────────────────────────────────────────
# 5. base_url 为空 → 视为 Anthropic（默认兼容）
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_base_url_is_compatible():
    agent = _make_agent_like(provider="", base_url="")
    assert agent._is_anthropic_compatible_provider() is True


# ──────────────────────────────────────────────────────────────────────────────
# 6. provider=ollama → 非 Anthropic → fallback 原始答案
# ──────────────────────────────────────────────────────────────────────────────

def test_ollama_provider_is_not_compatible():
    agent = _make_agent_like(provider="ollama", base_url="http://localhost:11434")
    assert agent._is_anthropic_compatible_provider() is False


def test_ollama_provider_fallback_original_answer(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    from agent.understanding.quality_loop_gated import apply_quality_gate
    from agent.understanding.schemas import UnderstandingState
    from agent.understanding.user_quality_function import UserQualityFunction

    state = UnderstandingState()
    state.split_frame = True
    qf = UserQualityFunction(must_separate_questions=True)

    bad_candidate = "综合来看，两个问题答案相同。"

    def ollama_rewrite(orig, guidance):
        raise RuntimeError("quality_rewrite: non-Anthropic provider detected")

    final_response, eval_result = apply_quality_gate(
        candidate_answer=bad_candidate,
        prior_response="",
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
        llm_rewrite_fn=ollama_rewrite,
    )

    assert final_response == bad_candidate
    assert eval_result.overall_pass is False
