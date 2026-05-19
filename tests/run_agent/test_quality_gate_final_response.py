"""
Quality Gate Final Response Tests — Phase 5

验证 apply_quality_gate 的 llm_rewrite_fn 接入和输出质量：
  1. QUALITY_LOOP_GATED=false → 输出 == 输入
  2. QUALITY_LOOP_GATED=true + pass → 输出 == 输入
  3. QUALITY_LOOP_GATED=true + fail + mock fn → 输出 == mock 干净答案
  4. fail 路径输出不包含 "【修复建议】" 前缀
  5. llm_rewrite_fn 抛异常 → fallback 原始答案
  6. is_streaming=True → 不修改输出（log only）
"""
from __future__ import annotations

import pytest

from agent.understanding.quality_loop_gated import apply_quality_gate
from agent.understanding.schemas import BoundaryMemory, UnderstandingState
from agent.understanding.user_quality_function import UserQualityFunction


def _mixed_question_answer() -> str:
    return "综合来看，这两个问题的答案是一样的，我们可以一起解决。"


def _clean_answer() -> str:
    return "这是一个干净的回答，没有任何质量问题。"


def _make_qf_separate() -> UserQualityFunction:
    qf = UserQualityFunction()
    qf.must_separate_questions = True
    return qf


# ──────────────────────────────────────────────
# 1. QUALITY_LOOP_GATED=false → 输出不变
# ──────────────────────────────────────────────

def test_gated_false_response_unchanged(monkeypatch):
    monkeypatch.delenv("QUALITY_LOOP_GATED", raising=False)
    answer, eval_result = apply_quality_gate(
        candidate_answer=_mixed_question_answer(),
        prior_response="",
        understanding_state=UnderstandingState(),
        boundary_memory=[],
        quality_fn=_make_qf_separate(),
        llm_rewrite_fn=None,
    )
    assert answer == _mixed_question_answer()
    assert eval_result.overall_pass is True


# ──────────────────────────────────────────────
# 2. QUALITY_LOOP_GATED=true + 干净答案 → 输出不变
# ──────────────────────────────────────────────

def test_gated_true_pass_response_unchanged(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    answer, eval_result = apply_quality_gate(
        candidate_answer=_clean_answer(),
        prior_response="",
        understanding_state=UnderstandingState(),
        boundary_memory=[],
        quality_fn=_make_qf_separate(),
        llm_rewrite_fn=None,
    )
    assert answer == _clean_answer()
    assert eval_result.overall_pass is True


# ──────────────────────────────────────────────
# 3. QUALITY_LOOP_GATED=true + fail + mock fn → 输出是 mock 返回的干净答案
# ──────────────────────────────────────────────

def test_gated_true_fail_triggers_rewrite(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    def mock_rewrite(original: str, guidance: str) -> str:
        return "这是经过改写的干净答案，已正确分别回答两个问题。"

    answer, eval_result = apply_quality_gate(
        candidate_answer=_mixed_question_answer(),
        prior_response="",
        understanding_state=UnderstandingState(),
        boundary_memory=[],
        quality_fn=_make_qf_separate(),
        llm_rewrite_fn=mock_rewrite,
    )
    assert answer == "这是经过改写的干净答案，已正确分别回答两个问题。"
    assert eval_result.overall_pass is False
    assert "mixed_questions" in eval_result.failed_checks


# ──────────────────────────────────────────────
# 4. fail 路径输出不包含 "【修复建议】" 前缀
# ──────────────────────────────────────────────

def test_rewrite_output_is_not_guidance_plus_original(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    def mock_rewrite(original: str, guidance: str) -> str:
        return "这是干净的重写结果。"

    answer, _ = apply_quality_gate(
        candidate_answer=_mixed_question_answer(),
        prior_response="",
        understanding_state=UnderstandingState(),
        boundary_memory=[],
        quality_fn=_make_qf_separate(),
        llm_rewrite_fn=mock_rewrite,
    )
    assert "【修复建议】" not in answer
    assert "---" not in answer    # 不是 "建议 + 分隔符 + 原答案" 格式
    assert _mixed_question_answer() not in answer  # 不含原始低质量答案


# ──────────────────────────────────────────────
# 5. llm_rewrite_fn 抛异常 → fallback 原始答案
# ──────────────────────────────────────────────

def test_rewrite_exception_fallback_original(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    def failing_rewrite(original: str, guidance: str) -> str:
        raise RuntimeError("LLM call failed")

    answer, eval_result = apply_quality_gate(
        candidate_answer=_mixed_question_answer(),
        prior_response="",
        understanding_state=UnderstandingState(),
        boundary_memory=[],
        quality_fn=_make_qf_separate(),
        llm_rewrite_fn=failing_rewrite,
    )
    assert answer == _mixed_question_answer()   # fallback
    assert eval_result.overall_pass is False


# ──────────────────────────────────────────────
# 6. streaming 路径（llm_rewrite_fn=None）→ 不修改输出
# ──────────────────────────────────────────────

def test_streaming_path_logs_only(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    # streaming 场景：调用方不传 llm_rewrite_fn（安全降级）
    answer, eval_result = apply_quality_gate(
        candidate_answer=_mixed_question_answer(),
        prior_response="",
        understanding_state=UnderstandingState(),
        boundary_memory=[],
        quality_fn=_make_qf_separate(),
        llm_rewrite_fn=None,   # streaming: no rewrite fn provided
    )
    # 输出与输入相同（不修改已流出的内容）
    assert answer == _mixed_question_answer()
    # 但 evaluation 仍然反映真实结果
    assert eval_result.overall_pass is False
    assert "mixed_questions" in eval_result.failed_checks
