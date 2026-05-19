"""
CorrectionClassifier — Golden Fixtures & Regression Tests

覆盖：
  B1. separation_correction 识别
  B2. generalization_correction 识别
  B3. scope=local 默认；scope=global 需明确触发词
  B4. regression_correction 需要 prior_corrections 上下文
  B5. none 对正常消息

Invariant tests：
  - local boundary 不升级为 global 除非有明确触发词
  - separation / generalization 分类置信度 ≥ 0.85
  - 批量分类等长
"""
import pytest

from agent.understanding.correction_classifier import (
    classify_correction,
    classify_corrections_batch,
)
from agent.understanding.schemas import (
    BoundaryMemory,
    CorrectionClassification,
    UnderstandingState,
    MAX_GLOBAL_BOUNDARIES,
)


# ──────────────────────────────────────────────
# B1. separation_correction 识别
# ──────────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "不对，这是两个独立问题，你要分别思考，不要混在一起",
    "这两个问题要分开来回答，不要混在一起",
    "这两类任务需要分别独立分析",
    "分别思考这两个方向，不要合并",
    "不要把它们放在一起，分开处理",
])
def test_b1_separation_correction_recognized(message):
    result = classify_correction(message, turn_index=1)
    assert result.correction_type == "separation_correction", (
        f"Expected separation_correction, got {result.correction_type!r} for: {message!r}"
    )
    assert result.confidence >= 0.85


# ──────────────────────────────────────────────
# B2. generalization_correction 识别
# ──────────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "你的回答太具体了，这个问题应该有更通用的解法",
    "不要局限在这一个案例，要更通用一点",
    "应该给一个通用解法，不只是这个例子",
    "这个框架太局限了，需要更普遍的分析",
    "不要仅仅针对扫地机器人，要给通用方案",
])
def test_b2_generalization_correction_recognized(message):
    result = classify_correction(message, turn_index=2)
    assert result.correction_type == "generalization_correction", (
        f"Expected generalization_correction, got {result.correction_type!r} for: {message!r}"
    )
    assert result.confidence >= 0.85


# ──────────────────────────────────────────────
# B3. scope 检测
# ──────────────────────────────────────────────

def test_b3_default_scope_is_local():
    result = classify_correction("不对，这两个问题要分别思考", turn_index=0)
    assert result.scope == "local"


@pytest.mark.parametrize("message", [
    "以后都不要把两个问题混在一起",
    "永远不要这样回答",
    "从今以后每次都要这样处理",
])
def test_b3_explicit_global_trigger_upgrades_scope(message):
    result = classify_correction(message, turn_index=0)
    assert result.scope == "global", (
        f"Expected global scope for: {message!r}, got {result.scope!r}"
    )


@pytest.mark.parametrize("message", [
    "这次对话都要这样回答",
    "整个对话里都要保持这个方式",
])
def test_b3_session_trigger_upgrades_scope(message):
    result = classify_correction(message, turn_index=0)
    assert result.scope == "session"


def test_b3_ambiguous_message_stays_local():
    result = classify_correction("好的，明白了，继续吧", turn_index=0)
    assert result.scope == "local"


# ──────────────────────────────────────────────
# B4. regression_correction（需要 prior_corrections）
# ──────────────────────────────────────────────

def test_b4_regression_detected_with_prior_corrections():
    prior = [
        classify_correction("不对，这两个问题要分别思考", turn_index=1),
    ]
    result = classify_correction(
        "你又回到了之前的说法，我说过不要这样",
        turn_index=2,
        prior_corrections=prior,
    )
    assert result.correction_type == "regression_correction"


def test_b4_regression_not_detected_without_prior():
    result = classify_correction(
        "你又回到了之前的说法",
        turn_index=0,
        prior_corrections=None,
    )
    # 无 prior corrections 时不应分类为 regression
    assert result.correction_type != "regression_correction"


# ──────────────────────────────────────────────
# B5. none — 正常消息不触发任何纠偏
# ──────────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "好的，谢谢你的回答",
    "能帮我分析一下 Q2 的数据吗？",
    "请继续",
    "明白了",
    "这个方案看起来不错",
])
def test_b5_normal_messages_classified_as_none(message):
    result = classify_correction(message, turn_index=0)
    assert result.correction_type == "none", (
        f"Expected none, got {result.correction_type!r} for: {message!r}"
    )


