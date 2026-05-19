"""
Understanding Loop Run Conversation Integration Tests (P1-1)

验证多轮对话质量闭环：
  1. 第一轮纠偏后 UnderstandingState / BoundaryMemory 被正确更新
  2. 第二轮 quality function 从更新后的 state 派生
  3. 候选答案不合格时被 gate 检测，触发 rewrite 或 clarify
  4. rewrite 后 final_response 与通过 _apply_history_sync 的 messages 内容一致
  5. streaming 场景 final_response 不被静默替换
  6. rewrite 失败 fallback，不中断主流程
  7. UNDERSTANDING_LOOP_ENABLED=false 时 state 不更新（shadow 也不更新 state）
"""
from __future__ import annotations

import pytest

from agent.understanding.correction_classifier import classify_correction
from agent.understanding.quality_loop_gated import apply_quality_gate
from agent.understanding.schemas import BoundaryMemory, UnderstandingState
from agent.understanding.user_quality_function import UserQualityFunction, derive_quality_function


def _simulate_correction_hook(
    user_message: str,
    state: UnderstandingState,
    boundary_memory: list,
    turn_index: int = 1,
    gated: bool = True,
) -> None:
    """模拟 run_agent.py _classify_and_log_correction 的 gated 路径。"""
    result = classify_correction(user_message, turn_index=turn_index)
    if not gated or result.correction_type == "none":
        return
    state.update_from_correction(result)
    neg_types = {
        "fact_correction", "scope_correction", "frame_correction",
        "separation_correction", "generalization_correction", "regression_correction",
    }
    if result.correction_type in neg_types:
        boundary_memory.append(BoundaryMemory(
            boundary_type="negative",
            content=user_message[:200],
            source_turn=turn_index,
            session_id="test-session",
            scope=result.scope,
        ))


def _apply_history_sync(final_msg: dict, final_response: str) -> dict:
    """模拟 run_agent.py 的 history sync 修复逻辑。"""
    if final_msg.get("content") != final_response:
        final_msg["content"] = final_response
    return final_msg


# ──────────────────────────────────────────────────────────────────────────────
# 1. 第一轮纠偏 → state / boundary_memory 正确更新
# ──────────────────────────────────────────────────────────────────────────────

def test_correction_updates_state_and_boundary():
    state = UnderstandingState()
    boundary_memory = []

    _simulate_correction_hook(
        "这两个问题要分别思考，不要混在一起",
        state, boundary_memory, turn_index=1, gated=True,
    )

    assert state.split_frame is True
    assert len(boundary_memory) == 1
    assert boundary_memory[0].boundary_type == "negative"


# ──────────────────────────────────────────────────────────────────────────────
# 2. 第二轮 quality function 从更新后 state 派生
# ──────────────────────────────────────────────────────────────────────────────

def test_quality_function_derived_from_updated_state():
    state = UnderstandingState()
    boundary_memory = []

    _simulate_correction_hook(
        "你的回答太具体了，应该给出更通用的解法",
        state, boundary_memory, turn_index=1,
    )

    qf = derive_quality_function(state, boundary_memory)
    assert qf.must_keep_generalized_scope is True
    assert qf.must_separate_questions is False


# ──────────────────────────────────────────────────────────────────────────────
# 3. 候选答案不合格 → gate 检测 + rewrite
# ──────────────────────────────────────────────────────────────────────────────

def test_gate_detects_and_rewrites_bad_candidate(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    state = UnderstandingState()
    boundary_memory = []

    _simulate_correction_hook(
        "这两个问题要分别思考，不要混在一起",
        state, boundary_memory, turn_index=1,
    )

    qf = derive_quality_function(state, boundary_memory)
    bad_candidate = "综合来看，这两个问题的答案是一样的。"
    rewritten = "问题1：降低成本的方法是精简供应链。\n问题2：提升利润的方法是涨价。"

    final_response, eval_result = apply_quality_gate(
        candidate_answer=bad_candidate,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
        llm_rewrite_fn=lambda orig, guidance: rewritten,
    )

    assert eval_result.overall_pass is False
    assert "mixed_questions" in eval_result.failed_checks
    assert final_response == rewritten


# ──────────────────────────────────────────────────────────────────────────────
# 4. rewrite 后 final_response 与 messages[-1]["content"] 一致
# ──────────────────────────────────────────────────────────────────────────────

def test_history_sync_after_rewrite(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    state = UnderstandingState()
    boundary_memory = []

    _simulate_correction_hook(
        "这两个问题要分别思考，不要混在一起",
        state, boundary_memory,
    )

    qf = derive_quality_function(state, boundary_memory)
    bad_candidate = "综合来看，两个问题的答案是相同的。"
    rewritten = "问题1的答案是A，问题2的答案是B。"

    final_response, _ = apply_quality_gate(
        candidate_answer=bad_candidate,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
        llm_rewrite_fn=lambda o, g: rewritten,
    )

    # 模拟 _build_assistant_message 使用原始 assistant_message.content
    final_msg = {"role": "assistant", "content": bad_candidate, "finish_reason": "stop"}
    result = _apply_history_sync(final_msg, final_response)

    assert result["content"] == rewritten
    assert result["content"] != bad_candidate


# ──────────────────────────────────────────────────────────────────────────────
# 5. streaming 场景：final_response 不被静默替换（fn=None）
# ──────────────────────────────────────────────────────────────────────────────

def test_streaming_path_no_silent_replacement(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    state = UnderstandingState()
    boundary_memory = []

    _simulate_correction_hook("这两个问题要分别思考", state, boundary_memory)
    qf = derive_quality_function(state, boundary_memory)

    bad_candidate = "综合来看，两个问题可以一起回答。"
    final_response, eval_result = apply_quality_gate(
        candidate_answer=bad_candidate,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
        llm_rewrite_fn=None,  # streaming: no rewrite
    )

    # streaming 路径：不修改，即使 fail
    assert final_response == bad_candidate
    assert eval_result.overall_pass is False


# ──────────────────────────────────────────────────────────────────────────────
# 6. rewrite 失败 fallback，不中断主流程
# ──────────────────────────────────────────────────────────────────────────────

def test_rewrite_failure_fallback(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    state = UnderstandingState()
    boundary_memory = []

    _simulate_correction_hook("这两个问题要分别思考", state, boundary_memory)
    qf = derive_quality_function(state, boundary_memory)

    bad_candidate = "综合来看，两个问题答案相同。"

    def failing_rewrite(orig, guidance):
        raise RuntimeError("LLM unavailable")

    final_response, eval_result = apply_quality_gate(
        candidate_answer=bad_candidate,
        prior_response="",
        understanding_state=state,
        boundary_memory=boundary_memory,
        quality_fn=qf,
        llm_rewrite_fn=failing_rewrite,
    )

    # fallback 到原始答案，不中断
    assert final_response == bad_candidate
    assert eval_result.overall_pass is False


# ──────────────────────────────────────────────────────────────────────────────
# 7. UNDERSTANDING_LOOP_ENABLED=false → state 不更新
# ──────────────────────────────────────────────────────────────────────────────

def test_understanding_loop_disabled_state_not_updated():
    state = UnderstandingState()
    boundary_memory = []

    # gated=False 模拟 UNDERSTANDING_LOOP_ENABLED=false
    _simulate_correction_hook(
        "这两个问题要分别思考，不要混在一起",
        state, boundary_memory, gated=False,
    )

    assert state.split_frame is False
    assert len(boundary_memory) == 0
