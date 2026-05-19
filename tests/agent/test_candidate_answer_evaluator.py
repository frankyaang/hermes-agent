"""
CandidateAnswerEvaluator — Unit Tests

验证 6 项检测逻辑和 rewrite_or_clarify 决策。
"""
from __future__ import annotations

from agent.understanding.candidate_answer_evaluator import evaluate_candidate_answer
from agent.understanding.schemas import BoundaryMemory, UnderstandingState
from agent.understanding.user_quality_function import UserQualityFunction, derive_quality_function


def _qf(**kwargs) -> UserQualityFunction:
    qf = UserQualityFunction()
    for k, v in kwargs.items():
        setattr(qf, k, v)
    return qf


def _eval(candidate: str, prior: str = "", qf: UserQualityFunction | None = None, **state_kwargs):
    if qf is None:
        qf = UserQualityFunction()
    state = UnderstandingState()
    for k, v in state_kwargs.items():
        setattr(state, k, v)
    return evaluate_candidate_answer(
        candidate_answer=candidate,
        prior_response=prior,
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
    )


# 1. 干净回答全部通过
def test_clean_answer_passes_all_checks():
    result = _eval("这是一个干净的回答，没有任何问题。")
    assert result.overall_pass is True
    assert result.failed_checks == []
    assert result.rewrite_or_clarify == "pass"


# 2. 混题检测
def test_mixed_questions_detected():
    qf = _qf(must_separate_questions=True)
    result = _eval("综合来看，这两个问题的答案是一样的。", qf=qf)
    assert result.overall_pass is False
    assert "mixed_questions" in result.failed_checks
    assert result.rewrite_or_clarify == "rewrite"


# 3. 范围回退检测
def test_scope_regression_detected():
    qf = _qf(must_keep_generalized_scope=True)
    result = _eval("以扫地机器人为例，这个问题的解法是...", qf=qf)
    assert result.overall_pass is False
    assert "scope_regression" in result.failed_checks
    assert result.rewrite_or_clarify == "rewrite"


# 4. boundary violation 检测
def test_boundary_violation_detected():
    qf = _qf(must_avoid_negative_boundaries=["不能把这个问题限定在扫地机器人案例"])
    result = _eval("扫地机器人案例说明了这个问题的核心。", qf=qf)
    assert result.overall_pass is False
    assert "boundary_violation" in result.failed_checks
    assert result.rewrite_or_clarify == "rewrite"


# 5. 同义复述检测
def test_synonym_paraphrase_detected():
    prior = "用户的核心诉求是价格敏感性，对价格变化较为敏感"
    candidate = "用户的核心诉求是价格敏感性，对价格变化较为敏感，需要特别关注"
    qf = _qf(must_avoid_synonym_paraphrase=True)
    result = _eval(candidate, prior=prior, qf=qf)
    assert result.overall_pass is False
    assert "synonym_paraphrase" in result.failed_checks
    assert result.rewrite_or_clarify == "rewrite"


# 6. 缺少新系统层检测
def test_missing_new_system_layer_detected():
    qf = _qf(must_add_new_system_layer=True)
    result = _eval("这个问题可以通过调整现有逻辑解决。", qf=qf)
    assert result.overall_pass is False
    assert "missing_new_system_layer" in result.failed_checks
    assert result.rewrite_or_clarify == "clarify"


# 7. 缺少 agent system 机制检测
def test_missing_agent_system_mechanism_detected():
    qf = _qf(must_use_agent_system_mechanism=True)
    result = _eval("建议用函数封装这个逻辑。", qf=qf)
    assert result.overall_pass is False
    assert "missing_agent_system_mechanism" in result.failed_checks
    assert result.rewrite_or_clarify == "clarify"


# 8. 失败时 rewrite_guidance 被填充
def test_rewrite_guidance_populated_on_failure():
    qf = _qf(must_separate_questions=True)
    result = _eval("综合来看两个问题本质相同。", qf=qf)
    assert result.overall_pass is False
    assert result.rewrite_guidance.startswith("【修复建议】")
    assert "mixed_questions" in result.rewrite_guidance
