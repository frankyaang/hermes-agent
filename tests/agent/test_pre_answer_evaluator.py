"""
B-4 PreAnswerEvaluation — Regression Tests

覆盖：
  1. 无违规时 overall_pass=True
  2. split_frame=True + 混题关键词 → check_mixed_questions=True
  3. split_frame=False 时不触发混题检测
  4. negative boundary 关键词出现在 draft → check_boundary_violation=True
  5. widen_scope=True + 单一案例词 → check_scope_regression=True
  6. 任一检测触发 → overall_pass=False
  7. synonym_paraphrase 只在 confidence > 0.9 时触发
"""
from __future__ import annotations

import pytest

from agent.understanding.pre_answer_evaluator import evaluate_pre_answer
from agent.understanding.schemas import BoundaryMemory, UnderstandingState


def _messages(assistant_text: str) -> list:
    return [{"role": "assistant", "content": assistant_text}]


def _state(**kwargs) -> UnderstandingState:
    defaults = dict(confidence=0.5, split_frame=False, widen_scope=False)
    defaults.update(kwargs)
    return UnderstandingState(**defaults)


# ──────────────────────────────────────────────
# 1. 无违规时 overall_pass=True
# ──────────────────────────────────────────────

def test_eval_pass_on_clean_draft():
    result = evaluate_pre_answer(
        draft_messages=_messages("这是一个关于定价策略的分析。"),
        understanding_state=_state(),
        boundary_memory=[],
    )
    assert result.overall_pass is True
    assert result.check_mixed_questions is False
    assert result.check_boundary_violation is False
    assert result.check_scope_regression is False
    assert result.check_synonym_paraphrase is False


# ──────────────────────────────────────────────
# 2. split_frame=True + 混题关键词 → check_mixed_questions=True
# ──────────────────────────────────────────────

def test_detect_mixed_questions_when_split_frame_true():
    result = evaluate_pre_answer(
        draft_messages=_messages("综合来看，问题1和问题2都指向同一个根因。"),
        understanding_state=_state(split_frame=True),
        boundary_memory=[],
    )
    assert result.check_mixed_questions is True
    assert result.overall_pass is False


def test_mixed_questions_not_triggered_without_keywords():
    result = evaluate_pre_answer(
        draft_messages=_messages("定价策略需要考虑成本和市场需求两个维度。"),
        understanding_state=_state(split_frame=True),
        boundary_memory=[],
    )
    assert result.check_mixed_questions is False


# ──────────────────────────────────────────────
# 3. split_frame=False 时不触发混题检测
# ──────────────────────────────────────────────

def test_no_mixed_question_flag_when_split_frame_false():
    result = evaluate_pre_answer(
        draft_messages=_messages("综合来看，问题1和问题2需要一起分析。"),
        understanding_state=_state(split_frame=False),
        boundary_memory=[],
    )
    assert result.check_mixed_questions is False


# ──────────────────────────────────────────────
# 4. negative boundary 关键词出现在 draft → check_boundary_violation=True
# ──────────────────────────────────────────────

def test_detect_boundary_violation():
    bm = BoundaryMemory(
        boundary_type="negative",
        content="不能把这个问题限定在扫地机器人案例",
        source_turn=2,
        session_id="sess_001",
        scope="local",
    )
    result = evaluate_pre_answer(
        draft_messages=_messages("以扫地机器人为例，我们来分析这个问题的解法。"),
        understanding_state=_state(),
        boundary_memory=[bm],
    )
    assert result.check_boundary_violation is True
    assert result.overall_pass is False


def test_no_boundary_violation_when_content_differs():
    bm = BoundaryMemory(
        boundary_type="negative",
        content="不能把问题限定在扫地机器人",
        source_turn=2,
        session_id="sess_001",
        scope="local",
    )
    result = evaluate_pre_answer(
        draft_messages=_messages("这个定价策略适用于多个产品线。"),
        understanding_state=_state(),
        boundary_memory=[bm],
    )
    assert result.check_boundary_violation is False


def test_positive_boundary_does_not_trigger_violation():
    bm = BoundaryMemory(
        boundary_type="positive",
        content="每次要给通用框架",
        source_turn=2,
        session_id="sess_001",
        scope="local",
    )
    result = evaluate_pre_answer(
        draft_messages=_messages("通用框架的核心是抽象出共同模式。"),
        understanding_state=_state(),
        boundary_memory=[bm],
    )
    assert result.check_boundary_violation is False


# ──────────────────────────────────────────────
# 5. widen_scope=True + 单一案例词 → check_scope_regression=True
# ──────────────────────────────────────────────

def test_detect_scope_regression_when_widen_scope_true():
    result = evaluate_pre_answer(
        draft_messages=_messages("以扫地机器人的案例为例，可以看出这个规律。"),
        understanding_state=_state(widen_scope=True),
        boundary_memory=[],
    )
    assert result.check_scope_regression is True
    assert result.overall_pass is False


def test_no_scope_regression_when_widen_scope_false():
    result = evaluate_pre_answer(
        draft_messages=_messages("以扫地机器人的案例为例。"),
        understanding_state=_state(widen_scope=False),
        boundary_memory=[],
    )
    assert result.check_scope_regression is False


# ──────────────────────────────────────────────
# 6. 任一检测触发 → overall_pass=False
# ──────────────────────────────────────────────

def test_overall_pass_false_when_any_check_triggered():
    result = evaluate_pre_answer(
        draft_messages=_messages("综合来看，两个问题一起分析。"),
        understanding_state=_state(split_frame=True),
        boundary_memory=[],
    )
    assert result.overall_pass is False


# ──────────────────────────────────────────────
# 7. synonym_paraphrase 只在 confidence > 0.9 时触发
# ──────────────────────────────────────────────

def test_synonym_paraphrase_triggered_at_high_confidence():
    prior = "用户的核心诉求是价格敏感性，对价格变化较为敏感。"
    draft = "用户最关心的是价格因素，对价格变化非常敏感，价格敏感性是核心诉求。"
    result = evaluate_pre_answer(
        draft_messages=_messages(draft),
        understanding_state=_state(confidence=0.95),
        boundary_memory=[],
        prior_response=prior,
    )
    assert result.check_synonym_paraphrase is True


def test_synonym_paraphrase_not_triggered_at_low_confidence():
    prior = "用户的核心诉求是价格敏感性，对价格变化较为敏感。"
    draft = "用户最关心的是价格因素，对价格变化非常敏感，价格敏感性是核心诉求。"
    result = evaluate_pre_answer(
        draft_messages=_messages(draft),
        understanding_state=_state(confidence=0.5),
        boundary_memory=[],
        prior_response=prior,
    )
    assert result.check_synonym_paraphrase is False


def test_none_understanding_state_skips_state_checks():
    result = evaluate_pre_answer(
        draft_messages=_messages("综合来看，两个问题一起分析。"),
        understanding_state=None,
        boundary_memory=[],
    )
    assert result.check_mixed_questions is False
    assert result.check_scope_regression is False
    assert result.overall_pass is True
