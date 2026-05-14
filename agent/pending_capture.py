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
    platform: str = ""
    suggested_next_action: str = ""
    structured_candidate: str = ""
    terminal_state: str = ""
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
    platform: str = "",
    suggested_next_action: str = "",
    structured_candidate: dict | None = None,
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
            platform=platform,
            suggested_next_action=suggested_next_action,
            structured_candidate=json.dumps(structured_candidate or {}, ensure_ascii=False),
            terminal_state="",
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")
    except Exception as exc:
        logger.warning("write_pending_capture failed (non-fatal): %s", exc)
    return capture_id


def list_pending(hermes_home: Path | None = None) -> list[dict]:
    """Return all records from pending_captures.jsonl as dicts."""
    base = hermes_home or get_hermes_home()
    path = base / "knowledge" / "pending_captures.jsonl"
    if not path.exists():
        return []
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    except Exception as exc:
        logger.warning("list_pending failed: %s", exc)
    return records


def mark_terminal(
    capture_id: str,
    terminal_state: str,
    hermes_home: Path | None = None,
) -> None:
    """Update terminal_state of a pending capture in-place (rewrites file)."""
    base = hermes_home or get_hermes_home()
    path = base / "knowledge" / "pending_captures.jsonl"
    if not path.exists():
        return
    try:
        records = list_pending(hermes_home=hermes_home)
        updated = False
        for rec in records:
            if rec.get("capture_id") == capture_id:
                rec["terminal_state"] = terminal_state
                updated = True
        if updated:
            with open(path, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec) + "\n")
    except Exception as exc:
        logger.warning("mark_terminal failed (non-fatal): %s", exc)
