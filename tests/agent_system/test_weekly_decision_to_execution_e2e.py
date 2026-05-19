"""
Weekly Decision-to-Execution E2E Tests

端到端验证 Issue → DecisionGate → execution_contract/skill 全链路：
  1. Issue → DecisionGate → decision_agenda → DecisionCard
  2. Issue → DecisionGate → confirmation → ExecutionContract
  3. Issue (fake closure) → skipped_fake_closure
  4. 缺字段 → incomplete_commitments → follow_up_list
"""
from __future__ import annotations

import json

from agent_system.evaluators.decision_gate import route_issues
from agent_system.schemas.weekly_schemas import Issue
from agent_system.skills.execution_contract.skill import run as ec_run
from agent_system.skills.decision_gate.skill import run as dg_run


def _make_issue(**kwargs) -> Issue:
    defaults = dict(
        issue_id="e2e_001",
        title="X11 海外配件定价策略",
        background="配件利润率低于目标 5pp",
        source_ref="weekly_2026_w20",
        urgency="medium",
        options=["方案A", "方案B"],
        recommended_option="方案B：涨价 8%，捆绑促销",
        owner_candidate="张三",
        acceptance_criteria="Q3 配件毛利率达到 35%",
    )
    defaults.update(kwargs)
    return Issue(**defaults)


# ──────────────────────────────────────────────
# 1. Issue → DecisionGate → decision_agenda → DecisionCard
# ──────────────────────────────────────────────

def test_mini_e2e_issue_to_decision_card(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        tmp_path / "audit.jsonl",
    )
    issue = _make_issue()
    issues_json = json.dumps([{
        "issue_id": issue.issue_id,
        "title": issue.title,
        "background": issue.background,
        "source_ref": issue.source_ref,
        "urgency": issue.urgency,
        "options": issue.options,
        "recommended_option": issue.recommended_option,
        "owner_candidate": issue.owner_candidate,
        "acceptance_criteria": issue.acceptance_criteria,
    }])

    # Step 1: decision_gate
    dg_result = json.loads(dg_run(issues_json))
    assert dg_result["routes"]["e2e_001"] == "decision_agenda"

    # Step 2: execution_contract（无确认，只生成 DecisionCard）
    ec_result = json.loads(ec_run(issues_json, json.dumps(dg_result["routes"])))
    cards = ec_result["decision_cards"]
    assert len(cards) == 1
    assert cards[0]["issue_id"] == "e2e_001"
    assert cards[0]["confirmed_by_human"] is False
    assert ec_result["execution_contracts"] == []


# ──────────────────────────────────────────────
# 2. Issue → DecisionGate → confirmation → ExecutionContract
# ──────────────────────────────────────────────

def test_mini_e2e_issue_to_confirmed_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        tmp_path / "audit.jsonl",
    )
    issue = _make_issue()
    issues_json = json.dumps([{
        "issue_id": issue.issue_id,
        "title": issue.title,
        "background": issue.background,
        "source_ref": issue.source_ref,
        "urgency": issue.urgency,
        "options": issue.options,
        "recommended_option": issue.recommended_option,
        "owner_candidate": issue.owner_candidate,
        "acceptance_criteria": issue.acceptance_criteria,
    }])

    dg_result = json.loads(dg_run(issues_json))
    assert dg_result["routes"]["e2e_001"] == "decision_agenda"

    confirmation = {
        "e2e_001": {
            "decision": "方案B：涨价 8%",
            "execution_owner": "张三",
            "committed_action": "完成定价方案文档并完成产品线 review",
            "deadline": "2026-06-01",
            "acceptance_criteria": "文档通过产品线 review",
            "verification_evidence": "review 签名截图",
        }
    }
    ec_result = json.loads(ec_run(
        issues_json,
        json.dumps(dg_result["routes"]),
        json.dumps(confirmation),
    ))
    contracts = ec_result["execution_contracts"]
    assert len(contracts) == 1
    assert contracts[0]["confirmed_by_human"] is True
    assert contracts[0]["current_status"] == "confirmed"
    assert contracts[0]["missing_fields"] == []
    assert ec_result["consensus_ledger"]["confirmed_count"] == 1


# ──────────────────────────────────────────────
# 3. fake_closure → skipped_fake_closure
# ──────────────────────────────────────────────

def test_mini_e2e_fake_closure_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        tmp_path / "audit.jsonl",
    )
    issue = _make_issue(
        issue_id="e2e_002",
        recommended_option="持续跟进并推动清库",
        acceptance_criteria="Q3 达标",
    )
    issues_json = json.dumps([{
        "issue_id": issue.issue_id,
        "title": issue.title,
        "background": issue.background,
        "source_ref": issue.source_ref,
        "urgency": issue.urgency,
        "options": issue.options,
        "recommended_option": issue.recommended_option,
        "owner_candidate": issue.owner_candidate,
        "acceptance_criteria": issue.acceptance_criteria,
    }])

    dg_result = json.loads(dg_run(issues_json))
    assert dg_result["routes"]["e2e_002"] == "fake_closure_detected"

    ec_result = json.loads(ec_run(issues_json, json.dumps(dg_result["routes"])))
    assert ec_result["decision_cards"] == []
    assert ec_result["execution_contracts"] == []
    skipped = ec_result["consensus_ledger"]["skipped_fake_closure"]
    assert len(skipped) == 1
    assert skipped[0]["issue_id"] == "e2e_002"


# ──────────────────────────────────────────────
# 4. 缺字段 → incomplete_commitments → follow_up_list
# ──────────────────────────────────────────────

def test_mini_e2e_incomplete_contract_in_follow_up(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        tmp_path / "audit.jsonl",
    )
    issue = _make_issue()
    issues_json = json.dumps([{
        "issue_id": issue.issue_id,
        "title": issue.title,
        "background": issue.background,
        "source_ref": issue.source_ref,
        "urgency": issue.urgency,
        "options": issue.options,
        "recommended_option": issue.recommended_option,
        "owner_candidate": issue.owner_candidate,
        "acceptance_criteria": issue.acceptance_criteria,
    }])

    dg_result = json.loads(dg_run(issues_json))

    # 提供确认但缺少两个字段
    confirmation = {
        "e2e_001": {
            "decision": "方案B",
            "execution_owner": None,               # 缺失
            "committed_action": "完成定价文档",
            "deadline": "2026-06-01",
            "acceptance_criteria": "通过 review",
            "verification_evidence": None,          # 缺失
        }
    }
    ec_result = json.loads(ec_run(
        issues_json,
        json.dumps(dg_result["routes"]),
        json.dumps(confirmation),
    ))
    assert ec_result["execution_contracts"][0]["current_status"] == "incomplete"
    missing = ec_result["execution_contracts"][0]["missing_fields"]
    assert "execution_owner" in missing
    assert "verification_evidence" in missing

    fu = ec_result["follow_up_list"]
    assert fu["items"][0]["status"] == "incomplete"
    assert len(ec_result["incomplete_commitments"]) == 1
