"""
Quality Convergence Mechanism Tests

验证多轮质量改进机制作为通用收敛引擎：
  1. separation_correction 后 split_frame=True，后续混题答案被检测
  2. generalization_correction 后 widen_scope=True，后续缩回案例被检测
  3. 纠偏记录跨轮次保留（BoundaryMemory 在 session 内存中持续有效）
  4. boundary_violation 阻止历史否定路径重现
  5. 无需人工干预即可收敛：gate 改写产出干净答案
"""
from __future__ import annotations

import pytest

from agent.understanding.candidate_answer_evaluator import evaluate_candidate_answer
from agent.understanding.correction_classifier import classify_correction
from agent.understanding.quality_loop_gated import apply_quality_gate
from agent.understanding.schemas import BoundaryMemory, UnderstandingState
from agent.understanding.user_quality_function import (
    UserQualityFunction,
    derive_quality_function,
)


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数：模拟 session 内 correction 处理流水线
# ──────────────────────────────────────────────────────────────────────────────

def _process_correction(
    user_msg: str,
    state: UnderstandingState,
    boundary_memory: list[BoundaryMemory],
    turn_index: int = 1,
) -> None:
    """模拟 run_agent.py 的 _classify_and_log_correction 逻辑。"""
    correction = classify_correction(user_msg, turn_index=turn_index)
    state.update_from_correction(correction)

    if correction.correction_type != "none" and correction.correction_type != "regression_correction":
        bm = BoundaryMemory(
            session_id="test-session",
            boundary_type="negative",
            content=user_msg[:200],
            source_turn=turn_index,
            scope=correction.scope,
        )
        boundary_memory.append(bm)


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: separation_correction → split_frame=True → 后续混题答案被检测
# ──────────────────────────────────────────────────────────────────────────────

def test_separation_correction_propagates_across_turns():
    state = UnderstandingState()
    boundary_memory: list[BoundaryMemory] = []

    # 轮 1：用户要求分别处理
    _process_correction(
        "这两个问题要分别思考，不要把它们混在一起回答",
        state, boundary_memory, turn_index=1,
    )
    assert state.split_frame is True

    # 轮 2：派生质量函数 → 检测混题
    qf = derive_quality_function(state, boundary_memory)
    assert qf.must_separate_questions is True

    # 候选答案：混题
    mixed = "综合来看，这两个问题的答案是一样的，我们可以统一处理。"
    eval_result = evaluate_candidate_answer(
        candidate_answer=mixed,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
    )
    assert eval_result.overall_pass is False
    assert "mixed_questions" in eval_result.failed_checks


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: generalization_correction → widen_scope=True → 后续缩回案例被检测
# ──────────────────────────────────────────────────────────────────────────────

def test_generalization_correction_propagates_across_turns():
    state = UnderstandingState()
    boundary_memory: list[BoundaryMemory] = []

    # 轮 1：用户要求更通用
    _process_correction(
        "你的回答太具体了，应该给出更通用的解决方案",
        state, boundary_memory, turn_index=1,
    )
    assert state.widen_scope is True

    # 轮 2：派生质量函数
    qf = derive_quality_function(state, boundary_memory)
    assert qf.must_keep_generalized_scope is True

    # 候选答案：缩回单一案例（匹配 _SCOPE_REGRESSION_RE pattern 2: "例如.{0-8}这个案例"）
    narrow = "例如，扫地机器人这个案例中，价格弹性约为 -1.2。"
    eval_result = evaluate_candidate_answer(
        candidate_answer=narrow,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
    )
    assert eval_result.overall_pass is False
    assert "scope_regression" in eval_result.failed_checks


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: BoundaryMemory 在 session 内跨多轮保留
# ──────────────────────────────────────────────────────────────────────────────

def test_boundary_memory_persists_across_turns():
    state = UnderstandingState()
    boundary_memory: list[BoundaryMemory] = []

    # 轮 1
    _process_correction("不要混在一起，分开处理", state, boundary_memory, turn_index=1)
    count_after_turn1 = len(boundary_memory)
    assert count_after_turn1 == 1

    # 轮 2（新的普通消息）
    _process_correction("好的，那这个问题怎么解决", state, boundary_memory, turn_index=2)
    # 非纠偏消息不添加 boundary
    assert len(boundary_memory) == count_after_turn1

    # 轮 3（新的纠偏）
    _process_correction("你的答案太浅了，要更深入分析", state, boundary_memory, turn_index=3)
    assert len(boundary_memory) == 2

    # 所有轮次的 boundary 都还在
    assert any("混在一起" in bm.content for bm in boundary_memory)


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: boundary_violation 阻止历史否定路径重现
# ──────────────────────────────────────────────────────────────────────────────

def test_boundary_violation_blocks_denied_path():
    state = UnderstandingState()
    boundary_memory: list[BoundaryMemory] = []

    # 轮 1：用户明确否定"价格弹性"这个解释路径
    _process_correction(
        "不要局限在价格弹性这个概念，用更通用的方式分析",
        state, boundary_memory, turn_index=1,
    )

    qf = derive_quality_function(state, boundary_memory)
    # must_avoid_negative_boundaries 应包含否定内容
    assert len(qf.must_avoid_negative_boundaries) > 0

    # 轮 2 候选答案：重新引用被否定的路径
    violating = "从价格弹性角度来看，弹性系数为 -0.8，说明需求对价格敏感。"
    eval_result = evaluate_candidate_answer(
        candidate_answer=violating,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
    )
    assert eval_result.overall_pass is False
    assert "boundary_violation" in eval_result.failed_checks


# ──────────────────────────────────────────────────────────────────────────────
# Test 5: 无需人工干预即收敛 — gate + mock rewrite 产出干净答案
# ──────────────────────────────────────────────────────────────────────────────

def test_convergence_without_manual_copying(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    state = UnderstandingState()
    boundary_memory: list[BoundaryMemory] = []

    # 模拟：用户曾发出 separation_correction
    _process_correction(
        "这两个问题要分别思考，不要把它们混在一起",
        state, boundary_memory, turn_index=1,
    )

    qf = derive_quality_function(state, boundary_memory)
    low_quality = "综合来看，两个问题的答案是相同的：都需要降低成本。"
    clean_answer = "问题1：降低成本的策略是精简供应链。\n问题2：提升利润的方法是涨价。"

    def mock_rewrite(original: str, guidance: str) -> str:
        return clean_answer

    final_answer, eval_result = apply_quality_gate(
        candidate_answer=low_quality,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
        llm_rewrite_fn=mock_rewrite,
    )

    assert eval_result.overall_pass is False          # 检测到混题
    assert final_answer == clean_answer               # gate 自动改写
    assert "综合来看" not in final_answer             # 低质量内容不出现
    assert "问题1" in final_answer and "问题2" in final_answer  # 分别回答