# ──────────────────────────────────────────────
# 其他纠偏类型覆盖
# ──────────────────────────────────────────────

@pytest.mark.parametrize("message,expected", [
    ("不对，事实上这个数字是错的", "fact_correction"),
    ("你说错了，实际上是另一个结果", "fact_correction"),
    ("范围太宽了，只聚焦于这一块就好", "scope_correction"),
    ("换个角度来看这个问题", "frame_correction"),
    ("太浅了，需要更深入的分析", "depth_correction"),
    ("太复杂了，简单点就好", "depth_correction"),
])
def test_other_correction_types(message, expected):
    result = classify_correction(message, turn_index=0)
    assert result.correction_type == expected, (
        f"Expected {expected}, got {result.correction_type!r} for: {message!r}"
    )


# ──────────────────────────────────────────────
# Invariant：separation > generalization > others
# ──────────────────────────────────────────────

def test_separation_has_higher_priority_than_generalization():
    msg = "这两个问题要分别思考，而且要更通用的解法"
    result = classify_correction(msg, turn_index=0)
    assert result.correction_type == "separation_correction"


# ──────────────────────────────────────────────
# UnderstandingState 更新
# ──────────────────────────────────────────────

def test_understanding_state_updates_from_separation():
    state = UnderstandingState()
    correction = classify_correction(
        "这是两个独立问题，要分别思考", turn_index=1
    )
    state.update_from_correction(correction)
    assert state.split_frame is True
    assert state.confidence < 0.5


def test_understanding_state_updates_from_generalization():
    state = UnderstandingState()
    correction = classify_correction(
        "应该更通用，不要局限在一个案例", turn_index=1
    )
    state.update_from_correction(correction)
    assert state.widen_scope is True


def test_understanding_state_confidence_increases_on_none():
    state = UnderstandingState(confidence=0.6)
    correction = classify_correction("好的，继续", turn_index=1)
    state.update_from_correction(correction)
    assert state.confidence > 0.6


def test_understanding_state_snapshot_is_dict():
    state = UnderstandingState(current_task_frame="pricing", confidence=0.7)
    snap = state.snapshot()
    assert isinstance(snap, dict)
    assert snap["confidence"] == 0.7


# ──────────────────────────────────────────────
# BoundaryMemory
# ──────────────────────────────────────────────

def test_boundary_memory_negative_to_prompt_line():
    bm = BoundaryMemory(
        boundary_type="negative",
        content="不能把问题限定在扫地机器人案例",
        source_turn=2,
        session_id="sess_001",
        scope="local",
    )
    line = bm.to_prompt_line()
    assert line.startswith("【禁止】")
    assert "扫地机器人" in line


def test_boundary_memory_positive_to_prompt_line():
    bm = BoundaryMemory(
        boundary_type="positive",
        content="每次回答要给通用框架",
        source_turn=3,
        session_id="sess_001",
        scope="session",
    )
    line = bm.to_prompt_line()
    assert line.startswith("【规则】")


def test_boundary_memory_max_global_constant():
    assert MAX_GLOBAL_BOUNDARIES == 10


# ──────────────────────────────────────────────
# 批量分类
# ──────────────────────────────────────────────

def test_batch_classification_length_matches():
    messages = [
        "好的，继续",
        "不对，这是两个独立问题",
        "应该更通用一点",
    ]
    results = classify_corrections_batch(messages)
    assert len(results) == len(messages)


def test_batch_classification_types():
    messages = [
        "好的，继续",
        "这两个问题要分别思考",
        "应该更通用",
    ]
    results = classify_corrections_batch(messages)
    assert results[0].correction_type == "none"
    assert results[1].correction_type == "separation_correction"
    assert results[2].correction_type == "generalization_correction"


def test_batch_classification_turn_indices():
    messages = ["消息A", "消息B", "消息C"]
    results = classify_corrections_batch(messages)
    for i, r in enumerate(results):
        assert r.turn_index == i
