"""
Persistent consensus ledger + follow-up store for the Weekly flow.

All writes go to:
  get_hermes_home() / "weekly" / "ledger.json"     ← confirmed ExecutionContracts
  get_hermes_home() / "weekly" / "follow_up.json"  ← incomplete/rejected records

Write strategy: atomic JSON write (write-then-rename) for crash safety.
Idempotent: repeated process_confirmation for same issue_id returns same contract.
Recoverable: new WeeklyLedger() loads existing ledger from disk automatically.
"""
from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

from .models import ConfirmationEvent, DecisionCard, ExecutionContract

logger = logging.getLogger(__name__)

_WEEKLY_DIR_NAME = "weekly"
_LEDGER_FILE = "ledger.json"
_FOLLOW_UP_FILE = "follow_up.json"


class WeeklyLedger:
    """
    Persistent consensus ledger for Weekly flow contracts.

    Thread-safety: single-process write-then-rename is atomic on POSIX.
    Idempotent: same issue_id → same contract, no duplication.
    """

    def __init__(self) -> None:
        self._dir = get_hermes_home() / _WEEKLY_DIR_NAME
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ledger_path = self._dir / _LEDGER_FILE
        self._follow_up_path = self._dir / _FOLLOW_UP_FILE
        # In-memory cache — loaded lazily
        self._contracts: dict[str, dict] = {}
        self._follow_ups: list[dict] = []
        self._loaded = False

    def process_confirmation(
        self,
        card: DecisionCard,
        event: ConfirmationEvent,
    ) -> ExecutionContract | None:
        """
        Process a confirmation event for a DecisionCard.

        - If already confirmed (idempotent): return existing contract.
        - If confirmed: create ExecutionContract, persist to ledger.json.
        - If rejected/incomplete: record in follow_up.json, return None.
        """
        self._ensure_loaded()

        # Idempotency: already confirmed → return existing
        if event.issue_id in self._contracts:
            existing = self._contracts[event.issue_id]
            return _dict_to_contract(existing)

        if event.decision == "confirmed":
            contract = _make_contract(card, event)
            entry = _contract_to_dict(contract)
            self._contracts[event.issue_id] = entry
            self._persist_ledger()
            logger.info("Weekly ledger: contract confirmed for issue_id=%s", event.issue_id)
            return contract

        # rejected or incomplete → follow_up
        follow_up_entry = {
            "issue_id": event.issue_id,
            "decision": event.decision,
            "owner_id": event.owner_id,
            "channel": event.channel,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "card_status": card.status,
            "missing_fields": list(card.missing_fields),
            "follow_up_items": list(card.follow_up),
        }
        self._follow_ups.append(follow_up_entry)
        self._persist_follow_up()
        logger.info(
            "Weekly ledger: issue_id=%s → %s, added to follow_up",
            event.issue_id, event.decision,
        )
        return None

    def list_contracts(self) -> list[ExecutionContract]:
        """Return all confirmed contracts (loads from disk)."""
        self._ensure_loaded()
        return [_dict_to_contract(v) for v in self._contracts.values()]

    def list_follow_ups(self) -> list[dict]:
        """Return all follow_up records."""
        self._ensure_loaded()
        return list(self._follow_ups)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._contracts = _load_json(self._ledger_path, default={})
        self._follow_ups = _load_json(self._follow_up_path, default=[])
        self._loaded = True

    def _persist_ledger(self) -> None:
        _atomic_write_json(self._ledger_path, self._contracts)

    def _persist_follow_up(self) -> None:
        _atomic_write_json(self._follow_up_path, self._follow_ups)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_contract(card: DecisionCard, event: ConfirmationEvent) -> ExecutionContract:
    now = datetime.now(timezone.utc).isoformat()
    hash_input = f"{card.issue_id}:{event.owner_id}:{event.received_at}"
    contract_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:24]
    return ExecutionContract(
        issue_id=event.issue_id,
        card_issue_id=card.issue_id,
        confirmed_by=event.owner_id,
        confirmed_at=now,
        confirmation_channel=event.channel,
        contract_hash=contract_hash,
    )


def _contract_to_dict(contract: ExecutionContract) -> dict:
    return {
        "issue_id": contract.issue_id,
        "card_issue_id": contract.card_issue_id,
        "confirmed_by": contract.confirmed_by,
        "confirmed_at": contract.confirmed_at,
        "confirmation_channel": contract.confirmation_channel,
        "contract_hash": contract.contract_hash,
        "status": contract.status,
    }


def _dict_to_contract(d: dict) -> ExecutionContract:
    return ExecutionContract(
        issue_id=d["issue_id"],
        card_issue_id=d["card_issue_id"],
        confirmed_by=d["confirmed_by"],
        confirmed_at=d["confirmed_at"],
        confirmation_channel=d["confirmation_channel"],
        contract_hash=d["contract_hash"],
        status=d.get("status", "active"),
    )


def _load_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("WeeklyLedger: failed to load %s, using default", path)
        return default


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
