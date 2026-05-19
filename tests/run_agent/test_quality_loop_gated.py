"""
quality_loop_gated — Unit Tests

验证 QUALITY_LOOP_GATED 特性门控行为：
  1. QUALITY_LOOP_GATED=false → 返回原始回答，不做评估
  2. QUALITY_LOOP_GATED=false → evaluation.overall_pass=True（noop）
  3. QUALITY_LOOP_GATED=true + 通过 → 返回原始回答
  4. QUALITY_LOOP_GATED=true + 失败 → 返回 repair（前缀 rewrite_guidance）
  5. repair 异常 → fallback 原始回答
"""
from __future__ import annotations

import pytest

from agent.understanding.quality_loop_gated import apply_quality_gate
from agent.understanding.schemas import BoundaryMemory, UnderstandingState
from agent.understanding.user_quality_function import UserQualityFunction


def _args(candidate: str = "测试回答", prior: str = "", **qf_kwargs):
    state = UnderstandingState()
    qf = UserQualityFunction(**qf_kwargs)
    return dict(
        candidate_answer=candidate,
        prior_response=prior,
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
    )


# 1. QUALITY_LOOP_GATED=false → 返回原始回答
def test_gated_false_returns_original_answer(monkeypatch):
    monkeypatch.delenv("QUALITY_LOOP_GATED", raising=False)
    answer, _ = apply_quality_gate(**_args("原始回答"))
    assert answer == "原始回答"


# 2. QUALITY_LOOP_GATED=false → evaluation.overall_pass=True（noop）
def test_gated_false_does_not_evaluate(monkeypatch):
    monkeypatch.delenv("QUALITY_LOOP_GATED", raising=False)
    _, evaluation = apply_quality_gate(**_args())
    assert evaluation.overall_pass is True
    assert evaluation.failed_checks == []
    assert evaluation.rewrite_or_clarify == "pass"


# 3. QUALITY_LOOP_GATED=true + 通过 → 返回原始回答
def test_gated_true_pass_returns_original(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    answer, evaluation = apply_quality_gate(**_args("这是一个合格的回答，没有任何问题。"))
    assert answer == "这是一个合格的回答，没有任何问题。"
    assert evaluation.overall_pass is True


# 4. QUALITY_LOOP_GATED=true + 失败 + llm_rewrite_fn 提供 → 返回干净 rewrite
def test_gated_true_fail_returns_repaired_with_guidance(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    qf = UserQualityFunction(must_separate_questions=True)
    state = UnderstandingState()

    def mock_rewrite(original: str, guidance: str) -> str:
        return "这是干净的重写答案，两个问题已分别回答。"

    answer, evaluation = apply_quality_gate(
        candidate_answer="综合来看这两个问题的答案是一样的。",
        prior_response="",
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
        llm_rewrite_fn=mock_rewrite,
    )
    assert evaluation.overall_pass is False
    assert "mixed_questions" in evaluation.failed_checks
    # 新行为：输出是干净的重写结果，不是"建议 + 原答案"
    assert answer == "这是干净的重写答案，两个问题已分别回答。"
    assert "【修复建议】" not in answer
    assert "综合来看" not in answer   # 原始低质量内容不出现在输出中


# 5. repair 异常 → fallback 原始回答
def test_repair_exception_fallback_original(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    from unittest.mock import patch
    from agent.understanding import candidate_answer_evaluator as cae_mod
    from agent.understanding.candidate_answer_evaluator import CandidateAnswerEvaluation

    class _Explode:
        def __format__(self, spec: str) -> str:
            raise RuntimeError("intentional repair failure")

    failing_eval = CandidateAnswerEvaluation(
        overall_pass=False,
        failed_checks=["mixed_questions"],
        reason="mixed_questions",
        rewrite_guidance=_Explode(),  # type: ignore[arg-type]
        rewrite_or_clarify="rewrite",
    )

    with patch.object(cae_mod, "evaluate_candidate_answer", return_value=failing_eval):
        answer, evaluation = apply_quality_gate(
            candidate_answer="原始回答内容",
            prior_response="",
            understanding_state=UnderstandingState(),
            boundary_memory=[],
            quality_fn=UserQualityFunction(must_separate_questions=True),
        )

    assert answer == "原始回答内容"
    assert evaluation.overall_pass is False
