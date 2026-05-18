"""Tests for gstack_control.ops — operations entrypoints."""
from __future__ import annotations

import pytest
from agent_system.gstack_control.ops import status, smoke, report, metrics, rollback_report


def test_status_returns_dict():
    r = status()
    assert isinstance(r, dict)


def test_status_has_required_keys():
    r = status()
    for key in ("enabled", "mode", "allow_blocking", "controlled", "kill_switch",
                "adapter_available", "phases", "known_commands"):
        assert key in r, f"missing key: {key}"


def test_status_defaults_disabled():
    r = status()
    assert r["enabled"] is False
    assert r["mode"] == "disabled"
    assert r["allow_blocking"] is False
    assert r["controlled"] is False
    assert r["kill_switch"] is True


def test_status_adapter_available_is_bool():
    r = status()
    assert isinstance(r["adapter_available"], bool)


def test_status_phases_list():
    r = status()
    assert isinstance(r["phases"], list)
    assert len(r["phases"]) >= 3
    ids = [p["id"] for p in r["phases"]]
    assert "gstack.plan_eng_review" in ids
    assert "gstack.review" in ids
    assert "gstack.qa" in ids


def test_smoke_returns_dict():
    r = smoke()
    assert isinstance(r, dict)


def test_smoke_has_required_keys():
    r = smoke()
    for key in ("adapter_available", "blocked", "phase_smoke"):
        assert key in r


def test_smoke_phase_results_structure():
    r = smoke()
    for entry in r["phase_smoke"]:
        assert "phase_id" in entry
        assert "available" in entry
        assert "blocked_reason" in entry


def test_smoke_blocked_when_cli_missing():
    r = smoke()
    # gstack CLI not installed in this env
    if not r["adapter_available"]:
        assert r["blocked"] is True
        assert r["blocked_reason"] != ""


def test_report_returns_dict():
    r = report()
    assert isinstance(r, dict)
    assert "status" in r
    assert "smoke" in r


def test_metrics_returns_dict():
    r = metrics()
    assert isinstance(r, dict)
    assert "entries" in r
    assert "count" in r
    assert isinstance(r["entries"], list)


def test_metrics_count_matches_entries():
    r = metrics()
    assert r["count"] == len(r["entries"])


def test_rollback_report_returns_dict():
    r = rollback_report()
    assert isinstance(r, dict)


def test_rollback_report_has_instructions():
    r = rollback_report()
    assert "instructions" in r
    assert isinstance(r["instructions"], list)
    assert len(r["instructions"]) > 0


def test_rollback_report_no_tokens():
    import json
    r = rollback_report()
    text = json.dumps(r)
    for secret_key in ("Bearer", "Authorization", "access_token", "refresh_token"):
        assert secret_key not in text
