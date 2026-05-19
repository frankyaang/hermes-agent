from __future__ import annotations
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from hermes_constants import get_hermes_home
from gateway.session_context import get_session_env, set_session_vars
from agent.knowledge_models import PendingDisposition

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
    # Extended transaction fields (optional for backward compat)
    transaction_id: str = ""
    idempotency_key: str = ""
    original_user_id: str = ""
    root_session_id: str = ""
    parent_session_id: str = ""
    asset_type: str = ""
    failure_category: str = ""


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


def write_pending_capture_tx(
    tx,
    content: str,
    doc_slug: str,
    knowledge_type: str,
    finance_flag: bool,
    sensitivity_level: str,
    hermes_home: Path | None = None,
) -> str:
    """Write a pending capture from a KnowledgeWriteTransaction.

    Preserves the full transaction context so replay can use the original
    identity, source, and scope without re-deriving them from the current
    session.

    Returns capture_id. Never raises.
    """
    structured = {
        "content": content,
        "knowledge_type": knowledge_type,
        "finance_flag": finance_flag,
        "sensitivity_level": sensitivity_level,
        "confidence": tx.confidence,
        "doc_slug": doc_slug,
    }
    capture_id = str(uuid.uuid4())
    try:
        base = hermes_home or get_hermes_home()
        path = base / "knowledge" / "pending_captures.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = PendingCapture(
            capture_id=capture_id,
            title=tx.title,
            summary=tx.content_summary,
            candidate_type=tx.candidate_type or "knowledge",
            scope_id=tx.target_scope_id,
            source_uri=tx.source_uri,
            confidence=tx.confidence,
            missing_fields=[],
            failure_reason=tx.failure_category or tx.failure_reason,
            session_id=tx.source_session_id,
            user_id=tx.original_user_id,  # always original, never CLI fallback
            platform=tx.platform,
            suggested_next_action="",
            structured_candidate=json.dumps(structured, ensure_ascii=False),
            terminal_state="pending_created",
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            transaction_id=tx.transaction_id,
            idempotency_key=tx.idempotency_key,
            original_user_id=tx.original_user_id,
            root_session_id=tx.root_session_id,
            parent_session_id=tx.parent_session_id,
            asset_type=tx.asset_type,
            failure_category=tx.failure_category,
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("pending_created")
        except Exception:
            pass
    except Exception as exc:
        logger.warning("write_pending_capture_tx failed (non-fatal): %s", exc)
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


def _resolve_original_user_id(record: dict) -> str:
    """Return the original_user_id from a pending record.

    Preference order:
    1. ``original_user_id`` (set by write_pending_capture_tx — most reliable)
    2. ``user_id`` when it is a platform identity (feishu:, telegram:, etc.)
    3. Raise ValueError if only a CLI fallback is available.
    """
    original = (record.get("original_user_id") or "").strip()
    if original:
        return original
    user_id = (record.get("user_id") or "").strip()
    if user_id and not user_id.startswith("cli:"):
        return user_id
    raise ValueError(
        f"pending capture {record.get('capture_id')} has no resolvable original_user_id "
        f"(user_id={user_id!r}) — replay blocked to prevent identity drift"
    )


