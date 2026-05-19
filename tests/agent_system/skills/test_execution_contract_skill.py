"""
ExecutionContract skill.py — Regression Tests

验证：
  1. decision_agenda 议题生成 DecisionCard
  2. fake_closure 议题进入 skipped_fake_closure，不生成 contract
  3. 未确认的 decision_agenda 无 confirmed contract
  4. confirmation_json 触发 ExecutionContract 生成
  5. 缺 execution_owner 进入 incomplete_commitments
  6. 缺 verification_evidence 进入 incomplete_commitments
  7. consensus_ledger 记录各类状态
  8. follow_up_list 含 pending 条目
"""
from __future__ import annotations

import json

import pytest

from agent_system.skills.execution_contract.skill import run


def _issue(**kwargs) -> dict:
    defaults = dict(
        issue_id="issue_001",
        title="测试议题",
        background="背景",
        source_ref="weekly_2026_w20",
        urgency="medium",
        options=["方案A", "方案B"],
        recommended_option="方案B",
        owner_candidate=None,
        acceptance_criteria="Q3 达标",
    )
    defaults.update(kwargs)
    return defaults


def _routes(issue_id: str, route: str) -> str:
    return json.dumps({issue_id: route})


# ──────────────────────────────────────────────
# 1. decision_agenda 议题生成 DecisionCard
# ──────────────────────────────────────────────

def test_decision_agenda_generates_decision_card():
    issue = _issue()
    result = json.loads(run(
        json.dumps([issue]),
        _routes("issue_001", "decision_agenda"),
    ))
    cards = result["decision_cards"]
    assert len(cards) == 1
    assert cards[0]["issue_id"] == "issue_001"
    assert cards[0]["confirmed_by_human"] is False
    assert cards[0]["route"] == "decision_agenda"


# ──────────────────────────────────────────────
# 2. fake_closure 进入 skipped，不生成 contract
# ──────────────────────────────────────────────

def test_fake_closure_goes_to_skipped_list():
    issue = _issue(issue_id="issue_002", recommended_option="持续跟进并推动清库")
    result = json.loads(run(
        json.dumps([issue]),
        _routes("issue_002", "fake_closure_detected"),
    ))
    assert result["decision_cards"] == []
    assert result["execution_contracts"] == []
    skipped = result["consensus_ledger"]["skipped_fake_closure"]
    assert len(skipped) == 1
    assert skipped[0]["issue_id"] == "issue_002"
    assert skipped[0]["reason"] == "fake_closure_detected"


# ──────────────────────────────────────────────
# 3. 未确认的 decision_agenda 无 confirmed contract
# ──────────────────────────────────────────────

def test_unconfirmed_decision_agenda_no_confirmed_contract():
    issue = _issue()
    result = json.loads(run(
        json.dumps([issue]),
        _routes("issue_001", "decision_agenda"),
    ))
    assert result["execution_contracts"] == []
    assert result["consensus_ledger"]["confirmed_count"] == 0
    assert result["consensus_ledger"]["pending_count"] == 1


# ──────────────────────────────────────────────
# 4. confirmation_json 触发 ExecutionContract 生成
# ──────────────────────────────────────────────

def test_confirmation_json_generates_execution_contract():
    issue = _issue()
    confirmation = {
        "issue_001": {
            "decision": "方案B：涨价 8%",
            "execution_owner": "张三",
            "committed_action": "完成定价方案文档",
            "deadline": "2026-06-01",
            "acceptance_criteria": "文档通过 review",
            "verification_evidence": "review 签名截图",
        }
    }
    result = json.loads(run(
        json.dumps([issue]),
        _routes("issue_001", "decision_agenda"),
        json.dumps(confirmation),
    ))
    contracts = result["execution_contracts"]
    assert len(contracts) == 1
    assert contracts[0]["confirmed_by_human"] is True
    assert contracts[0]["current_status"] == "confirmed"
    assert contracts[0]["execution_owner"] == "张三"
    assert contracts[0]["missing_fields"] == []


# ──────────────────────────────────────────────
# 5. 缺 execution_owner 进入 incomplete_commitments
# ──────────────────────────────────────────────

def test_missing_owner_goes_to_incomplete_commitments():
    issue = _issue()
    confirmation = {
        "issue_001": {
            "decision": "方案B",
            "execution_owner": None,   # 缺失
            "committed_action": "完成文档",
            "deadline": "2026-06-01",
            "acceptance_criteria": "通过 review",
            "verification_evidence": "截图",
        }
    }
    result = json.loads(run(
        json.dumps([issue]),
        _routes("issue_001", "decision_agenda"),
        json.dumps(confirmation),
    ))
    contracts = result["execution_contracts"]
    assert len(contracts) == 1
    assert contracts[0]["current_status"] == "incomplete"
    assert "execution_owner" in contracts[0]["missing_fields"]
    incomplete = result["incomplete_commitments"]
    assert len(incomplete) == 1
    assert "execution_owner" in incomplete[0]["missing_fields"]


# ──────────────────────────────────────────────
# 6. 缺 verification_evidence 进入 incomplete_commitments
# ──────────────────────────────────────────────

def test_missing_verification_evidence_goes_to_incomplete():
    issue = _issue()
    confirmation = {
        "issue_001": {
            "decision": "方案B",
            "execution_owner": "张三",
            "committed_action": "完成文档",
            "deadline": "2026-06-01",
            "acceptance_criteria": "通过 review",
            "verification_evidence": None,   # 缺失
        }
    }
    result = json.loads(run(
        json.dumps([issue]),
        _routes("issue_001", "decision_agenda"),
        json.dumps(confirmation),
    ))
    assert result["execution_contracts"][0]["current_status"] == "incomplete"
    assert "verification_evidence" in result["execution_contracts"][0]["missing_fields"]


# ──────────────────────────────────────────────
# 7. consensus_ledger 记录各类状态
# ──────────────────────────────────────────────

def test_consensus_ledger_records_status():
    issues = [
        _issue(issue_id="i1", recommended_option="方案A"),
        _issue(issue_id="i2", recommended_option="持续跟进"),
    ]
    routes = json.dumps({"i1": "decision_agenda", "i2": "fake_closure_detected"})
    result = json.loads(run(json.dumps(issues), routes))
    ledger = result["consensus_ledger"]
    assert ledger["total_issues"] == 2
    assert ledger["pending_count"] == 1
    assert len(ledger["skipped_fake_closure"]) == 1


# ──────────────────────────────────────────────
# 8. follow_up_list 含 pending 条目
# ──────────────────────────────────────────────

def test_follow_up_list_has_pending_items():
    issue = _issue()
    result = json.loads(run(
        json.dumps([issue]),
        _routes("issue_001", "decision_agenda"),
    ))
    fu = result["follow_up_list"]
    assert fu["pending_count"] == 1
    assert fu["items"][0]["status"] == "pending_confirmation"
    assert fu["items"][0]["issue_id"] == "issue_001"
