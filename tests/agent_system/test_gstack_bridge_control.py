"""gstack_control → gstack_bridge Route Tests

Verifies that phase results from gstack_control can be routed through
gstack_bridge to the appropriate sedimentation destination.
"""
from __future__ import annotations

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _make_gstack_result(stdout="ok output", blocked_reason="", available=True):
    from agent_system.gstack_control.adapter import GstackResult
    return GstackResult(
        available=available,
        command="gstack review",
        exit_code=0 if not blocked_reason else 1,
        stdout=stdout,
        stderr="",
        blocked_reason=blocked_reason,
        duration_ms=100,
    )


# ── Feature flag guard ──────────────────────────────────────────────────────────

def test_route_gstack_result_skips_when_flag_off(tmp_path, monkeypatch):
    """GSTACK_SEDIMENTATION_ENABLED=false → route is a no-op (skipped=True)."""
    monkeypatch.delenv("GSTACK_SEDIMENTATION_ENABLED", raising=False)

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)
    import agent_system.sedimentation.gstack_bridge as gb
    importlib.reload(gb)

    result = gb.route(
        output="some review output",
        output_type="review",
        source_uri="hermes://gstack/test",
        hermes_home=tmp_path,
    )

    assert result.skipped, "flag OFF → must skip"


def test_route_gstack_result_runs_when_flag_on(tmp_path, monkeypatch):
    """GSTACK_SEDIMENTATION_ENABLED=true → route executes and returns destination."""
    monkeypatch.setenv("GSTACK_SEDIMENTATION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)
    import agent_system.sedimentation.gstack_bridge as gb
    importlib.reload(gb)

    result = gb.route(
        output="review: no issues found in PR",
        output_type="review",
        source_uri="hermes://gstack/review/test",
        hermes_home=tmp_path,
    )

    assert not result.skipped
    assert result.destination == "audit_evidence"


# ── Phase ID → output_type mapping ─────────────────────────────────────────────

def test_map_phase_id_to_output_type():
    """map_phase_to_output_type must correctly map known phase IDs."""
    from agent_system.sedimentation.gstack_bridge import map_phase_to_output_type

    assert map_phase_to_output_type("gstack.review") == "review"
    assert map_phase_to_output_type("gstack.plan_eng_review") == "lesson"
    assert map_phase_to_output_type("gstack.qa") == "fact"
    assert map_phase_to_output_type("gstack.retro") == "lesson"
    assert map_phase_to_output_type("unknown.phase") == "uncertain"


# ── route_gstack_result utility ─────────────────────────────────────────────────

def test_route_gstack_result_review_to_audit(tmp_path, monkeypatch):
    """GstackResult for review phase → audit_evidence."""
    monkeypatch.setenv("GSTACK_SEDIMENTATION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)
    import agent_system.sedimentation.gstack_bridge as gb
    importlib.reload(gb)

    gstack_result = _make_gstack_result("Code LGTM, no issues found")
    bridge_result = gb.route_gstack_result(
        phase_id="gstack.review",
        gstack_result=gstack_result,
        hermes_home=tmp_path,
    )

    assert not bridge_result.skipped
    assert bridge_result.destination == "audit_evidence"


def test_route_gstack_result_lesson_to_expert_candidate(tmp_path, monkeypatch):
    """GstackResult for retro/lesson phase → expert_mem_candidate."""
    monkeypatch.setenv("GSTACK_SEDIMENTATION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)
    import agent_system.sedimentation.gstack_bridge as gb
    importlib.reload(gb)

    gstack_result = _make_gstack_result("Retrospective: validate inputs earlier")
    bridge_result = gb.route_gstack_result(
        phase_id="gstack.retro",
        gstack_result=gstack_result,
        hermes_home=tmp_path,
    )

    assert not bridge_result.skipped
    assert bridge_result.destination == "expert_mem_candidate"


def test_route_gstack_result_blocked_goes_to_staging(tmp_path, monkeypatch):
    """Blocked GstackResult (not available) → staging(needs_project_mapping)."""
    monkeypatch.setenv("GSTACK_SEDIMENTATION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)
    import agent_system.sedimentation.gstack_bridge as gb
    importlib.reload(gb)

    gstack_result = _make_gstack_result(
        stdout="",
        blocked_reason="gstack CLI not found",
        available=False,
    )
    bridge_result = gb.route_gstack_result(
        phase_id="gstack.review",
        gstack_result=gstack_result,
        hermes_home=tmp_path,
    )

    assert not bridge_result.skipped
    assert bridge_result.destination == "staging"


def test_route_gstack_result_flag_off_skips(tmp_path, monkeypatch):
    """Flag OFF → route_gstack_result also skips."""
    monkeypatch.delenv("GSTACK_SEDIMENTATION_ENABLED", raising=False)

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)
    import agent_system.sedimentation.gstack_bridge as gb
    importlib.reload(gb)

    gstack_result = _make_gstack_result("review output")
    bridge_result = gb.route_gstack_result(
        phase_id="gstack.review",
        gstack_result=gstack_result,
        hermes_home=tmp_path,
    )

    assert bridge_result.skipped
