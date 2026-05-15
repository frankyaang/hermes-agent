from __future__ import annotations
import getpass
import json
import logging
import os
import re
from datetime import datetime, timezone
from tools.registry import registry
from gateway.session_context import get_session_env
from agent.knowledge_alias import resolve_product_line_alias
from agent.pending_capture import (
    list_pending,
    mark_terminal,
    read_pending,
    replay_pending,
    write_pending_capture,
)

logger = logging.getLogger(__name__)

# session_id -> KnowledgeManager; populated lazily on first tool call per session.
_MANAGER_CACHE: dict[str, object] = {}


def _candidate_user_ids(raw_user_id: str, platform: str) -> list[str]:
    """Return registry user_id candidates for the current session identity."""
    raw = (raw_user_id or "").strip()
    platform_key = (platform or "").strip().lower()
    candidates: list[str] = []
    if raw:
        if platform_key and ":" not in raw:
            candidates.append(f"{platform_key}:{raw}")
        candidates.append(raw)
    elif not platform_key or platform_key == "cli":
        profile = os.getenv("HERMES_PROFILE", "default")
        candidates.append(f"cli:{getpass.getuser()}:{profile}")

    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _get_manager(session_id: str):
    """Return the KnowledgeManager for this session, or None on any error (fail closed)."""
    user_id = get_session_env("HERMES_SESSION_USER_ID", "")
    platform = get_session_env("HERMES_SESSION_PLATFORM", "")
    candidates = _candidate_user_ids(user_id, platform)
    key = f"{session_id or 'cli_default'}:{'|'.join(candidates)}"
    if key in _MANAGER_CACHE:
        return _MANAGER_CACHE[key]

    from agent.knowledge_user_registry import KnowledgeUserRegistry
    from agent.knowledge_manager import KnowledgeManager
    from agent.knowledge_acl import KnowledgeACLGuard
    from agent.knowledge_audit import KnowledgeAuditLogger
    from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider

    reg = KnowledgeUserRegistry()
    reg.load()
    ctx = None
    matched_user_id = ""
    for candidate in candidates:
        ctx = reg.get_user(candidate)
        if ctx is not None:
            matched_user_id = candidate
            break
    if ctx is None:
        logger.warning("knowledge: user_id candidates=%r not in registry — access denied", candidates)
        return None

    errors = reg.validate_config(ctx)
    if errors:
        logger.error("knowledge: config errors for %r: %s", matched_user_id, errors)
        return None

    mgr = KnowledgeManager(
        ctx=ctx,
        provider=GBrainCLIKnowledgeProvider(),
        acl=KnowledgeACLGuard(),
        audit=KnowledgeAuditLogger(),
    )
    _MANAGER_CACHE[key] = mgr
    return mgr


def _knowledge_query(query: str, product_line_id: str, finance: bool, task_id: str) -> str:
    mgr = _get_manager(task_id)
    if mgr is None:
        return json.dumps({"error": "access_denied", "reason": "user_not_registered_or_config_error"})

    if not product_line_id:
        product_line_id = mgr._ctx.default_product_line_id
    if not product_line_id:
        return json.dumps({"error": "no_product_line", "reason": "specify product_line_id or set default"})

    results = mgr.query(query, product_line_id, finance_ok=finance)
    return json.dumps({
        "count": len(results),
        "product_line_id": product_line_id,
        "finance_mode": finance,
        "results": [
            {
                "slug": d.slug,
                "title": d.title,
                "snippet": d.snippet or d.content[:300],
                "source_uri": d.source_uri,
                "confidence": d.confidence,
                "knowledge_type": d.knowledge_type,
            }
            for d in results
        ],
    })


def _next_action_hint(reason: str, scope_id: str, session_id: str) -> str:
    if reason == "product_line_not_authorized":
        return (
            f"Add {scope_id} to your product_line_ids in ~/.hermes/knowledge/users.yaml, "
            "or use ecovacs_company for company-level facts"
        )
    if reason == "source_uri_required":
        return f"Provide source_uri (e.g. feishu://doc/xxx or hermes://session/{session_id})"
    if reason == "finance_write_not_authorized":
        return f"Add {scope_id} to finance_product_line_ids in users.yaml"
    return "Check pending captures at ~/.hermes/knowledge/pending_captures.jsonl"


def _structured_write_candidate(
    content: str,
    knowledge_type: str,
    finance_flag: bool,
    sensitivity_level: str,
    confidence: str,
    doc_slug: str,
) -> dict:
    return {
        "content": content,
        "knowledge_type": knowledge_type,
        "finance_flag": finance_flag,
        "sensitivity_level": sensitivity_level,
        "confidence": confidence,
        "doc_slug": doc_slug,
    }


