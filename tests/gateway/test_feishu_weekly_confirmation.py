"""
Feishu Weekly Confirmation Handler Tests

验证 weekly_confirmation 真实入口行为：
  1. type != "weekly_confirmation" → None（安全忽略）
  2. issue_id 缺失 → None
  3. 合法确认 payload → store.apply_event 被调用，返回 contract
  4. fake_closure 路由 → None（拦截，不写 ledger）
  5. 相同 event_id 两次 → 幂等，返回已有 contract
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_system.adapters.weekly_confirmation_handler import (
    handle_weekly_confirmation_payload,
)
from agent_system.schemas.weekly_schemas import (
    ConfirmationEvent,
    Issue,
)
from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore


def _make_issue(issue_id: str = "ISS-001", title: str = "测试议题") -> Issue:
    return Issue(
        issue_id=issue_id,
        title=title,
        background="背景说明",
        recommended_option="方案A",
        options=["方案A", "方案B"],
        owner_candidate="张三",
        urgency="high",
        source_ref="weekly_2026w20",
    )


def _full_payload(issue_id: str = "ISS-001", event_id: str = "EVT-001") -> dict:
    return {
        "action": {
            "value": {
                "type": "weekly_confirmation",
                "issue_id": issue_id,
                "event_id": event_id,
                "decision": "采用方案A",
                "execution_owner": "张三",
                "committed_action": "完成定价方案文档",
                "deadline": "2026-06-01",
                "acceptance_criteria": "文档通过产品线 review",
                "verification_evidence": "review 记录截图",
            }
        }
    }


# 1. 非 weekly_confirmation type → None（安全忽略）
def test_non_weekly_type_returns_none(tmp_path):
    payload = {"action": {"value": {"type": "some_other_type", "issue_id": "ISS-001"}}}
    store = WeeklyLedgerStore(home=tmp_path)
    result = handle_weekly_confirmation_payload(payload, issue_lookup={}, store=store)
    assert result is None


# 2. issue_id 缺失 → None
def test_missing_issue_id_returns_none(tmp_path):
    payload = {"action": {"value": {"type": "weekly_confirmation"}}}
    store = WeeklyLedgerStore(home=tmp_path)
    result = handle_weekly_confirmation_payload(payload, issue_lookup={}, store=store)
    assert result is None


# 3. 合法确认 → contract 生成，store.apply_event 被调用
def test_valid_confirmation_generates_contract(tmp_path):
    issue = _make_issue()
    payload = _full_payload(issue_id="ISS-001")
    store = WeeklyLedgerStore(home=tmp_path)

    result = handle_weekly_confirmation_payload(
        payload,
        issue_lookup={"ISS-001": issue},
        store=store,
    )

    assert result is not None
    assert result.issue_id == "ISS-001"
    assert result.execution_owner == "张三"
    assert result.current_status == "confirmed"

    # 验证 ledger 已写入
    ledger = store.load()
    assert len(ledger.confirmed_contracts) == 1


# 4. fake_closure 路由 → None，不写 ledger
def test_fake_closure_issue_returns_none(tmp_path):
    # fake_closure issue: recommended_option 含伪闭环语言
    issue = _make_issue()
    issue.recommended_option = "持续跟进并推动落实"
    payload = _full_payload(issue_id="ISS-001")
    store = WeeklyLedgerStore(home=tmp_path)

    result = handle_weekly_confirmation_payload(
        payload,
        issue_lookup={"ISS-001": issue},
        store=store,
    )

    assert result is None
    # ledger 未写入任何合同
    ledger = store.load()
    assert len(ledger.confirmed_contracts) == 0


# 5. 相同 event_id 两次 → 幂等
def test_duplicate_event_id_idempotent(tmp_path):
    issue = _make_issue()
    payload = _full_payload(issue_id="ISS-001", event_id="EVT-FIXED")
    store = WeeklyLedgerStore(home=tmp_path)

    r1 = handle_weekly_confirmation_payload(
        payload, issue_lookup={"ISS-001": issue}, store=store
    )
    r2 = handle_weekly_confirmation_payload(
        payload, issue_lookup={"ISS-001": issue}, store=store
    )

    assert r1 is not None
    assert r2 is not None
    assert r1.contract_id == r2.contract_id

    ledger = store.load()
    assert len(ledger.confirmed_contracts) == 1
