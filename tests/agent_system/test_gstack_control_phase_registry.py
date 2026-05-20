"""
Tests for agent_system.gstack_control.phase_registry.

Key invariants:
  - Core phases registered: plan_eng_review, review, qa (+ expanded 24-specialist set)
  - All phases are NOT production_ready
  - real_gstack is False for all phases
  - blocking_allowed is False for all phases
"""
import pytest
from agent_system.gstack_control.phase_registry import (
    get_phase,
    list_phases,
    is_registered,
    is_production_ready,
)

EXPECTED_PHASES = ["gstack.plan_eng_review", "gstack.review", "gstack.qa"]


def test_all_expected_phases_registered():
    for pid in EXPECTED_PHASES:
        assert is_registered(pid), f"Phase {pid} must be registered"


def test_list_phases_covers_all_layers():
    phases = list_phases()
    # Protocol v0.3.0: 27 phases across scheduler/expert/skill/sedimentation/tool layers
    assert len(phases) >= 24, f"Expected >= 24 phases, got {len(phases)}"


def test_unknown_phase_not_registered():
    assert not is_registered("gstack.unknown")


def test_get_phase_returns_spec():
    spec = get_phase("gstack.plan_eng_review")
    assert spec is not None
    assert spec.id == "gstack.plan_eng_review"


def test_get_phase_returns_none_for_unknown():
    assert get_phase("gstack.does_not_exist") is None


def test_no_phase_is_production_ready():
    for pid in EXPECTED_PHASES:
        assert not is_production_ready(pid), f"{pid} must not be production_ready"


def test_unknown_phase_is_not_production_ready():
    assert not is_production_ready("gstack.unknown")


def test_no_phase_uses_real_gstack():
    for phase in list_phases():
        assert phase.real_gstack is False, f"{phase.id} must not use real gstack"


def test_no_phase_allows_blocking():
    for phase in list_phases():
        assert phase.blocking_allowed is False, (
            f"{phase.id} must not allow blocking"
        )
