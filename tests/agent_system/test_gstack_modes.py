"""Tests for gstack_control.modes — all five runtime modes."""
from __future__ import annotations

import pytest
from agent_system.gstack_control.modes import (
    ModeResult,
    run_disabled,
    run_shadow,
    run_advisory,
    run_controlled,
    run_quarantined,
)


def test_disabled_is_noop():
    r = run_disabled("gstack.review")
    assert r.mode == "disabled"
    assert r.success is True
    assert r.advisory_note == ""
    assert r.blocked_reason == ""


def test_disabled_with_context():
    r = run_disabled("gstack.qa", {"key": "value"})
    assert r.success is True


def test_shadow_returns_success_even_when_cli_missing():
    r = run_shadow("gstack.review")
    assert r.mode == "shadow"
    assert r.success is True  # observation succeeds even if CLI unavailable


def test_shadow_blocked_reason_when_cli_missing():
    r = run_shadow("gstack.plan_eng_review")
    if not r.blocked_reason == "":
        assert "not found" in r.blocked_reason or "timeout" in r.blocked_reason or "error" in r.blocked_reason


def test_advisory_returns_success_when_cli_missing():
    r = run_advisory("gstack.review")
    assert r.mode == "advisory"
    assert r.success is True


def test_advisory_note_is_set():
    r = run_advisory("gstack.review")
    assert "[gstack advisory]" in r.advisory_note


def test_controlled_blocked_when_feature_not_enabled():
    r = run_controlled("gstack.review")
    assert r.mode == "controlled"
    assert r.success is False
    assert "not enabled" in r.blocked_reason or "kill_switch" in r.blocked_reason or "allowlist" in r.blocked_reason


def test_controlled_blocked_by_kill_switch(monkeypatch):
    import agent_system.gstack_control.feature_flags as ff
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "controlled", True)
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "kill_switch", True)
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "allowlist_phases", ["gstack.review"])
    r = run_controlled("gstack.review")
    assert not r.success
    assert "kill_switch" in r.blocked_reason


def test_controlled_blocked_by_allowlist(monkeypatch):
    import agent_system.gstack_control.feature_flags as ff
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "controlled", True)
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "kill_switch", False)
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "allowlist_phases", [])
    r = run_controlled("gstack.review")
    assert not r.success
    assert "allowlist" in r.blocked_reason


def test_controlled_proceeds_when_guards_pass(monkeypatch):
    import agent_system.gstack_control.feature_flags as ff
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "controlled", True)
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "kill_switch", False)
    monkeypatch.setitem(ff.GSTACK_FEATURE_FLAGS, "allowlist_phases", ["gstack.review"])
    r = run_controlled("gstack.review")
    # Even if CLI unavailable, mode is controlled and dry_run_only=True
    assert r.mode == "controlled"
    assert r.dry_run_only is True


def test_quarantined_fail_closed():
    r = run_quarantined("gstack.qa", "test error")
    assert r.mode == "quarantined"
    assert r.success is False
    assert "manual human reset" in r.blocked_reason


def test_quarantined_records_evidence():
    r = run_quarantined("gstack.review", "something failed")
    assert "error_summary" in r.evidence


def test_quarantined_with_exception_object():
    try:
        raise ValueError("injected error")
    except ValueError as exc:
        r = run_quarantined("gstack.plan_eng_review", exc)
    assert r.mode == "quarantined"
    assert r.success is False


def test_mode_result_blocking_never_set():
    for fn in [run_disabled, run_shadow, run_advisory, run_controlled, run_quarantined]:
        r = fn("gstack.review")
        assert not hasattr(r, "blocking") or getattr(r, "blocking", False) is False
