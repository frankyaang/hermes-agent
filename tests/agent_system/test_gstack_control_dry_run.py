"""
Tests for agent_system.gstack_control.dry_run.

Key invariants:
  - dry_run.run() never calls real gstack
  - blocking is always False in returned DryRunRecord
  - replay produces a structurally identical DryRunRecord
"""
import json
import pytest
from agent_system.gstack_control.dry_run import run, to_json
from agent_system.gstack_control.replay import replay_record, replay_json


def test_dry_run_returns_record():
    record = run("gstack.plan_eng_review", "low")
    assert record.phase_id == "gstack.plan_eng_review"
    assert record.risk_level == "low"
    assert isinstance(record.timestamp_ms, int)


def test_dry_run_blocking_always_false():
    for risk in ("low", "medium", "high"):
        record = run("gstack.review", risk)
        assert record.decision["blocking"] is False, f"blocking must be False for risk={risk}"


def test_dry_run_mode_disabled_by_default():
    """Feature flag is off by default → mode=disabled."""
    record = run("gstack.qa", "high")
    assert record.decision["mode"] == "disabled"


def test_dry_run_to_json_is_valid():
    record = run("gstack.plan_eng_review", "medium")
    raw = to_json(record)
    parsed = json.loads(raw)
    assert parsed["phase_id"] == "gstack.plan_eng_review"
    assert parsed["decision"]["blocking"] is False


def test_replay_record_produces_same_phase():
    original = run("gstack.review", "medium")
    replayed = replay_record(original)
    assert replayed.phase_id == original.phase_id
    assert replayed.risk_level == original.risk_level


def test_replay_json_roundtrip():
    original = run("gstack.qa", "high")
    raw = to_json(original)
    replayed = replay_json(raw)
    assert replayed.phase_id == "gstack.qa"
    assert replayed.decision["blocking"] is False
