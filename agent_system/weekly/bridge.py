"""
WeeklyFlowBridge — chains issue_extractor → decision_gate → ledger.

Used by agent_system runtime to run the weekly flow pipeline.
Not called directly by users — invoked via WeeklyFlowBridge.run().
"""
from __future__ import annotations

import logging
from typing import Any

from .confirmation import make_confirmation_event, parse_feishu_reply
from .decision_gate import evaluate as gate_evaluate
from .issue_extractor import extract_issues
from .ledger import WeeklyLedger
from .models import ConfirmationEvent, DecisionCard, ExecutionContract

logger = logging.getLogger(__name__)


class WeeklyFlowBridge:
    """
    Orchestrates the weekly flow from raw material to ExecutionContract.

    Usage:
        bridge = WeeklyFlowBridge()
        card = bridge.process_material(material)
        contract = bridge.apply_confirmation(card, event)
    """

    def __init__(self) -> None:
        self._ledger = WeeklyLedger()

    def process_material(self, material: dict[str, Any]) -> DecisionCard | None:
        """
        Extract issues from material and evaluate via decision gate.

        Returns:
            DecisionCard(status="pending_confirmation") — all valid
            DecisionCard(status="incomplete") — missing fields
            None — fake closure detected
        """
        issues = extract_issues(material)
        if not issues:
            logger.warning("WeeklyFlowBridge: no issues extracted from material")
            return None
        card = gate_evaluate(issues)
        if card is None:
            logger.warning("WeeklyFlowBridge: fake closure detected, no contract possible")
        elif card.status == "incomplete":
            logger.info(
                "WeeklyFlowBridge: incomplete card issue_id=%s missing=%s",
                card.issue_id, card.missing_fields,
            )
        else:
            logger.info(
                "WeeklyFlowBridge: pending confirmation card issue_id=%s",
                card.issue_id,
            )
        return card

    def apply_confirmation(
        self,
        card: DecisionCard,
        event: ConfirmationEvent,
    ) -> ExecutionContract | None:
        """
        Apply a confirmation event to a DecisionCard.

        Returns ExecutionContract on confirmed, None on rejected/incomplete.
        Idempotent: repeated calls for same issue_id return same contract.
        """
        return self._ledger.process_confirmation(card, event)

    def apply_feishu_confirmation(
        self,
        card: DecisionCard,
        owner_id: str,
        reply_text: str,
        raw_payload: dict[str, Any] | None = None,
    ) -> ExecutionContract | None:
        """Parse a Feishu reply and apply it as a confirmation event."""
        event = parse_feishu_reply(
            issue_id=card.issue_id,
            owner_id=owner_id,
            reply_text=reply_text,
            raw_payload=raw_payload,
        )
        return self.apply_confirmation(card, event)

    def list_contracts(self) -> list[ExecutionContract]:
        return self._ledger.list_contracts()

    def list_follow_ups(self) -> list[dict]:
        return self._ledger.list_follow_ups()
