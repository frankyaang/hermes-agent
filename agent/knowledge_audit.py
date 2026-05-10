from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from agent.knowledge_models import KnowledgeAuditEvent
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


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

    def make_event(self, **kwargs) -> KnowledgeAuditEvent:
        return KnowledgeAuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )
