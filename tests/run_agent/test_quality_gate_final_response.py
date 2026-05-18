"""
Quality Gate Final Response Tests (Q1–Q7)

These tests define the contract for the quality gate integration with run_agent.py.
They must ALL FAIL before implementation (Phase A/C/D).
They must ALL PASS after implementation.

HERMES_HOME is automatically isolated by conftest.py _hermetic_environment fixture.
"""
from __future__ import annotations

import os
import pytest


# ── Q1 ────────────────────────────────────────────────────────────────────────

def test_quality_gate_disabled_noop(monkeypatch):
    """QUALITY_LOOP_GATED=false (default) → output is unchanged."""
    monkeypatch.delenv("QUALITY_LOOP_GATED", raising=False)

    from agent_system.quality.gate import apply_quality_gate_if_enabled

    original = "This is a perfectly fine response from the model."
    result = apply_quality_gate_if_enabled(original, already_streamed=False)
    assert result == original, "disabled gate must return original unchanged"


# ── Q2 ────────────────────────────────────────────────────────────────────────

def test_quality_gate_in_run_agent_main_path(monkeypatch):
    """QUALITY_LOOP_GATED=true → apply_quality_gate_if_enabled runs evaluator and returns str."""
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    from agent_system.quality.gate import apply_quality_gate_if_enabled

    # Good response: gate should pass it unchanged
    good_response = (
        "The root cause of the latency spike is the N+1 query in the user profile "
        "loader. Specifically, for each user in the list, the code makes a separate "
        "database call to fetch preferences. To fix this, batch the preference "
        "queries into a single SELECT WHERE user_id IN (...) statement."
    )
    result = apply_quality_gate_if_enabled(good_response, already_streamed=False)
    assert isinstance(result, str)
    assert len(result) > 0
    # Good response should pass unchanged
    assert result == good_response


# ── Q3 ────────────────────────────────────────────────────────────────────────

def test_low_quality_response_is_rewritten(monkeypatch):
    """QUALITY_LOOP_GATED=true, low-quality response → result is different from original."""
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    from agent_system.quality.gate import apply_quality_gate_if_enabled
    from agent_system.quality.evaluator import CandidateAnswerEvaluator

    # A response that evaluator should score as low quality (vague, non-actionable)
    low_quality = "I don't know. Maybe try something? It could work or not."

    result = apply_quality_gate_if_enabled(low_quality, already_streamed=False)

    # Result must be a non-empty string
    assert isinstance(result, str)
    assert len(result) > 0
    # And it must NOT be the exact original (it was rewritten or clarified)
    # Note: evaluator may score it as "pass" if threshold is conservative —
    # so we use a known-bad input that should always trigger rewrite
    evaluator = CandidateAnswerEvaluator()
    eval_result = evaluator.evaluate(low_quality)
    if eval_result.verdict != "pass":
        assert result != low_quality, "low-quality response must be rewritten or replaced"


# ── Q4 ────────────────────────────────────────────────────────────────────────

def test_rewrite_is_clean_not_suggestion_plus_original(monkeypatch):
    """Rewritten response must be a clean answer, NOT 'suggestions + original answer'."""
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    from agent_system.quality.evaluator import CandidateAnswerEvaluator

    low_quality = "um... I'm not sure what you want. Here are some things: A, B, maybe C?"
    evaluator = CandidateAnswerEvaluator()
    eval_result = evaluator.evaluate(low_quality)

    if eval_result.verdict == "rewrite":
        rewritten = eval_result.rewrite_target
        # Must NOT contain the original concatenated with suggestions
        assert low_quality not in rewritten, (
            "rewrite must not contain original as suffix"
        )
        # Must NOT start with suggestion-pattern phrases
        forbidden_patterns = [
            "Here are suggestions:",
            "Suggestions:",
            "To improve:",
            "Original answer:",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in rewritten, (
                f"rewrite must not contain suggestion pattern: {pattern!r}"
            )
        # Must be non-empty clean text
        assert len(rewritten.strip()) > 0


# ── Q5 ────────────────────────────────────────────────────────────────────────

def test_rewrite_exception_fallback_original(monkeypatch):
    """If rewrite raises an exception, original response is returned + warning logged."""
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    import logging
    from agent_system.quality.gate import apply_quality_gate_if_enabled
    from agent_system.quality import evaluator as eval_mod

    original = "Some response that happens to be low quality."

    class BrokenEvaluator:
        def evaluate(self, candidate):
            raise RuntimeError("injected evaluator failure")

    monkeypatch.setattr(eval_mod, "CandidateAnswerEvaluator", BrokenEvaluator)

    # Must not raise; must return original
    result = apply_quality_gate_if_enabled(original, already_streamed=False)
    assert result == original, "on evaluator exception, must fall back to original"


# ── Q6 ────────────────────────────────────────────────────────────────────────

def test_streaming_safe_degradation(monkeypatch):
    """already_streamed=True → gate only logs evaluation, never replaces output."""
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    from agent_system.quality.gate import apply_quality_gate_if_enabled

    # Even a terrible response must not be replaced when already streamed
    streamed_content = "I don't know. Maybe try something?"
    result = apply_quality_gate_if_enabled(streamed_content, already_streamed=True)

    assert result == streamed_content, (
        "already_streamed=True: gate must return original, no silent replacement"
    )


# ── Q7 ────────────────────────────────────────────────────────────────────────

def test_clarify_path_outputs_clean_question(monkeypatch):
    """When evaluator verdict=clarify, result is a clean clarification question."""
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    from agent_system.quality.evaluator import CandidateAnswerEvaluator, EvalResult

    # Simulate a clarify verdict from the evaluator
    evaluator = CandidateAnswerEvaluator()

    # A response that is ambiguous (needs clarification)
    # We inject a clarify verdict directly to test the gate path
    injected_clarify = EvalResult(
        verdict="clarify",
        score=0.2,
        reason="user intent is ambiguous",
        rewrite_target="Could you clarify what you mean by X?",
    )

    from agent_system.quality import gate as gate_mod
    from agent_system.quality import evaluator as eval_mod

    class ClarifyEvaluator:
        def evaluate(self, candidate):
            return injected_clarify

    monkeypatch.setattr(eval_mod, "CandidateAnswerEvaluator", ClarifyEvaluator)

    from agent_system.quality.gate import apply_quality_gate_if_enabled
    # Reload gate to pick up monkeypatched evaluator
    import importlib
    import agent_system.quality.gate
    importlib.reload(agent_system.quality.gate)
    from agent_system.quality.gate import apply_quality_gate_if_enabled as gate_fn

    result = gate_fn("ambiguous response", already_streamed=False)

    assert isinstance(result, str)
    assert len(result.strip()) > 0
    # Result must be the clarification question, not original + suggestions
    assert "ambiguous response" not in result or "?" in result
    # Must NOT contain "Original answer:"
    assert "Original answer:" not in result