def _replay_write_knowledge(record: dict) -> dict:
    """Replay a pending knowledge record through the regular knowledge tool path.

    Always uses the original_user_id from the record — never the current
    session's CLI user. Raises ValueError if identity cannot be resolved.
    """
    structured = {}
    try:
        raw_structured = record.get("structured_candidate") or "{}"
        structured = json.loads(raw_structured) if isinstance(raw_structured, str) else raw_structured
    except Exception:
        structured = {}

    # Resolve original identity — fail if only CLI fallback is available.
    original_user_id = _resolve_original_user_id(record)

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
    # Set the original platform identity, not the current CLI user.
    replay_session = {
        **previous_session,
        "platform": record.get("platform") or previous_session["platform"],
        "user_id": original_user_id,
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


def replay_pending(
    capture_id: str,
    hermes_home: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Replay one pending knowledge capture and update its terminal_state.

    Args:
        capture_id: the capture_id to replay
        hermes_home: optional override for HERMES_HOME
        dry_run: when True, resolve identity and validate but do NOT write

    Returns:
        dict with ``status``, ``capture_id``, and either ``result`` or ``reason``.
    """
    rec = read_pending(capture_id, hermes_home=hermes_home)
    if rec is None:
        return {"status": "not_found", "capture_id": capture_id}

    if rec.get("candidate_type") != "knowledge":
        mark_terminal(capture_id, "blocked", hermes_home=hermes_home)
        return {
            "status": "blocked",
            "capture_id": capture_id,
            "reason": "only knowledge captures can be replayed",
        }

    # Validate identity before attempting write.
    try:
        original_user_id = _resolve_original_user_id(rec)
    except ValueError as exc:
        mark_terminal(capture_id, "blocked", hermes_home=hermes_home)
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("replay_failed")
        except Exception:
            pass
        return {
            "status": "blocked_identity",
            "capture_id": capture_id,
            "reason": str(exc),
        }

    if dry_run:
        return {
            "status": "dry_run_ok",
            "capture_id": capture_id,
            "original_user_id": original_user_id,
            "scope_id": rec.get("scope_id"),
            "source_uri": rec.get("source_uri"),
        }

    result = _replay_write_knowledge(rec)
    if isinstance(result, dict) and result.get("success"):
        mark_terminal(capture_id, "knowledge_saved", hermes_home=hermes_home)
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("replay_success")
        except Exception:
            pass
        # Attempt query verification (best-effort; does not block on failure)
        verified = _try_query_verify(rec)
        if verified:
            mark_terminal(capture_id, "query_verified", hermes_home=hermes_home)
            try:
                sedimentation_metrics.increment("query_verified")
            except Exception:
                pass
        return {
            "status": "replayed",
            "capture_id": capture_id,
            "result": result,
            "query_verified": verified,
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


def _try_query_verify(rec: dict) -> bool:
    """Attempt to query the knowledge base to verify the replay write succeeded.

    Returns True if the slug is found, False on any failure (non-blocking).
    """
    try:
        structured = {}
        raw = rec.get("structured_candidate") or "{}"
        structured = json.loads(raw) if isinstance(raw, str) else raw
        doc_slug = structured.get("doc_slug") or ""
        scope_id = rec.get("scope_id", "")
        if not doc_slug or not scope_id:
            return False

        from tools.knowledge_tool import _knowledge_query
        raw_result = _knowledge_query(
            query=rec.get("title", ""),
            product_line_id=scope_id,
            finance=bool(structured.get("finance_flag", False)),
            task_id=rec.get("session_id", ""),
        )
        result = json.loads(raw_result)
        return bool(result.get("count", 0) > 0)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pending Reconciliation — dry-run analysis, no production writes
# ---------------------------------------------------------------------------

# CLI identity prefixes that indicate a drifted background review
_CLI_IDENTITY_PREFIXES = ("cli:",)


def _classify_pending_disposition(record: dict) -> dict:
    """Classify a single pending capture and return its disposition.

    Returns a dict with:
    - ``capture_id``
    - ``disposition``: a ``PendingDisposition`` constant
    - ``rationale``: human-readable explanation
    - ``original_user_id``: the identity that should be used for replay
    - ``retryable``: bool

    This is pure analysis — no files are read or written beyond the record dict.
    """
    capture_id = record.get("capture_id", "unknown")
    user_id = (record.get("user_id") or "").strip()
    original_user_id = (record.get("original_user_id") or user_id).strip()
    failure_reason = record.get("failure_reason", "")
    missing_fields = record.get("missing_fields") or []
    candidate_type = record.get("candidate_type", "")
    scope_id = record.get("scope_id", "")
    source_uri = record.get("source_uri", "")
    transaction_id = record.get("transaction_id", "")
    idempotency_key = record.get("idempotency_key", "")

    # — Identity drift —
    if not original_user_id:
        return {
            "capture_id": capture_id,
            "disposition": PendingDisposition.BLOCKED_IDENTITY,
            "rationale": "original_user_id is missing — cannot replay without identity",
            "original_user_id": "",
            "retryable": False,
        }
    for prefix in _CLI_IDENTITY_PREFIXES:
        if original_user_id.startswith(prefix):
            return {
                "capture_id": capture_id,
                "disposition": PendingDisposition.BLOCKED_IDENTITY,
                "rationale": (
                    f"user_id={original_user_id!r} is a CLI fallback identity — "
                    "background review identity drift; needs the original platform user"
                ),
                "original_user_id": original_user_id,
                "retryable": False,
            }

    # — Missing transaction semantics (no idempotency_key or root_session_id) —
    if not transaction_id and not idempotency_key:
        if not scope_id or not source_uri:
            return {
                "capture_id": capture_id,
                "disposition": PendingDisposition.NEEDS_HUMAN_REVIEW,
                "rationale": (
                    "missing transaction_id, idempotency_key, scope_id, or source_uri — "
                    "cannot safely replay without transaction semantics"
                ),
                "original_user_id": original_user_id,
                "retryable": False,
            }

    # — ACL / permission failures —
    if "not_authorized" in failure_reason or "permission_denied" in failure_reason:
        return {
            "capture_id": capture_id,
            "disposition": PendingDisposition.BLOCKED_PERMISSION,
            "rationale": f"ACL denied: {failure_reason}",
            "original_user_id": original_user_id,
            "retryable": False,
        }

    # — Missing required fields —
    if missing_fields:
        return {
            "capture_id": capture_id,
            "disposition": PendingDisposition.NEEDS_HUMAN_REVIEW,
            "rationale": f"missing required fields: {missing_fields}",
            "original_user_id": original_user_id,
            "retryable": False,
        }

    # — Provider unavailable (FileNotFoundError / executable_not_found) —
    if "FileNotFoundError" in failure_reason or "executable_not_found" in failure_reason or "provider_unavailable" in failure_reason:
        return {
            "capture_id": capture_id,
            "disposition": PendingDisposition.RETRYABLE_PROVIDER,
            "rationale": (
                f"provider unavailable ({failure_reason}) — "
                "will succeed once gbrain CLI is installed"
            ),
            "original_user_id": original_user_id,
            "retryable": True,
        }

    # — Generic write failure — optimistically retryable
    if "write_failed" in failure_reason or "provider_error" in failure_reason:
        return {
            "capture_id": capture_id,
            "disposition": PendingDisposition.RETRYABLE_PROVIDER,
            "rationale": f"provider write failed ({failure_reason}) — may be retryable",
            "original_user_id": original_user_id,
            "retryable": True,
        }

    # — Default: attempt replay —
    return {
        "capture_id": capture_id,
        "disposition": PendingDisposition.READY_TO_REPLAY,
        "rationale": "no known blocker — ready to replay",
        "original_user_id": original_user_id,
        "retryable": True,
    }


def dry_run_reconcile(hermes_home: Path | None = None) -> list[dict]:
    """Classify all pending captures for reconciliation (dry-run, read-only).

    Returns a list of disposition dicts (one per pending capture). Does NOT
    write to pending_captures.jsonl or any other file.

    Use this to understand which pending captures can be replayed, which are
    blocked by identity drift, which need human review, etc.
    """
    records = list_pending(hermes_home=hermes_home)
    return [_classify_pending_disposition(rec) for rec in records]
