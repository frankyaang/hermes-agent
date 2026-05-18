"""
Tests for agent_system.gstack_control.state_machine.

Key invariants:
  - When enabled=False (default), evaluate() always returns mode=disabled
  - blocking is NEVER returned by evaluate()
  - State transitions: low→disabled, medium→shadow, high→advisory (when enabled)
"""
import pytest
from unittest.mock import patch

from agent_system.gstack_control.state_machine import evaluate
from agent_system.gstack_control.specs import ControlDecision


def test_evaluate_returns_disabled_when_flag_off():
    """Default flag state → always disabled regardless of risk_level."""
    for risk in ("low", "medium", "high"):
        decision = evaluate("gstack.plan_eng_review", risk)
        assert decision.mode == "disabled", f"Expected disabled for risk={risk}"
        assert decision.blocking is False


def test_evaluate_never_returns_blocking_by_default():
    decision = evaluate("gstack.review", "high")
    assert decision.blocking is False


def test_evaluate_unknown_phase_returns_disabled():
    decision = evaluate("gstack.unknown_phase", "high")
    assert decision.mode == "disabled"
    assert decision.blocking is False


def test_evaluate_low_risk_when_enabled_returns_disabled():
    with patch(
        "agent_system.gstack_control.state_machine.is_enabled", return_value=True
    ), patch(
        "agent_system.gstack_control.state_machine.get_mode", return_value="advisory"
    ):
        decision = evaluate("gstack.plan_eng_review", "low")
        assert decision.mode == "disabled"
        assert decision.blocking is False


def test_evaluate_medium_risk_when_enabled_returns_shadow():
    with patch(
        "agent_system.gstack_control.state_machine.is_enabled", return_value=True
    ), patch(
        "agent_system.gstack_control.state_machine.get_mode", return_value="advisory"
    ):
        decision = evaluate("gstack.review", "medium")
        assert decision.mode == "shadow"
        assert decision.blocking is False


def test_evaluate_high_risk_when_enabled_returns_advisory():
    with patch(
        "agent_system.gstack_control.state_machine.is_enabled", return_value=True
    ), patch(
        "agent_system.gstack_control.state_machine.get_mode", return_value="advisory"
    ):
        decision = evaluate("gstack.qa", "high")
        assert decision.mode == "advisory"
        assert decision.blocking is False
        assert decision.advisory_message != ""


def test_control_decision_raises_on_blocking_true():
    """ControlDecision must raise if blocking=True is attempted."""
    with pytest.raises(ValueError, match="blocking"):
        ControlDecision(
            phase_id="gstack.plan_eng_review",
            risk_level="high",
            mode="advisory",
            blocking=True,
        )
