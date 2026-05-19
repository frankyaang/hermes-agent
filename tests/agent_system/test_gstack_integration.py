"""
Mock E2E integration test for gstack_control.

Tests the full path: feature_flag → state_machine → modes → metrics
with CLI monkeypatched out. Verifies Hermes main chain is unaffected.
"""
from __future__ import annotations

import pytest
from agent_system.gstack_control import evaluate
from agent_system.gstack_control.feature_flags import GSTACK_FEATURE_FLAGS
from agent_system.gstack_control.modes import run_shadow, run_advisory, run_controlled
from agent_system.gstack_control.state_machine import evaluate as sm_evaluate


# ── disabled (default) ────────────────────────────────────────────────────────

def test_disabled_evaluate_all_phases():
    for phase_id in ("gstack.plan_eng_review", "gstack.review", "gstack.qa"):
        d = evaluate(phase_id)
        assert d.mode == "disabled"
        assert d.blocking is False


def test_disabled_state_machine():
    d = sm_evaluate("gstack.review", "high")
    assert d.mode == "disabled"
    assert d.blocking is False


# ── shadow mode ───────────────────────────────────────────────────────────────

def test_shadow_mode_e2e(monkeypatch):
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "enabled", True)
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "mode", "advisory")
    d = sm_evaluate("gstack.review", "medium")
    assert d.mode == "shadow"
    assert d.blocking is False
    r = run_shadow("gstack.review", {"source": "test"})
    assert r.mode == "shadow"
    assert r.success is True


# ── advisory mode ─────────────────────────────────────────────────────────────

def test_advisory_mode_e2e(monkeypatch):
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "enabled", True)
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "mode", "advisory")
    d = sm_evaluate("gstack.qa", "high")
    assert d.mode == "advisory"
    assert d.blocking is False
    r = run_advisory("gstack.qa", {"source": "test"})
    assert r.mode == "advisory"
    assert "[gstack advisory]" in r.advisory_note


# ── controlled mode ───────────────────────────────────────────────────────────

def test_controlled_mode_e2e_guards_pass(monkeypatch):
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "enabled", True)
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "mode", "advisory")
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "controlled", True)
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "kill_switch", False)
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "allowlist_phases", ["gstack.review"])

    d = sm_evaluate("gstack.review", "high")
    assert d.mode == "controlled"
    assert d.blocking is False

    r = run_controlled("gstack.review", {"source": "test"})
    assert r.mode == "controlled"
    assert r.dry_run_only is True


def test_controlled_mode_e2e_kill_switch_blocks(monkeypatch):
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "controlled", True)
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "kill_switch", True)
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "allowlist_phases", ["gstack.review"])
    r = run_controlled("gstack.review")
    assert not r.success
    assert "kill_switch" in r.blocked_reason


# ── quarantined ───────────────────────────────────────────────────────────────

def test_quarantined_on_evaluate_exception(monkeypatch):
    """If state_machine._evaluate raises, outer evaluate catches → quarantined."""
    import agent_system.gstack_control.state_machine as sm
    monkeypatch.setattr(sm, "_evaluate", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("injected")))
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "enabled", True)
    d = evaluate("gstack.review", "high")
    assert d.mode == "quarantined"
    assert d.blocking is False
    assert "injected" in d.evidence.get("quarantine_reason", "")


# ── cli_bridge integration ────────────────────────────────────────────────────

def test_gstack_phase_gate_noop_when_disabled():
    from agent_system.cli_bridge import _gstack_phase_gate
    # Must not raise and must be noop (returns None)
    result = _gstack_phase_gate("gstack.plan_eng_review", "test_entrypoint")
    assert result is None


def test_gstack_phase_gate_shadow_when_enabled(monkeypatch):
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "enabled", True)
    monkeypatch.setitem(GSTACK_FEATURE_FLAGS, "mode", "advisory")
    from agent_system.cli_bridge import _gstack_phase_gate
    # Must not raise; shadow mode writes metric silently
    result = _gstack_phase_gate("gstack.review", "test_entrypoint")
    assert result is None


# ── safety invariants ─────────────────────────────────────────────────────────

def test_blocking_never_true_in_any_mode():
    for risk in ("low", "medium", "high"):
        d = evaluate("gstack.review", risk)
        assert d.blocking is False


def test_no_token_in_metrics_secret_key(monkeypatch, tmp_path):
    """Metrics with secret key names must have values redacted."""
    import agent_system.gstack_control.metrics_writer as mw
    monkeypatch.setattr(mw, "_metrics_dir", lambda: tmp_path)
    from agent_system.gstack_control.metrics_writer import write_metric
    # Key named "token" triggers redaction of its value
    write_metric("test", {"token": "secret_token_12345", "phase": "gstack.review"})
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    content = written[0].read_text()
    assert "secret_token_12345" not in content
    assert "gstack.review" in content  # non-secret field preserved


def test_redact_string_strips_bearer():
    """redact_string removes Bearer token values from arbitrary strings."""
    from agent_system.gstack_control.metrics_redaction import redact_string
    s = "Bearer secret_token_12345 output"
    result = redact_string(s)
    assert "secret_token_12345" not in result
    assert "Bearer" in result  # keyword preserved, value redacted


def test_advisory_routes_external_evidence_without_direct_memory(tmp_path, monkeypatch):
    """gstack advisory output enters the evidence bridge, not private memory."""
    monkeypatch.setenv("GSTACK_SEDIMENTATION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)

    from agent_system.gstack_control.adapter import GstackResult
    import agent_system.gstack_control.adapter as adapter
    from agent_system.gstack_control.modes import run_advisory

    monkeypatch.setattr(
        adapter,
        "run_gstack_advisory",
        lambda phase_id, ctx: GstackResult(
            available=True,
            command="gstack review --advisory",
            exit_code=0,
            stdout="Review evidence: keep QA non-blocking.",
            stderr="",
            blocked_reason="",
            duration_ms=12,
        ),
    )

    result = run_advisory(
        "gstack.review",
        {"hermes_home": str(tmp_path), "project_hint": "agent_system"},
    )

    evidence = result.evidence["external_expert_evidence"]
    assert result.success is True
    assert evidence["destination"] == "audit_evidence"
    assert evidence["direct_memory_write"] is False
    assert (tmp_path / "memory_events" / "events.jsonl").exists()
    assert not (tmp_path / "experience_cards" / "cards.jsonl").exists()
    assert not (tmp_path / "memory" / "system_mem" / "MEMORY.md").exists()
