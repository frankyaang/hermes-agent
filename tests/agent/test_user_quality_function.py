"""
UserQualityFunction — Unit Tests

验证 derive_quality_function() 正确从 UnderstandingState + BoundaryMemory 派生质量要求。
"""
from __future__ import annotations

from agent.understanding.schemas import BoundaryMemory, UnderstandingState
from agent.understanding.user_quality_function import UserQualityFunction, derive_quality_function


def _state(**kwargs) -> UnderstandingState:
    s = UnderstandingState()
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def _neg_boundary(content: str) -> BoundaryMemory:
    return BoundaryMemory(
        boundary_id="b1",
        session_id="s1",
        boundary_type="negative",
        content=content,
        source_turn=1,
        scope="local",
    )


# 1. separation_correction → must_separate_questions
def test_separation_correction_sets_must_separate_questions():
    state = _state(split_frame=True)
    qf = derive_quality_function(state, [])
    assert qf.must_separate_questions is True


# 2. generalization_correction → must_keep_generalized_scope
def test_generalization_correction_sets_must_keep_generalized_scope():
    state = _state(widen_scope=True)
    qf = derive_quality_function(state, [])
    assert qf.must_keep_generalized_scope is True


# 3. negative boundary 填充 must_avoid_negative_boundaries
def test_negative_boundary_populates_must_avoid_list():
    state = _state()
    bm = _neg_boundary("不能把这个问题限定在扫地机器人案例")
    qf = derive_quality_function(state, [bm])
    assert len(qf.must_avoid_negative_boundaries) == 1
    assert "扫地机器人" in qf.must_avoid_negative_boundaries[0]


# 4. 新系统层关键词 → must_add_new_system_layer
def test_system_layer_keyword_sets_must_add_new_system_layer():
    state = _state(negative_boundaries=["需要新的系统层来处理这个问题"])
    qf = derive_quality_function(state, [])
    assert qf.must_add_new_system_layer is True


# 5. agent system 关键词 → must_use_agent_system_mechanism
def test_agent_system_keyword_sets_must_use_agent_system():
    state = _state()
    bm = _neg_boundary("应该通过 pipeline 节点来实现，而不是内联代码")
    qf = derive_quality_function(state, [bm])
    assert qf.must_use_agent_system_mechanism is True


# 6. 空状态 → 全部 False
def test_empty_state_all_false():
    qf = derive_quality_function(UnderstandingState(), [])
    assert qf.must_separate_questions is False
    assert qf.must_keep_generalized_scope is False
    assert qf.must_avoid_synonym_paraphrase is False
    assert qf.must_add_new_system_layer is False
    assert qf.must_use_agent_system_mechanism is False
    assert qf.must_avoid_negative_boundaries == []
