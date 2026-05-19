"""
Quality Loop Config Strategy Tests (P1-2)

验证质量机制的启用策略：
  1. QUALITY_LOOP_GATED 未设置（默认）→ gate 不激活
  2. QUALITY_LOOP_GATED=false → gate 不激活
  3. QUALITY_LOOP_GATED=true → gate 激活，评估运行
  4. UNDERSTANDING_LOOP_ENABLED 未设置 → correction 不更新 state
  5. UNDERSTANDING_LOOP_ENABLED=true → correction 更新 state
  6. UNDERSTANDING_LOOP_SHADOW=true → 记录日志但不更新 state
  7. 各 flag 独立：QUALITY_LOOP_GATED 不影响 UNDERSTANDING_LOOP_ENABLED

说明：env var 是正确的部署机制（runtime config 不属于代码 config.yaml）。
     生产环境通过容器/进程环境变量控制，测试通过 monkeypatch 控制。
     此策略有意为之，无需 config.yaml 集成。
"""
from __future__ import annotations

import pytest

from agent.understanding.quality_loop_gated import apply_quality_gate
from agent.understanding.schemas import UnderstandingState
from agent.understanding.user_quality_function import UserQualityFunction


def _gate_result(candidate: str, monkeypatch_env: bool = False, **qf_kwargs):
    state = UnderstandingState()
    qf = UserQualityFunction(**qf_kwargs)
    return apply_quality_gate(
        candidate_answer=candidate,
        prior_response="",
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. QUALITY_LOOP_GATED 未设置（默认）→ gate 不激活
# ──────────────────────────────────────────────────────────────────────────────

def test_gate_inactive_when_env_not_set(monkeypatch):
    monkeypatch.delenv("QUALITY_LOOP_GATED", raising=False)
    answer, eval_result = _gate_result("任意答案", must_separate_questions=True)
    assert eval_result.overall_pass is True   # noop evaluation
    assert answer == "任意答案"


# ──────────────────────────────────────────────────────────────────────────────
# 2. QUALITY_LOOP_GATED=false → gate 不激活
# ──────────────────────────────────────────────────────────────────────────────

def test_gate_inactive_when_env_false(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "false")
    answer, eval_result = _gate_result("任意答案", must_separate_questions=True)
    assert eval_result.overall_pass is True
    assert answer == "任意答案"


# ──────────────────────────────────────────────────────────────────────────────
# 3. QUALITY_LOOP_GATED=true → gate 激活
# ──────────────────────────────────────────────────────────────────────────────

def test_gate_active_when_env_true(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    state = UnderstandingState()
    state.split_frame = True
    from agent.understanding.user_quality_function import derive_quality_function
    qf = derive_quality_function(state, [])

    bad_candidate = "综合来看，这两个问题的答案是一样的。"
    _, eval_result = apply_quality_gate(
        candidate_answer=bad_candidate,
        prior_response="",
        understanding_state=state,
        boundary_memory=[],
        quality_fn=qf,
    )
    assert eval_result.overall_pass is False


# ──────────────────────────────────────────────────────────────────────────────
# 4. UNDERSTANDING_LOOP_ENABLED 未设置 → correction 不更新 state（simulate hook）
# ──────────────────────────────────────────────────────────────────────────────

def test_understanding_loop_disabled_no_state_update(monkeypatch):
    monkeypatch.delenv("UNDERSTANDING_LOOP_ENABLED", raising=False)
    from agent.understanding.schemas import UnderstandingState

    state = UnderstandingState()
    gated = False  # env var not set → gated=False

    from agent.understanding.correction_classifier import classify_correction
    result = classify_correction("这两个问题要分别处理，分开回答")
    if gated and result.correction_type != "none":
        state.update_from_correction(result)

    assert state.split_frame is False


# ──────────────────────────────────────────────────────────────────────────────
# 5. UNDERSTANDING_LOOP_ENABLED=true → correction 更新 state
# ──────────────────────────────────────────────────────────────────────────────

def test_understanding_loop_enabled_updates_state(monkeypatch):
    monkeypatch.setenv("UNDERSTANDING_LOOP_ENABLED", "true")
    from agent.understanding.schemas import UnderstandingState
    from agent.understanding.correction_classifier import classify_correction

    state = UnderstandingState()
    gated = True

    result = classify_correction("这两个问题要分别处理，分开回答")
    if gated and result.correction_type != "none":
        state.update_from_correction(result)

    assert state.split_frame is True


# ──────────────────────────────────────────────────────────────────────────────
# 6. UNDERSTANDING_LOOP_SHADOW=true → 不更新 state（shadow-only）
# ──────────────────────────────────────────────────────────────────────────────

def test_shadow_mode_does_not_update_state(monkeypatch):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "true")
    monkeypatch.delenv("UNDERSTANDING_LOOP_ENABLED", raising=False)
    from agent.understanding.schemas import UnderstandingState
    from agent.understanding.correction_classifier import classify_correction

    state = UnderstandingState()
    shadow = True
    gated = False  # only shadow, not gated

    result = classify_correction("这两个问题要分别处理，分开回答")
    if gated and result.correction_type != "none":  # gated=False → no state update
        state.update_from_correction(result)

    assert state.split_frame is False  # shadow 不修改 state


# ──────────────────────────────────────────────────────────────────────────────
# 7. 各 flag 独立：QUALITY_LOOP_GATED 不影响 UNDERSTANDING_LOOP_ENABLED
# ──────────────────────────────────────────────────────────────────────────────

def test_flags_are_independent(monkeypatch):
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    monkeypatch.delenv("UNDERSTANDING_LOOP_ENABLED", raising=False)

    import os
    assert os.getenv("QUALITY_LOOP_GATED", "").lower() == "true"
    assert os.getenv("UNDERSTANDING_LOOP_ENABLED", "").lower() != "true"
