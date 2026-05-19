"""
Weekly Flow Runtime E2E Tests — Phase 5

验证真实路径闭环：
  1. raw material → mock issue_extractor → decision_gate → DecisionCard
  2. ConfirmationEvent → confirmed ExecutionContract（via WeeklyLedgerStore）
  3. 缺字段 ConfirmationEvent → incomplete + follow_up
  4. fake_closure route → skipped，永不生成 contract
  5. ledger 持久化到 HERMES_HOME（隔离）
  6. 重复 event_id → 幂等，只有一个合同
  7. 重建 WeeklyLedgerStore 实例 → 仍能读取已有合同（recovery）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_system.schemas.weekly_schemas import ConfirmationEvent, Issue
from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore
from agent_system.evaluators.decision_gate import route_issues
from agent_system.skills.decision_gate.skill import run as dg_run


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def _full_issue(**kwargs) -> Issue:
    defaults = dict(
        issue_id="w5_001",
        title="X11 海外配件定价策略",
        background="配件利润率低于目标 5pp",
        source_ref="weekly_2026_w21",
        urgency="medium",
        options=["方案A", "方案B"],
        recommended_option="方案B：涨价 8%",
        owner_candidate="张三",
        acceptance_criteria="Q3 毛利率达到 35%",
    )
    defaults.update(kwargs)
    return Issue(**defaults)


def _full_event(**kwargs) -> ConfirmationEvent:
    defaults = dict(
        issue_id="w5_001",
        decision="方案B：涨价 8%",
        execution_owner="张三",
        committed_action="完成定价文档并通过 review",
        deadline="2026-06-01",
        acceptance_criteria="文档通过产品线 review",
        verification_evidence="review 签名截图",
    )
    defaults.update(kwargs)
    return ConfirmationEvent(**defaults)


# ──────────────────────────────────────────────
# 1. raw material → decision_gate → DecisionCard
# ──────────────────────────────────────────────

def test_material_to_decision_card(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent_system.skills.decision_gate.skill._AUDIT_PATH",
        tmp_path / "audit.jsonl",
    )
    issue = _full_issue()
    issues_json = json.dumps([{
        "issue_id": issue.issue_id, "title": issue.title,
        "background": issue.background, "source_ref": issue.source_ref,
        "urgency": issue.urgency, "options": issue.options,
        "recommended_option": issue.recommended_option,
        "owner_candidate": issue.owner_candidate,
        "acceptance_criteria": issue.acceptance_criteria,
    }])
    dg_result = json.loads(dg_run(issues_json, pipeline_run_id="w21"))
    assert dg_result["routes"]["w5_001"] == "decision_agenda"

    from agent_system.skills.execution_contract.skill import run as ec_run
    ec_result = json.loads(ec_run(issues_json, json.dumps(dg_result["routes"])))
    cards = ec_result["decision_cards"]
    assert len(cards) == 1
    assert cards[0]["confirmed_by_human"] is False


# ──────────────────────────────────────────────
# 2. ConfirmationEvent → confirmed ExecutionContract
# ──────────────────────────────────────────────

def test_confirmation_event_generates_contract(hermes_home):
    store = WeeklyLedgerStore(hermes_home)
    issue = _full_issue()
    event = _full_event()

    contract = store.apply_event(event, issue)
    assert contract is not None
    assert contract.confirmed_by_human is True
    assert contract.current_status == "confirmed"
    assert contract.missing_fields() == []


# ──────────────────────────────────────────────
# 3. 缺字段 ConfirmationEvent → incomplete + follow_up
# ──────────────────────────────────────────────

def test_missing_field_stays_incomplete(hermes_home):
    store = WeeklyLedgerStore(hermes_home)
    issue = _full_issue()
    event = _full_event(execution_owner=None, verification_evidence=None)

    contract = store.apply_event(event, issue)
    assert contract.current_status == "incomplete"
    assert "execution_owner" in contract.missing_fields()
    assert "verification_evidence" in contract.missing_fields()

    ledger = store.load()
    assert len(ledger.incomplete_commitments) == 1


# ──────────────────────────────────────────────
# 4. fake_closure → skipped，永不生成 contract
# ──────────────────────────────────────────────

def test_fake_closure_never_generates_contract(hermes_home):
    store = WeeklyLedgerStore(hermes_home)
    issue = _full_issue(recommended_option="持续跟进并推动清库")
    route = route_issues([issue])
    assert route[issue.issue_id] == "fake_closure_detected"

    # fake_closure 不能调用 apply_event → 如果强行调用也应被拒绝
    event = _full_event(issue_id=issue.issue_id)
    contract = store.apply_event(event, issue, route=route[issue.issue_id])
    assert contract is None   # fake_closure 路由下 apply_event 必须返回 None


# ──────────────────────────────────────────────
# 5. ledger 持久化到 HERMES_HOME
# ──────────────────────────────────────────────

def test_ledger_persists_to_hermes_home(hermes_home):
    store = WeeklyLedgerStore(hermes_home)
    issue = _full_issue()
    event = _full_event()

    store.apply_event(event, issue)

    ledger_path = hermes_home / "weekly_flow" / "ledger.json"
    assert ledger_path.exists()
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data["total_issues"] >= 1


# ──────────────────────────────────────────────
# 6. 重复 event_id → 幂等，只有一个合同
# ──────────────────────────────────────────────

def test_duplicate_callback_idempotent(hermes_home):
    store = WeeklyLedgerStore(hermes_home)
    issue = _full_issue()
    event = _full_event(event_id="fixed_event_001")

    c1 = store.apply_event(event, issue)
    c2 = store.apply_event(event, issue)

    assert c1.contract_id == c2.contract_id   # 同一合同

    ledger = store.load()
    confirmed_ids = [c["contract_id"] for c in ledger.confirmed_contracts
                     if isinstance(c, dict)]
    if not confirmed_ids:  # dataclass list
        confirmed_ids = [c.contract_id for c in ledger.confirmed_contracts]
    assert len(confirmed_ids) == 1


# ──────────────────────────────────────────────
# 7. recovery：新建实例仍能读取已有合同
# ──────────────────────────────────────────────

def test_recovery_reads_existing_ledger(hermes_home):
    # 第一个实例写入
    store1 = WeeklyLedgerStore(hermes_home)
    issue = _full_issue()
    event = _full_event()
    contract = store1.apply_event(event, issue)

    # 第二个独立实例读取
    store2 = WeeklyLedgerStore(hermes_home)
    ledger = store2.load()

    found_ids = [c.contract_id if hasattr(c, "contract_id") else c["contract_id"]
                 for c in ledger.confirmed_contracts]
    assert contract.contract_id in found_ids
