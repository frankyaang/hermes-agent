from __future__ import annotations
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from agent.knowledge_models import KnowledgeAuditEvent, TransactionState
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


@dataclass
class TransactionAuditEvent:
    """Lifecycle event for a KnowledgeWriteTransaction.

    Covers the full lifecycle from candidate_created to query_verified.
    Stored in the same audit directory as KnowledgeAuditEvent for unified
    querying. Identified by event_type (not the legacy `action` field).
    """
    event_id: str
    timestamp: str
    event_type: str            # TransactionState value or "query_verified"
    transaction_id: str
    original_user_id: str
    resolved_user_id: str = ""
    platform: str = ""
    source_session_id: str = ""
    root_session_id: str = ""
    asset_type: str = ""
    target_scope_id: str = ""
    provider_name: str = ""
    pending_capture_id: str = ""
    failure_category: str = ""
    failure_reason: str = ""
    detail: str = ""           # free-form context for the event


class KnowledgeAuditLogger:
    def __init__(self, audit_dir: Path | None = None):
        self._base = audit_dir or (get_hermes_home() / "knowledge" / "audit")

    def log(self, event: KnowledgeAuditEvent) -> None:
        try:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            path = self._base / month / "audit.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps({
                    "event_id": event.event_id,
                    "timestamp": event.timestamp,
                    "user_id": event.user_id,
                    "action": event.action,
                    "product_line_id": event.product_line_id,
                    "finance_flag": event.finance_flag,
                    "granted": event.granted,
                    "deny_reason": event.deny_reason,
                    "knowledge_slugs": event.knowledge_slugs,
                    "source_uris": event.source_uris,
                    "query_text": event.query_text,
                }) + "\n")
        except Exception as exc:
            logger.error("audit log write failed: %s", exc)

    def log_transaction_event(self, event: TransactionAuditEvent) -> None:
        """Write a transaction lifecycle event to the audit log.

        Uses a separate file (tx_audit.jsonl) to keep legacy query/write events
        and new transaction events independently queryable.
        """
        try:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            path = self._base / month / "tx_audit.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("transaction audit log write failed: %s", exc)

    def make_event(self, **kwargs) -> KnowledgeAuditEvent:
        return KnowledgeAuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )

    def make_tx_event(
        self,
        event_type: str,
        transaction_id: str,
        original_user_id: str,
        **kwargs,
    ) -> TransactionAuditEvent:
        return TransactionAuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            transaction_id=transaction_id,
            original_user_id=original_user_id,
            **kwargs,
        )

    def emit(
        self,
        event_type: str,
        transaction_id: str,
        original_user_id: str,
        **kwargs,
    ) -> None:
        """Create and immediately write a transaction lifecycle event."""
        ev = self.make_tx_event(
            event_type=event_type,
            transaction_id=transaction_id,
            original_user_id=original_user_id,
            **kwargs,
        )
        self.log_transaction_event(ev)

    def read_tx_events(
        self,
        month: str | None = None,
        transaction_id: str | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Read transaction audit events, optionally filtered by month and transaction_id."""
        month = month or datetime.now(timezone.utc).strftime("%Y-%m")
        path = self._base / month / "tx_audit.jsonl"
        if not path.exists():
            return []
        results = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if transaction_id and record.get("transaction_id") != transaction_id:
                    continue
                results.append(record)
                if len(results) >= limit:
                    break
        except Exception as exc:
            logger.warning("read_tx_events failed: %s", exc)
        return results
