"""
Weekly Flow Runtime E2E Tests (W1–W7)

These tests define the contract for the Weekly flow subsystem.
They must ALL FAIL before implementation (Phase A).
They must ALL PASS after implementation (Phase B).

HERMES_HOME is automatically isolated to a per-test tmpdir by conftest.py
_hermetic_environment autouse fixture — no manual setup needed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# ── W1 ────────────────────────────────────────────────────────────────────────

def test_raw_material_to_decision_card():
    """Raw weekly material → issue_extractor → decision_gate → DecisionCard."""
    from agent_system.weekly.issue_extractor import extract_issues
    from agent_system.weekly.decision_gate import evaluate as gate_evaluate
    from agent_system.weekly.models import DecisionCard

    material = {
        "week": "2026-W20",
        "items": [
            {
                "title": "API latency regression",
                "owner": "alice",
                "status": "open",
                "priority": "high",
                "description": "P99 jumped from 120ms to 340ms on Monday",
            }
        ],
    }
    issues = extract_issues(material)
    assert len(issues) >= 1
    assert issues[0].title == "API latency regression"
    assert issues[0].owner == "alice"

    card = gate_evaluate(issues)
    assert card is not None
    assert isinstance(card, DecisionCard)
    assert card.status == "pending_confirmation"
    assert card.issue_id != ""
    assert len(card.missing_fields) == 0


# ── W2 ────────────────────────────────────────────────────────────────────────

def test_owner_confirmation_creates_contract():
    """Confirmed DecisionCard + owner event → ExecutionContract written to ledger."""
    from agent_system.weekly.issue_extractor import extract_issues
    from agent_system.weekly.decision_gate import evaluate as gate_evaluate
    from agent_system.weekly.confirmation import make_confirmation_event
    from agent_system.weekly.ledger import WeeklyLedger
    from agent_system.weekly.models import ExecutionContract

    material = {
        "week": "2026-W20",
        "items": [
            {
                "title": "DB connection leak",
                "owner": "bob",
                "status": "open",
                "priority": "critical",
                "description": "Connection pool exhausted every ~6h",
            }
        ],
    }
    issues = extract_issues(material)
    card = gate_evaluate(issues)
    assert card is not None
    assert card.status == "pending_confirmation"

    event = make_confirmation_event(
        issue_id=card.issue_id,
        decision="confirmed",
        owner_id="bob",
        channel="test_mock",
    )
    ledger = WeeklyLedger()
    contract = ledger.process_confirmation(card, event)

    assert isinstance(contract, ExecutionContract)
    assert contract.issue_id == card.issue_id
    assert contract.confirmed_by == "bob"
    assert contract.confirmation_channel == "test_mock"
    assert contract.contract_hash != ""


# ── W3 ────────────────────────────────────────────────────────────────────────

def test_missing_fields_incomplete_and_followup():
    """Issue with missing required fields → DecisionCard(status=incomplete) + follow_up."""
    from agent_system.weekly.issue_extractor import extract_issues
    from agent_system.weekly.decision_gate import evaluate as gate_evaluate
    from agent_system.weekly.models import DecisionCard

    # Missing owner and description
    material = {
        "week": "2026-W20",
        "items": [
            {
                "title": "Mysterious spike",
                # owner missing
                "status": "open",
                "priority": "medium",
                # description missing
            }
        ],
    }
    issues = extract_issues(material)
    card = gate_evaluate(issues)

    assert card is not None
    assert isinstance(card, DecisionCard)
    assert card.status == "incomplete"
    assert len(card.missing_fields) >= 1
    assert len(card.follow_up) >= 1
    # follow_up items must be actionable strings
    for f in card.follow_up:
        assert isinstance(f, str) and len(f) > 0


# ── W4 ────────────────────────────────────────────────────────────────────────

def test_fake_closure_rejected_no_contract():
    """fake_closure_detected → gate returns None, no ExecutionContract can be created."""
    from agent_system.weekly.issue_extractor import extract_issues
    from agent_system.weekly.decision_gate import evaluate as gate_evaluate
    from agent_system.weekly.models import IssueSpec

    # Fake closure: status=closed but no real resolution evidence
    fake_issues = [
        IssueSpec(
            title="Cache miss rate",
            owner="carol",
            status="closed",
            priority="low",
            description="",  # empty description = no real resolution
            is_fake_closure=True,
        )
    ]
    card = gate_evaluate(fake_issues)
    assert card is None, "fake_closure must return None — no contract may be generated"


# ── W5 ────────────────────────────────────────────────────────────────────────

def test_ledger_persists_to_disk():
    """ExecutionContract is written to disk under HERMES_HOME/weekly/ledger.json."""
    from agent_system.weekly.issue_extractor import extract_issues
    from agent_system.weekly.decision_gate import evaluate as gate_evaluate
    from agent_system.weekly.confirmation import make_confirmation_event
    from agent_system.weekly.ledger import WeeklyLedger
    from hermes_constants import get_hermes_home

    material = {
        "week": "2026-W20",
        "items": [
            {
                "title": "Memory growth",
                "owner": "dave",
                "status": "open",
                "priority": "high",
                "description": "RSS grows 50MB/day",
            }
        ],
    }
    issues = extract_issues(material)
    card = gate_evaluate(issues)
    assert card is not None

    event = make_confirmation_event(
        issue_id=card.issue_id,
        decision="confirmed",
        owner_id="dave",
        channel="test_mock",
    )
    ledger = WeeklyLedger()
    contract = ledger.process_confirmation(card, event)
    assert contract is not None

    # Verify file on disk
    ledger_path = get_hermes_home() / "weekly" / "ledger.json"
    assert ledger_path.exists(), f"ledger.json not found at {ledger_path}"
    data = json.loads(ledger_path.read_text())
    assert card.issue_id in data
    assert data[card.issue_id]["confirmed_by"] == "dave"


# ── W6 ────────────────────────────────────────────────────────────────────────

def test_callback_idempotent_no_duplicate():
    """Repeated confirmation callbacks for same issue_id → no duplicate contracts."""
    from agent_system.weekly.issue_extractor import extract_issues
    from agent_system.weekly.decision_gate import evaluate as gate_evaluate
    from agent_system.weekly.confirmation import make_confirmation_event
    from agent_system.weekly.ledger import WeeklyLedger
    from agent_system.weekly.models import ExecutionContract

    material = {
        "week": "2026-W20",
        "items": [
            {
                "title": "CPU throttling",
                "owner": "eve",
                "status": "open",
                "priority": "high",
                "description": "k8s throttling at 80% cpu request",
            }
        ],
    }
    issues = extract_issues(material)
    card = gate_evaluate(issues)
    assert card is not None

    event = make_confirmation_event(
        issue_id=card.issue_id,
        decision="confirmed",
        owner_id="eve",
        channel="test_mock",
    )
    ledger = WeeklyLedger()
    contract1 = ledger.process_confirmation(card, event)
    contract2 = ledger.process_confirmation(card, event)  # duplicate call

    assert isinstance(contract1, ExecutionContract)
    assert isinstance(contract2, ExecutionContract)
    # Same contract returned, not duplicated
    assert contract1.contract_hash == contract2.contract_hash

    # Only one entry in ledger
    from hermes_constants import get_hermes_home
    ledger_path = get_hermes_home() / "weekly" / "ledger.json"
    data = json.loads(ledger_path.read_text())
    issue_entries = [v for k, v in data.items() if k == card.issue_id]
    assert len(issue_entries) == 1, "idempotent: must not create duplicate ledger entries"


# ── W7 ────────────────────────────────────────────────────────────────────────

def test_ledger_recoverable_after_restart():
    """After 'restart' (new WeeklyLedger object), can read existing ledger/follow_up."""
    from agent_system.weekly.issue_extractor import extract_issues
    from agent_system.weekly.decision_gate import evaluate as gate_evaluate
    from agent_system.weekly.confirmation import make_confirmation_event
    from agent_system.weekly.ledger import WeeklyLedger

    material = {
        "week": "2026-W20",
        "items": [
            {
                "title": "Disk I/O spike",
                "owner": "frank",
                "status": "open",
                "priority": "high",
                "description": "Sequential writes degrade to 5 MB/s",
            }
        ],
    }
    issues = extract_issues(material)
    card = gate_evaluate(issues)
    assert card is not None

    event = make_confirmation_event(
        issue_id=card.issue_id,
        decision="confirmed",
        owner_id="frank",
        channel="test_mock",
    )
    ledger1 = WeeklyLedger()
    ledger1.process_confirmation(card, event)

    # Simulate restart: new ledger object, same HERMES_HOME
    ledger2 = WeeklyLedger()
    all_contracts = ledger2.list_contracts()
    assert len(all_contracts) >= 1
    found = any(c.issue_id == card.issue_id for c in all_contracts)
    assert found, "recovered ledger must contain the previously confirmed contract"

    # Also verify follow_up store is readable
    follow_ups = ledger2.list_follow_ups()
    assert isinstance(follow_ups, list)