def _knowledge_write(
    title: str,
    content: str,
    product_line_id: str,
    knowledge_type: str,
    source_uri: str,
    finance_flag: bool,
    sensitivity_level: str,
    confidence: str,
    doc_slug: str,
    task_id: str,
) -> str:
    from agent.knowledge_manager import PermissionDenied
    from agent.knowledge_models import KnowledgeDoc

    mgr = _get_manager(task_id)
    if mgr is None:
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("knowledge_write_failed")
        except Exception:
            pass
        return json.dumps({"error": "access_denied", "reason": "user_not_registered_or_config_error"})

    # Normalize alias before any ACL check
    product_line_id = resolve_product_line_alias(product_line_id)

    if not product_line_id:
        product_line_id = mgr._ctx.default_product_line_id
    if not product_line_id:
        capture_id = write_pending_capture(
            title=title, summary=content[:500], candidate_type="knowledge",
            scope_id="", source_uri=source_uri, confidence=confidence,
            missing_fields=["product_line_id"], failure_reason="no_product_line",
            session_id=task_id, user_id=mgr._ctx.user_id,
            platform=get_session_env("HERMES_SESSION_PLATFORM", ""),
            structured_candidate=_structured_write_candidate(
                content, knowledge_type, finance_flag, sensitivity_level, confidence, doc_slug
            ),
        )
        mark_terminal(capture_id, "pending_created")
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("knowledge_write_failed")
        except Exception:
            pass
        return json.dumps({
            "error": "no_product_line",
            "reason": "specify product_line_id or set default",
            "pending_capture_id": capture_id,
            "next_action": "Check pending captures at ~/.hermes/knowledge/pending_captures.jsonl",
        })

    if not doc_slug:
        doc_slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:50].strip("-")

    now = datetime.now(timezone.utc).isoformat()
    doc = KnowledgeDoc(
        slug=doc_slug, title=title, content=content,
        product_line_id=product_line_id, finance_flag=finance_flag,
        source_uri=source_uri, knowledge_type=knowledge_type,
        sensitivity_level=sensitivity_level, confidence=confidence,
        owner=mgr._ctx.user_id, created_at=now, updated_at=now,
        updated_by=mgr._ctx.user_id,
    )
    try:
        slug = mgr.write(doc)
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("knowledge_write_success")
        except Exception:
            pass
        return json.dumps({"success": True, "slug": slug, "product_line_id": product_line_id})
    except PermissionDenied as exc:
        reason = str(exc)
        capture_id = write_pending_capture(
            title=title, summary=content[:500], candidate_type="knowledge",
            scope_id=product_line_id, source_uri=source_uri, confidence=confidence,
            missing_fields=[], failure_reason=reason,
            session_id=task_id, user_id=mgr._ctx.user_id,
            platform=get_session_env("HERMES_SESSION_PLATFORM", ""),
            structured_candidate=_structured_write_candidate(
                content, knowledge_type, finance_flag, sensitivity_level, confidence, doc_slug
            ),
        )
        mark_terminal(capture_id, "pending_created")
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("knowledge_write_failed")
        except Exception:
            pass
        return json.dumps({
            "error": "permission_denied",
            "reason": reason,
            "pending_capture_id": capture_id,
            "next_action": _next_action_hint(reason, product_line_id, task_id),
        })
    except Exception as exc:
        logger.error("knowledge write failed: %s", exc)
        capture_id = write_pending_capture(
            title=title, summary=content[:500], candidate_type="knowledge",
            scope_id=product_line_id, source_uri=source_uri, confidence=confidence,
            missing_fields=[], failure_reason=f"write_failed:{type(exc).__name__}",
            session_id=task_id, user_id=mgr._ctx.user_id,
            platform=get_session_env("HERMES_SESSION_PLATFORM", ""),
            structured_candidate=_structured_write_candidate(
                content, knowledge_type, finance_flag, sensitivity_level, confidence, doc_slug
            ),
        )
        mark_terminal(capture_id, "pending_created")
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("knowledge_write_failed")
        except Exception:
            pass
        return json.dumps({
            "error": "write_failed",
            "reason": str(exc),
            "pending_capture_id": capture_id,
            "next_action": "Check pending captures at ~/.hermes/knowledge/pending_captures.jsonl",
        })


def _pending_visible_to_manager(record: dict, mgr) -> bool:
    ctx = getattr(mgr, "_ctx", None)
    if ctx is None:
        return False
    if getattr(ctx, "is_admin", False):
        return True
    return (record.get("user_id") or "") == getattr(ctx, "user_id", "")


def _compact_pending_record(record: dict) -> dict:
    return {
        "capture_id": record.get("capture_id", ""),
        "title": record.get("title", ""),
        "candidate_type": record.get("candidate_type", ""),
        "scope_id": record.get("scope_id", ""),
        "source_uri": record.get("source_uri", ""),
        "confidence": record.get("confidence", ""),
        "failure_reason": record.get("failure_reason", ""),
        "missing_fields": record.get("missing_fields", []),
        "platform": record.get("platform", ""),
        "user_id": record.get("user_id", ""),
        "suggested_next_action": record.get("suggested_next_action", ""),
        "terminal_state": record.get("terminal_state", ""),
        "status": record.get("status", ""),
        "created_at": record.get("created_at", ""),
    }


