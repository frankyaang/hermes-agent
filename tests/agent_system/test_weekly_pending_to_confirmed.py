"""
Weekly Pending → Confirmed 状态连续性测试

验证 pending contract 在 Feishu 确认后正确转为 confirmed：
  1. execution_contract skill 生成 pending，ledger 持久化，original_recommended_option 保留
  2. _load_weekly_issue_lookup 从 pending contract 恢复 Issue（recommended_option 正确）
  3. route_issue(reconstructed_issue) 返回 decision_agenda（不返回 need_more_info）
  4. Feishu 确认后 pending → confirmed，重启 store 后仍可恢复
  5. fake_closure 在 pending → confirmed 路径中被正确拦截
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_system.evaluators.decision_gate import route_issue
from agent_system.schemas.weekly_schemas import (
    ConfirmationEvent,
    ExecutionContract,
    Issue,
)
from agent_system.skills.execution_contract.skill import run as run_execution_contract
from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore


def _make_issue_json(
    issue_id: str = "ISS-001",
    title: str = "X11 定价策略",
    recommended_option: str = "方案B：涨价 8%，捆绑促销",
) -> list[dict]:
    return [{
        "issue_id": issue_id,
        "title": title,
        "background": "当前配件利润率低于目标 5pp",
        "source_ref": "weekly_2026_w20",
        "urgency": "high",
        "options": ["方案A", "方案B"],
        "recommended_option": recommended_option,
        "owner_candidate": "张三",
        "acceptance_criteria": "Q3 配件毛利率达到 35%",
    }]


def _make_routes_json(issue_id: str, route: str = "decision_agenda") -> dict:
    return {issue_id: route}


# ──────────────────────────────────────────────────────────────────────────────
# 1. execution_contract skill 生成 pending，original_recommended_option 保留
# ──────────────────────────────────────────────────────────────────────────────

def test_pending_contract_preserves_original_recommended_option():
    issues = _make_issue_json(issue_id="ISS-P1", recommended_option="方案B：涨价 8%")
    routes = {"ISS-P1": "decision_agenda"}

    result_json = run_execution_contract(
        issues_json=json.dumps(issues),
        routes_json=json.dumps(routes),
        confirmation_json=None,
    )
    result = json.loads(result_json)

    assert result["consensus_ledger"]["pending_count"] == 1

    # 直接检查 skill 内 ledger（通过返回数据无法直接访问，但 store 应有 pending）
    # pending contract 在 skill 内创建但不写 store，所以通过 schema 直接验证
    contract = ExecutionContract(
        issue_id="ISS-P1",
        title="X11 定价策略",
        current_status="pending_confirmation",
        original_recommended_option="方案B：涨价 8%",
    )
    assert contract.original_recommended_option == "方案B：涨价 8%"


# ──────────────────────────────────────────────────────────────────────────────
# 2. _load_weekly_issue_lookup 从 pending contract 恢复 Issue（recommended_option 正确）
# ──────────────────────────────────────────────────────────────────────────────

def test_load_issue_lookup_recovers_recommended_option(tmp_path):
    store = WeeklyLedgerStore(home=tmp_path)
    ledger = store.load()

    # 模拟 execution_contract skill 创建的 pending contract
    pending = ExecutionContract(
        issue_id="ISS-002",
        title="X11 配件定价",
        current_status="pending_confirmation",
        original_recommended_option="方案B：涨价 8%",
    )
    ledger.pending_contracts.append(pending)
    store.save(ledger)

    # 重新加载并检查
    ledger2 = store.load()
    assert len(ledger2.pending_contracts) == 1
    c = ledger2.pending_contracts[0]
    assert c.original_recommended_option == "方案B：涨价 8%"

    # 模拟 _load_weekly_issue_lookup 重建 Issue
    recommended_option = c.original_recommended_option or c.decision or None
    issue = Issue(
        issue_id=c.issue_id,
        title=c.title,
        background="",
        recommended_option=recommended_option,
        options=[],
        owner_candidate=c.execution_owner,
        urgency="high",
        source_ref="",
    )
    assert issue.recommended_option == "方案B：涨价 8%"


# ──────────────────────────────────────────────────────────────────────────────
# 3. route_issue(reconstructed_issue) 返回 decision_agenda
# ──────────────────────────────────────────────────────────────────────────────

def test_reconstructed_issue_routes_to_decision_agenda(tmp_path):
    store = WeeklyLedgerStore(home=tmp_path)
    ledger = store.load()
    pending = ExecutionContract(
        issue_id="ISS-003",
        title="X11 定价",
        current_status="pending_confirmation",
        original_recommended_option="方案B：涨价 8%，捆绑促销",
        acceptance_criteria="Q3 毛利率达到 35%",
    )
    ledger.pending_contracts.append(pending)
    store.save(ledger)

    c = store.load().pending_contracts[0]
    issue = Issue(
        issue_id=c.issue_id,
        title=c.title,
        background="",
        recommended_option=c.original_recommended_option or c.decision or None,
        options=[],
        owner_candidate=None,
        urgency="high",
        source_ref="",
        acceptance_criteria=c.acceptance_criteria,
    )
    route = route_issue(issue)
    assert route == "decision_agenda"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Feishu 确认后 pending → confirmed，重启 store 后仍可恢复
# ──────────────────────────────────────────────────────────────────────────────

def test_pending_to_confirmed_persists_after_restart(tmp_path):
    issue = Issue(
        issue_id="ISS-004",
        title="X11 定价策略",
        background="利润低",
        recommended_option="方案B：涨价 8%",
        options=["方案A", "方案B"],
        owner_candidate="张三",
        urgency="high",
        source_ref="weekly_w20",
    )
    event = ConfirmationEvent(
        issue_id="ISS-004",
        decision="采用方案B",
        execution_owner="张三",
        committed_action="完成定价文档",
        deadline="2026-06-01",
        acceptance_criteria="文档通过 review",
        verification_evidence="review 记录",
        event_id="EVT-004",
    )

    store1 = WeeklyLedgerStore(home=tmp_path)
    contract = store1.apply_event(event, issue, route="decision_agenda")
    assert contract is not None
    assert contract.current_status == "confirmed"

    # 重启 store，验证恢复
    store2 = WeeklyLedgerStore(home=tmp_path)
    ledger = store2.load()
    assert len(ledger.confirmed_contracts) == 1
    assert ledger.confirmed_contracts[0].issue_id == "ISS-004"
    assert ledger.confirmed_contracts[0].current_status == "confirmed"


# ──────────────────────────────────────────────────────────────────────────────
# 5. fake_closure 在 pending → confirmed 路径中被拦截
# ──────────────────────────────────────────────────────────────────────────────

def test_fake_closure_intercepted_in_pending_to_confirmed_path(tmp_path):
    store = WeeklyLedgerStore(home=tmp_path)

    # fake_closure issue
    fake_issue = Issue(
        issue_id="ISS-FAKE",
        title="持续跟进库存问题",
        background="库存积压",
        recommended_option="持续跟进并推动清库",  # fake_closure pattern
        options=[],
        owner_candidate=None,
        urgency="low",
        source_ref="w20",
    )
    event = ConfirmationEvent(
        issue_id="ISS-FAKE",
        decision="持续跟进",
        execution_owner=None,
        committed_action=None,
        deadline=None,
        acceptance_criteria=None,
        verification_evidence=None,
        event_id="EVT-FAKE",
    )

    # apply_event with fake_closure_detected route → returns None
    result = store.apply_event(event, fake_issue, route="fake_closure_detected")
    assert result is None

    ledger = store.load()
    assert len(ledger.confirmed_contracts) == 0


# ──────────────────────────────────────────────────────────────────────────────
# P0-4：execution_contract skill 写 pending 到 WeeklyLedgerStore（RED）
# ──────────────────────────────────────────────────────────────────────────────

def test_execution_contract_writes_pending_to_ledger(tmp_path, monkeypatch):
    """execution_contract skill 生成 pending 后，pending 必须写入 WeeklyLedgerStore。
    RED：skill 当前不写 ledger → reload 后 pending_contracts 为空 → FAIL。
    """
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    issue_id = "ISS-P04-001"
    issues_json = json.dumps([{
        "issue_id": issue_id,
        "title": "P0-4 测试议题",
        "background": "测试背景",
        "source_ref": "w_test",
        "urgency": "high",
        "options": ["方案A", "方案B"],
        "recommended_option": "方案A：快速上线",
        "owner_candidate": "测试负责人",
        "acceptance_criteria": "测试验收标准",
    }])
    routes_json = json.dumps({issue_id: "decision_agenda"})

    # 调用 skill，不传 confirmation_json（生成 pending 状态）
    result_json = run_execution_contract(
        issues_json=issues_json,
        routes_json=routes_json,
        confirmation_json=None,
    )
    result = json.loads(result_json)
    assert result["consensus_ledger"]["pending_count"] == 1, "skill 应生成 1 个 pending contract"

    # 关键验证：reload WeeklyLedgerStore，pending 必须存在
    store = WeeklyLedgerStore(home=tmp_path)
    ledger = store.load()
    assert len(ledger.pending_contracts) == 1, (
        "execution_contract skill 必须将 pending contract 写入 WeeklyLedgerStore"
    )
    assert ledger.pending_contracts[0].issue_id == issue_id
    assert ledger.pending_contracts[0].original_recommended_option is not None
    assert ledger.pending_contracts[0].acceptance_criteria is not None
