"""
DecisionGate skill.py — Regression Tests

验证：
  1. 完整议题路由为 decision_agenda
  2. fake_closure 议题路由为 fake_closure_detected
  3. 输出 JSON 包含 routes 字段
  4. audit.jsonl 写入路由记录
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_system.skills.decision_gate.skill import run


def _issue_json(**kwargs) -> dict:
    defaults = dict(
        issue_id="issue_001",
        title="测试议题",
        background="背景说明",
        source_ref="weekly_2026_w20",
        urgency="medium",
        options=["方案A", "方案B"],
        recommended_option=None,
        owner_candidate=None,
        acceptance_criteria=None,
    )
    defaults.update(kwargs)
    return defaults


# ──────────────────────────────────────────────
# 1. 完整议题路由为 decision_agenda
# ──────────────────────────────────────────────

def test_complete_issue_routes_to_decision_agenda(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        tmp_path / "audit.jsonl",
    )
    issue = _issue_json(
        recommended_option="方案B：涨价 8%",
        acceptance_criteria="Q3 毛利率达到 35%",
    )
    result_str = run(json.dumps([issue]))
    result = json.loads(result_str)
    assert result["routes"]["issue_001"] == "decision_agenda"


# ──────────────────────────────────────────────
# 2. fake_closure 议题路由为 fake_closure_detected
# ──────────────────────────────────────────────

def test_fake_closure_issue_routes_correctly(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        tmp_path / "audit.jsonl",
    )
    issue = _issue_json(
        recommended_option="持续跟进并推动清库",
        acceptance_criteria="Q3 达标",
    )
    result_str = run(json.dumps([issue]))
    result = json.loads(result_str)
    assert result["routes"]["issue_001"] == "fake_closure_detected"


# ──────────────────────────────────────────────
# 3. 输出 JSON 包含 routes 字段
# ──────────────────────────────────────────────

def test_output_contains_routes_key(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        tmp_path / "audit.jsonl",
    )
    issue = _issue_json(recommended_option="方案A", acceptance_criteria="指标X")
    result_str = run(json.dumps([issue]))
    result = json.loads(result_str)
    assert "routes" in result
    assert isinstance(result["routes"], dict)


# ──────────────────────────────────────────────
# 4. audit.jsonl 写入路由记录
# ──────────────────────────────────────────────

def test_audit_log_written(tmp_path, monkeypatch):
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        audit_path,
    )
    issue = _issue_json(recommended_option="方案A", acceptance_criteria="指标X")
    run(json.dumps([issue]), pipeline_run_id="run_001")

    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "decision_gate_route"
    assert record["pipeline_id"] == "weekly_flow"
    assert record["pipeline_run_id"] == "run_001"
    assert record["issue_id"] == "issue_001"
    assert record["route"] == "decision_agenda"
