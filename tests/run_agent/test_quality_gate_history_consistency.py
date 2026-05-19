"""
Quality Gate History Consistency Tests

验证 QUALITY_LOOP_GATED 改写 final_response 后，final_msg["content"] 与之一致：
  1. gate 不活跃时：final_msg["content"] == 原始内容（无变化）
  2. gate 活跃 + pass：final_msg["content"] == 原始内容
  3. gate 活跃 + fail + rewrite：final_msg["content"] == 改写后内容
  4. streaming 路径：final_msg["content"] 不变（不改写）
  5. 同步修复逻辑：当 final_msg["content"] != final_response 时覆盖
"""
from __future__ import annotations

import pytest

from agent.understanding.quality_loop_gated import apply_quality_gate
from agent.understanding.schemas import BoundaryMemory, UnderstandingState
from agent.understanding.user_quality_function import UserQualityFunction


def _apply_history_sync(final_msg: dict, final_response: str) -> dict:
    """模拟 run_agent.py 中的 history sync 修复：
    final_msg = _build_assistant_message(...)  # 使用 assistant_message.content
    if final_msg.get("content") != final_response:
        final_msg["content"] = final_response  # <-- 修复点
    """
    if final_msg.get("content") != final_response:
        final_msg["content"] = final_response
    return final_msg


def _make_final_msg(original_content: str) -> dict:
    """模拟 _build_assistant_message 返回的 dict（使用原始 assistant_message.content）。"""
    return {"role": "assistant", "content": original_content, "finish_reason": "stop"}


# 1. gate 不活跃：final_msg["content"] 不变
def test_no_gate_final_msg_unchanged(monkeypatch):
    monkeypatch.delenv("QUALITY_LOOP_GATED", raising=False)
    original = "原始回答内容"
    final_response = original  # gate 不活跃，final_response 不变
    final_msg = _make_final_msg(original)
    result = _apply_history_sync(final_msg, final_response)
    assert result["content"] == original


# 2. gate 活跃 + pass：final_msg["content"] 不变
def test_gate_pass_final_msg_unchanged(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    original = "这是一个干净的回答，没有任何质量问题。"
    qf = UserQualityFunction()
    state = UnderstandingState()
    final_response, eval_result = apply_quality_gate(
        candidate_answer=original,
        prior_response="",
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
    )
    assert eval_result.overall_pass is True
    assert final_response == original
    final_msg = _make_final_msg(original)
    result = _apply_history_sync(final_msg, final_response)
    assert result["content"] == original


# 3. gate 活跃 + fail + rewrite：final_msg["content"] == 改写后内容
def test_gate_fail_rewrite_final_msg_updated(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    low_quality = "综合来看这两个问题的答案是一样的。"
    rewritten = "问题1的答案是A。问题2的答案是B。"

    def mock_rewrite(original: str, guidance: str) -> str:
        return rewritten

    qf = UserQualityFunction(must_separate_questions=True)
    state = UnderstandingState()
    state.split_frame = True

    final_response, eval_result = apply_quality_gate(
        candidate_answer=low_quality,
        prior_response="",
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
        llm_rewrite_fn=mock_rewrite,
    )
    assert eval_result.overall_pass is False
    assert final_response == rewritten  # gate 返回改写内容
    assert final_response != low_quality

    # 模拟 _build_assistant_message 仍用 assistant_message.content（原始）
    final_msg = _make_final_msg(low_quality)
    assert final_msg["content"] == low_quality  # 改写前：不一致

    # 应用 history sync 修复
    result = _apply_history_sync(final_msg, final_response)
    assert result["content"] == rewritten     # 修复后：一致
    assert result["content"] != low_quality   # 原始低质量内容不出现


# 4. streaming 路径：不改写，final_msg["content"] == 原始
def test_streaming_path_final_msg_unchanged(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    low_quality = "综合来看这两个问题的答案是一样的。"

    # streaming 路径：apply_quality_gate 传 llm_rewrite_fn=None
    qf = UserQualityFunction(must_separate_questions=True)
    state = UnderstandingState()
    state.split_frame = True

    final_response, eval_result = apply_quality_gate(
        candidate_answer=low_quality,
        prior_response="",
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
        llm_rewrite_fn=None,  # streaming fallback: fn=None
    )
    # streaming 时 final_response 不变（即使 fail）
    assert final_response == low_quality

    final_msg = _make_final_msg(low_quality)
    result = _apply_history_sync(final_msg, final_response)
    assert result["content"] == low_quality   # streaming 不修改


# 5. 同步修复逻辑本身：直接验证 content 覆盖行为
def test_history_sync_logic_overwrites_when_different():
    original = "原始内容"
    rewritten = "改写后内容"
    final_msg = _make_final_msg(original)

    # 修复前：不一致
    assert final_msg["content"] != rewritten

    result = _apply_history_sync(final_msg, rewritten)

    # 修复后：一致
    assert result["content"] == rewritten
    # 同一个 dict（原地修改）
    assert result is final_msg


def test_history_sync_logic_no_op_when_equal():
    content = "相同内容"
    final_msg = _make_final_msg(content)
    result = _apply_history_sync(final_msg, content)
    assert result["content"] == content
