from __future__ import annotations
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from hermes_constants import get_hermes_home
from gateway.session_context import get_session_env, set_session_vars

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
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("pending_created")
        except Exception:
            pass
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
                if terminal_state == "knowledge_saved":
                    rec["status"] = "written"
                elif terminal_state in ("blocked", "no_action_with_reason"):
                    rec["status"] = terminal_state
                elif terminal_state == "pending_created":
                    rec["status"] = "pending"
                updated = True
        if updated:
            with open(path, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec) + "\n")
    except Exception as exc:
        logger.warning("mark_terminal failed (non-fatal): %s", exc)


def read_pending(capture_id: str, hermes_home: Path | None = None) -> dict | None:
    """Return one pending capture by id, or None when absent."""
    for rec in list_pending(hermes_home=hermes_home):
        if rec.get("capture_id") == capture_id:
            return rec
    return None


def _replay_write_knowledge(record: dict) -> dict:
    """Replay a pending knowledge record through the regular knowledge tool path."""
    structured = {}
    try:
        raw_structured = record.get("structured_candidate") or "{}"
        structured = json.loads(raw_structured) if isinstance(raw_structured, str) else raw_structured
    except Exception:
        structured = {}

    from tools.knowledge_tool import _knowledge_write

    previous_session = {
        "platform": get_session_env("HERMES_SESSION_PLATFORM", ""),
        "chat_id": get_session_env("HERMES_SESSION_CHAT_ID", ""),
        "chat_name": get_session_env("HERMES_SESSION_CHAT_NAME", ""),
        "thread_id": get_session_env("HERMES_SESSION_THREAD_ID", ""),
        "user_id": get_session_env("HERMES_SESSION_USER_ID", ""),
        "user_name": get_session_env("HERMES_SESSION_USER_NAME", ""),
        "session_key": get_session_env("HERMES_SESSION_KEY", ""),
    }
    replay_session = {
        **previous_session,
        "platform": record.get("platform") or previous_session["platform"],
        "user_id": record.get("user_id") or previous_session["user_id"],
    }
    set_session_vars(**replay_session)
    try:
        raw = _knowledge_write(
            title=record.get("title", ""),
            content=structured.get("content") or record.get("summary", ""),
            product_line_id=record.get("scope_id", ""),
            knowledge_type=structured.get("knowledge_type", "other"),
            source_uri=record.get("source_uri", ""),
            finance_flag=bool(structured.get("finance_flag", False)),
            sensitivity_level=structured.get("sensitivity_level", "internal"),
            confidence=structured.get("confidence") or record.get("confidence", "unverified"),
            doc_slug=structured.get("doc_slug", ""),
            task_id=record.get("session_id", ""),
        )
    finally:
        set_session_vars(**previous_session)
    try:
        return json.loads(raw)
    except Exception:
        return {"error": "write_failed", "reason": str(raw)}


def stats(hermes_home: Path | None = None) -> dict:
    """Return count statistics by status across all pending captures."""
    records = list_pending(hermes_home=hermes_home)
    by_status: dict[str, int] = {}
    for rec in records:
        s = rec.get("status", "pending")
        by_status[s] = by_status.get(s, 0) + 1
    return {"total": len(records), "by_status": by_status}


def migrate_to_staging(capture_id: str, hermes_home: Path | None = None) -> str:
    """Idempotent: promote a pending capture to staging(retry_write).

    Returns staging_id on success, "" if capture not found.
    Already-migrated captures return the same staging_id stored in their record.
    """
    rec = read_pending(capture_id, hermes_home=hermes_home)
    if rec is None:
        return ""
    existing_staging_id = rec.get("staging_id", "")
    if existing_staging_id:
        mark_terminal(capture_id, "migrated_to_staging", hermes_home=hermes_home)
        return existing_staging_id

    from agent.staging_store import write_staging
    staging_id = write_staging(
        event_id=capture_id,
        reason=rec.get("failure_reason") or "pending_capture migration",
        next_action="retry_write",
        source_uri=rec.get("source_uri", ""),
        raw_content=rec.get("title", ""),
        hermes_home=hermes_home,
    )
    base = hermes_home or get_hermes_home()
    path = base / "knowledge" / "pending_captures.jsonl"
    try:
        records = list_pending(hermes_home=hermes_home)
        for r in records:
            if r.get("capture_id") == capture_id:
                r["staging_id"] = staging_id
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
    except Exception as exc:
        logger.warning("migrate_to_staging write-back failed (non-fatal): %s", exc)
    mark_terminal(capture_id, "migrated_to_staging", hermes_home=hermes_home)
    return staging_id


def replay_pending(capture_id: str, hermes_home: Path | None = None) -> dict:
    """Replay one pending knowledge capture and update its terminal_state."""
    rec = read_pending(capture_id, hermes_home=hermes_home)
    if rec is None:
        return {"status": "not_found", "capture_id": capture_id}

    if rec.get("candidate_type") != "knowledge":
        mark_terminal(capture_id, "blocked", hermes_home=hermes_home)
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("replay_failed")
        except Exception:
            pass
        return {
            "status": "blocked",
            "capture_id": capture_id,
            "reason": "only knowledge captures can be replayed",
        }

    result = _replay_write_knowledge(rec)
    if isinstance(result, dict) and result.get("success"):
        mark_terminal(capture_id, "knowledge_saved", hermes_home=hermes_home)
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("replay_success")
        except Exception:
            pass
        return {
            "status": "replayed",
            "capture_id": capture_id,
            "result": result,
        }

    mark_terminal(capture_id, "blocked", hermes_home=hermes_home)
    try:
        from agent import sedimentation_metrics
        sedimentation_metrics.increment("replay_failed")
    except Exception:
        pass
    return {
        "status": "blocked",
        "capture_id": capture_id,
        "result": result,
    }
