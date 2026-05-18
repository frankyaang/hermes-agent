"""
agent_system.weekly — Weekly flow subsystem.

Chain: issue_extractor → decision_gate → confirmation → ledger → ExecutionContract

All persistent state writes to get_hermes_home() / "weekly" /.
fake_closure is always rejected — no ExecutionContract generated.
Ledger is idempotent: repeated callbacks for same issue_id return same contract.
"""
from .models import DecisionCard, ExecutionContract, ConfirmationEvent, IssueSpec
from .issue_extractor import extract_issues
from .decision_gate import evaluate as evaluate_decision
from .ledger import WeeklyLedger
from .confirmation import make_confirmation_event

__all__ = [
    "DecisionCard",
    "ExecutionContract",
    "ConfirmationEvent",
    "IssueSpec",
    "extract_issues",
    "evaluate_decision",
    "WeeklyLedger",
    "make_confirmation_event",
]