def _knowledge_pending(
    action: str,
    capture_id: str,
    status: str,
    limit: int,
    task_id: str,
) -> str:
    """Operate on knowledge pending captures through ACL-aware tool access."""
    mgr = _get_manager(task_id)
    if mgr is None:
        return json.dumps({"error": "access_denied", "reason": "user_not_registered_or_config_error"})

    action = (action or "list").strip().lower()
    status_filter = (status or "").strip()
    safe_limit = max(1, min(int(limit or 20), 100))

    if action == "list":
        records = [
            _compact_pending_record(record)
            for record in list_pending()
            if _pending_visible_to_manager(record, mgr)
            and (not status_filter or record.get("status") == status_filter)
        ]
        return json.dumps({
            "count": len(records[:safe_limit]),
            "total_visible": len(records),
            "records": records[:safe_limit],
        })

    if action in {"read", "replay"} and not capture_id:
        return json.dumps({"error": "missing_capture_id", "reason": "capture_id is required"})

    record = read_pending(capture_id)
    if record is None:
        return json.dumps({"status": "not_found", "capture_id": capture_id})
    if not _pending_visible_to_manager(record, mgr):
        return json.dumps({"error": "access_denied", "reason": "pending_capture_not_visible"})

    if action == "read":
        visible = _compact_pending_record(record)
        visible["summary"] = record.get("summary", "")
        visible["structured_candidate"] = record.get("structured_candidate", "")
        return json.dumps({"record": visible})

    if action == "replay":
        return json.dumps(replay_pending(capture_id))

    return json.dumps({
        "error": "invalid_action",
        "reason": "action must be one of: list, read, replay",
    })


registry.register(
    name="knowledge_pending",
    toolset="knowledge",
    schema={
        "name": "knowledge_pending",
        "description": (
            "List, read, or replay pending business knowledge captures. "
            "Replay uses the original captured session identity and still enforces ACL."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "read", "replay"],
                    "description": "Operation to run. Default: list.",
                },
                "capture_id": {
                    "type": "string",
                    "description": "Required for read/replay.",
                },
                "status": {
                    "type": "string",
                    "description": "Optional status filter for list (e.g. pending, blocked, written).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum records to return for list. Default 20, max 100.",
                },
            },
        },
    },
    handler=lambda args, **kw: _knowledge_pending(
        action=args.get("action", "list"),
        capture_id=args.get("capture_id", ""),
        status=args.get("status", ""),
        limit=int(args.get("limit", 20) or 20),
        task_id=kw.get("task_id", ""),
    ),
)

registry.register(
    name="knowledge_query",
    toolset="knowledge",
    schema={
        "name": "knowledge_query",
        "description": (
            "Query the business knowledge base. "
            "Returns docs from the user's authorized product line only. "
            "Set finance=true only for financial data (requires finance permission). "
            "Never returns knowledge from unauthorized product lines."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "product_line_id": {
                    "type": "string",
                    "description": "Product line to search (e.g. 'cleaning_robot'). Defaults to user's default product line.",
                },
                "finance": {
                    "type": "boolean",
                    "description": "Set true to include financial knowledge (requires finance permission). Default false.",
                },
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: _knowledge_query(
        query=args["query"],
        product_line_id=args.get("product_line_id", ""),
        finance=bool(args.get("finance", False)),
        task_id=kw.get("task_id", ""),
    ),
)

registry.register(
    name="knowledge_write",
    toolset="knowledge",
    schema={
        "name": "knowledge_write",
        "description": (
            "Write a new knowledge entry to the business knowledge base. "
            "Requires business role or higher. source_uri is mandatory — no source, no write."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "product_line_id": {"type": "string"},
                "knowledge_type": {
                    "type": "string",
                    "enum": [
                        "product_spec", "org_info", "project_history",
                        "customer_feedback", "meeting_conclusion",
                        "financial_report", "financial_kpi", "financial_forecast",
                        "market_data", "compliance", "other",
                    ],
                },
                "source_uri": {
                    "type": "string",
                    "description": "Required: source document URI (e.g. feishu://doc/xxx, https://..., manual://)",
                },
                "finance_flag": {
                    "type": "boolean",
                    "description": "True if this is financial data. Default false.",
                },
                "sensitivity_level": {
                    "type": "string",
                    "enum": ["public", "internal", "confidential", "secret"],
                    "description": "Default: internal",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["draft", "unverified", "verified", "deprecated"],
                    "description": "Default: unverified",
                },
                "doc_slug": {
                    "type": "string",
                    "description": "Optional slug (auto-generated from title if omitted)",
                },
            },
            "required": ["title", "content", "product_line_id", "knowledge_type", "source_uri"],
        },
    },
    handler=lambda args, **kw: _knowledge_write(
        title=args["title"],
        content=args["content"],
        product_line_id=args["product_line_id"],
        knowledge_type=args["knowledge_type"],
        source_uri=args["source_uri"],
        finance_flag=bool(args.get("finance_flag", False)),
        sensitivity_level=args.get("sensitivity_level", "internal"),
        confidence=args.get("confidence", "unverified"),
        doc_slug=args.get("doc_slug", ""),
        task_id=kw.get("task_id", ""),
    ),
)
