from __future__ import annotations
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


@dataclass
class PendingCapture:
    capture_id: str
    title: str
    summary: str
    candidate_type: str        # "knowledge" | "memory" | "skill"
    scope_id: str
    source_uri: str
    confidence: str
    missing_fields: list[str] = field(default_factory=list)
    failure_reason: str = ""
    session_id: str = ""
    user_id: str = ""
    status: str = "pending"
    created_at: str = ""


def write_pending_capture(
    title: str,
    summary: str,
    candidate_type: str,
    scope_id: str,
    source_uri: str,
    confidence: str,
    missing_fields: list[str],
    failure_reason: str,
    session_id: str,
    user_id: str,
    hermes_home: Path | None = None,
) -> str:
    """Append a failed knowledge candidate to pending_captures.jsonl.

    Returns capture_id. Never raises — exceptions are logged as warnings.
    """
    capture_id = str(uuid.uuid4())
    try:
        base = hermes_home or get_hermes_home()
        path = base / "knowledge" / "pending_captures.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = PendingCapture(
            capture_id=capture_id,
            title=title,
            summary=summary,
            candidate_type=candidate_type,
            scope_id=scope_id,
            source_uri=source_uri,
            confidence=confidence,
            missing_fields=missing_fields,
            failure_reason=failure_reason,
            session_id=session_id,
            user_id=user_id,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")
    except Exception as exc:
        logger.warning("write_pending_capture failed (non-fatal): %s", exc)
    return capture_id
