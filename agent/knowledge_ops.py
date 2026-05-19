"""KnowledgeOps Orchestrator.

Unified lifecycle manager for all knowledge write operations. The model may
propose a write intent, but every write must flow through this orchestrator.

Lifecycle:
  candidate_created → classified → identity_resolved/identity_blocked
      → acl_granted/acl_denied → provider_started → provider_succeeded/provider_failed
      → [pending_created] → [replay_started → replay_succeeded/replay_failed]
      → [query_verified]

No knowledge write path is allowed to bypass this orchestrator.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.knowledge_audit import KnowledgeAuditLogger
from agent.knowledge_models import (
    AssetType,
    KnowledgeDoc,
    KnowledgeUserContext,
    KnowledgeWriteTransaction,
    PendingDisposition,
    ProviderError,
    TransactionState,
)
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


def _make_idempotency_key(source_uri: str, title: str, product_line_id: str) -> str:
    raw = f"{source_uri}|{title}|{product_line_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class IdentityError(Exception):
    """Raised when original_user_id is absent or has drifted to a fallback identity."""


class KnowledgeOpsOrchestrator:
    """Manages the full lifecycle of a knowledge write transaction.

    Callers obtain an orchestrator from ``KnowledgeOpsOrchestrator.for_session()``
    and call ``write()`` with the write intent. The orchestrator handles identity
    resolution, ACL, provider health check, write, pending creation, and audit.

    All state is recorded in ``KnowledgeWriteTransaction`` and audit events are
    emitted at each transition.
    """

    # Identity patterns that indicate a fallback / drifted identity.
    _FALLBACK_IDENTITY_PREFIXES = ("cli:", "default")

    def __init__(
        self,
        ctx: KnowledgeUserContext,
        provider,
        acl,
        audit: KnowledgeAuditLogger | None = None,
        hermes_home: Path | None = None,
    ):
        self._ctx = ctx
        self._provider = provider
        self._acl = acl
        self._audit = audit or KnowledgeAuditLogger()
        self._hermes_home = hermes_home or get_hermes_home()

    @classmethod
    def for_session(
        cls,
        session_id: str,
        user_id: str,
        platform: str,
        hermes_home: Path | None = None,
    ) -> "KnowledgeOpsOrchestrator | None":
        """Build an orchestrator for a specific session, loading user registry.

        Returns None if the user is not registered (access denied, fail-closed).
        """
        from agent.knowledge_acl import KnowledgeACLGuard
        from agent.knowledge_user_registry import KnowledgeUserRegistry
        from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider

        reg = KnowledgeUserRegistry()
        reg.load()
        ctx = reg.get_user(user_id)
        if ctx is None:
            logger.warning("KnowledgeOps: user_id=%r not in registry", user_id)
            return None
        return cls(
            ctx=ctx,
            provider=GBrainCLIKnowledgeProvider(),
            acl=KnowledgeACLGuard(),
            audit=KnowledgeAuditLogger(
                audit_dir=(hermes_home or get_hermes_home()) / "knowledge" / "audit"
            ),
            hermes_home=hermes_home,
        )

    def _new_tx(
        self,
        original_user_id: str,
        source_session_id: str,
        root_session_id: str,
        parent_session_id: str,
        platform: str,
        source_uri: str,
        title: str,
        content: str,
        product_line_id: str,
        asset_type: str,
        candidate_type: str,
        knowledge_type: str,
        finance_flag: bool,
        sensitivity_level: str,
        confidence: str,
        doc_slug: str,
        chat_id: str = "",
        chat_name: str = "",
        chat_type: str = "",
        evidence_snippet: str = "",
    ) -> KnowledgeWriteTransaction:
        now = datetime.now(timezone.utc).isoformat()
        return KnowledgeWriteTransaction(
            transaction_id=str(uuid.uuid4()),
            idempotency_key=_make_idempotency_key(source_uri, title, product_line_id),
            original_user_id=original_user_id,
            resolved_user_id=self._ctx.user_id,
            platform=platform,
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type=chat_type,
            source_session_id=source_session_id,
            root_session_id=root_session_id or source_session_id,
            parent_session_id=parent_session_id,
            source_uri=source_uri,
            evidence_snippet=evidence_snippet,
            asset_type=asset_type,
            candidate_type=candidate_type,
            target_scope_type="product_line",
            target_scope_id=product_line_id,
            title=title,
            content_summary=content[:500],
            knowledge_type=knowledge_type,
            finance_flag=finance_flag,
            sensitivity_level=sensitivity_level,
            confidence=confidence,
            doc_slug=doc_slug,
            provider_name=self._provider.name,
            current_state=TransactionState.CANDIDATE_CREATED,
            created_at=now,
            updated_at=now,
        )

    def _assert_identity_not_drifted(self, original_user_id: str) -> None:
        """Raise IdentityError if original_user_id is empty or is a CLI fallback."""
        if not original_user_id:
            raise IdentityError("original_user_id is required — blocked_identity")
        for prefix in self._FALLBACK_IDENTITY_PREFIXES:
            if original_user_id.startswith(prefix):
                raise IdentityError(
                    f"original_user_id={original_user_id!r} is a CLI fallback identity; "
                    "background review must inherit the parent session's platform user_id"
                )

    def write(
        self,
        original_user_id: str,
        source_session_id: str,
        root_session_id: str,
        parent_session_id: str,
        platform: str,
        title: str,
        content: str,
        product_line_id: str,
        knowledge_type: str,
        source_uri: str,
        finance_flag: bool,
        sensitivity_level: str,
        confidence: str,
        doc_slug: str,
        asset_type: str = "",
        candidate_type: str = "knowledge",
        chat_id: str = "",
        chat_name: str = "",
        chat_type: str = "",
        evidence_snippet: str = "",
    ) -> dict:
        """Execute a full knowledge write transaction and return a result dict.

        The dict always contains ``transaction_id``, ``current_state``, and either
        ``slug`` (on success) or ``failure_reason`` + ``pending_capture_id`` (on failure).

        This method NEVER raises — all errors are captured in the transaction and
        returned in the result dict.
        """
        if not asset_type:
            asset_type = AssetType.PRODUCT_LINE_KNOWLEDGE

        tx = self._new_tx(
            original_user_id=original_user_id,
            source_session_id=source_session_id,
            root_session_id=root_session_id,
            parent_session_id=parent_session_id,
            platform=platform,
            source_uri=source_uri,
            title=title,
            content=content,
            product_line_id=product_line_id,
            asset_type=asset_type,
            candidate_type=candidate_type,
            knowledge_type=knowledge_type,
            finance_flag=finance_flag,
            sensitivity_level=sensitivity_level,
            confidence=confidence,
            doc_slug=doc_slug,
            chat_id=chat_id,
            chat_name=chat_name,
            chat_type=chat_type,
            evidence_snippet=evidence_snippet,
        )

        self._emit(tx, TransactionState.CANDIDATE_CREATED)

        # — Identity check ——————————————————————————————————————————————————
        try:
            self._assert_identity_not_drifted(original_user_id)
        except IdentityError as exc:
            tx.current_state = TransactionState.IDENTITY_BLOCKED
            tx.failure_reason = str(exc)
            tx.failure_category = "blocked_identity"
            self._emit(tx, TransactionState.IDENTITY_BLOCKED, detail=str(exc))
            return self._fail_result(tx)

        tx.current_state = TransactionState.IDENTITY_RESOLVED
        self._emit(tx, TransactionState.IDENTITY_RESOLVED)

        # — Classification ——————————————————————————————————————————————————
        tx.current_state = TransactionState.CLASSIFIED
        self._emit(tx, TransactionState.CLASSIFIED, detail=f"asset_type={asset_type}")

        # — ACL check ———————————————————————————————————————————————————————
        decision = self._acl.check_write(self._ctx, product_line_id, finance_flag, source_uri)
        if not decision.allowed:
            tx.current_state = TransactionState.ACL_DENIED
            tx.failure_reason = decision.reason
            tx.failure_category = decision.reason
            self._emit(tx, TransactionState.ACL_DENIED, detail=decision.reason)
            audit_event = self._audit.make_event(
                user_id=original_user_id,
                action="write",
                product_line_id=product_line_id,
                finance_flag=finance_flag,
                granted=False,
                deny_reason=decision.reason,
                knowledge_slugs=[doc_slug],
                source_uris=[source_uri] if source_uri else [],
            )
            self._audit.log(audit_event)

            capture_id = self._create_pending(
                tx, content, doc_slug, knowledge_type, finance_flag, sensitivity_level
            )
            tx.pending_capture_id = capture_id
            tx.current_state = TransactionState.PENDING_CREATED
            self._emit(tx, TransactionState.PENDING_CREATED, detail=f"capture_id={capture_id}")
            return self._fail_result(tx)

        tx.current_state = TransactionState.ACL_GRANTED
        self._emit(tx, TransactionState.ACL_GRANTED)

        # Emit legacy ACL-granted audit event for backward compatibility
        audit_event = self._audit.make_event(
            user_id=original_user_id,
            action="write",
            product_line_id=product_line_id,
            finance_flag=finance_flag,
            granted=True,
            deny_reason="",
            knowledge_slugs=[doc_slug],
            source_uris=[source_uri] if source_uri else [],
        )
        self._audit.log(audit_event)

        # — Provider write ——————————————————————————————————————————————————
        now = datetime.now(timezone.utc).isoformat()
        doc = KnowledgeDoc(
            slug=doc_slug, title=title, content=content,
            product_line_id=product_line_id, finance_flag=finance_flag,
            source_uri=source_uri, knowledge_type=knowledge_type,
            sensitivity_level=sensitivity_level, confidence=confidence,
            owner=original_user_id, created_at=now, updated_at=now,
            updated_by=original_user_id,
        )
        tx.current_state = TransactionState.PROVIDER_STARTED
        self._emit(tx, TransactionState.PROVIDER_STARTED)

        try:
            slug = self._provider.write(doc, original_user_id)
            tx.current_state = TransactionState.PROVIDER_SUCCEEDED
            self._emit(tx, TransactionState.PROVIDER_SUCCEEDED, detail=f"slug={slug}")
            return {
                "success": True,
                "transaction_id": tx.transaction_id,
                "current_state": tx.current_state,
                "slug": slug,
                "product_line_id": product_line_id,
            }
        except Exception as exc:
            from plugins.knowledge.gbrain.provider import ProviderUnavailableError
            if isinstance(exc, ProviderUnavailableError):
                failure_category = f"provider_unavailable:{exc.error_code}"
            else:
                failure_category = f"provider_error:{ProviderError.classify(exc)}"
            tx.current_state = TransactionState.PROVIDER_FAILED
            tx.failure_reason = str(exc)
            tx.failure_category = failure_category
            self._emit(
                tx, TransactionState.PROVIDER_FAILED,
                detail=f"category={failure_category} exc={type(exc).__name__}",
            )
            logger.error("KnowledgeOps provider write failed (%s): %s", failure_category, exc)

        # — Pending creation ————————————————————————————————————————————————
        capture_id = self._create_pending(tx, content, doc_slug, knowledge_type, finance_flag, sensitivity_level)
        tx.pending_capture_id = capture_id
        tx.current_state = TransactionState.PENDING_CREATED
        self._emit(tx, TransactionState.PENDING_CREATED, detail=f"capture_id={capture_id}")
        return self._fail_result(tx)

    def _fail_result(self, tx: KnowledgeWriteTransaction) -> dict:
        return {
            "success": False,
            "transaction_id": tx.transaction_id,
            "current_state": tx.current_state,
            "failure_reason": tx.failure_reason,
            "failure_category": tx.failure_category,
            "pending_capture_id": tx.pending_capture_id,
        }

    def _emit(
        self,
        tx: KnowledgeWriteTransaction,
        event_type: str,
        detail: str = "",
    ) -> None:
        try:
            self._audit.emit(
                event_type=event_type,
                transaction_id=tx.transaction_id,
                original_user_id=tx.original_user_id,
                resolved_user_id=tx.resolved_user_id,
                platform=tx.platform,
                source_session_id=tx.source_session_id,
                root_session_id=tx.root_session_id,
                asset_type=tx.asset_type,
                target_scope_id=tx.target_scope_id,
                provider_name=tx.provider_name,
                pending_capture_id=tx.pending_capture_id,
                failure_category=tx.failure_category,
                failure_reason=tx.failure_reason,
                detail=detail,
            )
        except Exception as exc:
            logger.warning("KnowledgeOps audit emit failed: %s", exc)

    def _create_pending(
        self,
        tx: KnowledgeWriteTransaction,
        content: str,
        doc_slug: str,
        knowledge_type: str,
        finance_flag: bool,
        sensitivity_level: str,
    ) -> str:
        from agent.pending_capture import write_pending_capture_tx
        return write_pending_capture_tx(
            tx, content, doc_slug, knowledge_type, finance_flag, sensitivity_level,
            hermes_home=self._hermes_home,
        )


# ---------------------------------------------------------------------------
# David case: cross-layer knowledge classification helper
# ---------------------------------------------------------------------------

def classify_david_knowledge(topic: str, scope_hint: str = "") -> dict:
    """Return asset_type and target_scope_type for David-related knowledge.

    David is the company CEO. His knowledge spans multiple layers:
    - Personal values / decision frameworks → company_knowledge (company-wide)
    - Instructions about a specific product line → product_line_knowledge
    - Judgments about a specific project meeting → project_knowledge
    - How a user reports to David → personal_memory (user-private)

    Args:
        topic: free-form description of the knowledge topic
        scope_hint: optional product_line_id or project_id to narrow scope

    Returns:
        dict with ``asset_type``, ``target_scope_type``, ``target_scope_id``
    """
    topic_lower = topic.lower()
    if any(kw in topic_lower for kw in ("report to", "汇报", "向 david", "how to tell david")):
        return {
            "asset_type": AssetType.PERSONAL_MEMORY,
            "target_scope_type": "user",
            "target_scope_id": "",
            "rationale": "User-private: how the user personally interacts with David",
        }
    if any(kw in topic_lower for kw in ("project meeting", "项目会议", "project judgment")):
        return {
            "asset_type": AssetType.PROJECT_KNOWLEDGE,
            "target_scope_type": "project",
            "target_scope_id": scope_hint,
            "rationale": "Time-bound project decision/meeting judgment",
        }
    if scope_hint and any(kw in topic_lower for kw in ("product line", "产品线", "instruction", "指示", "directive")):
        return {
            "asset_type": AssetType.PRODUCT_LINE_KNOWLEDGE,
            "target_scope_type": "product_line",
            "target_scope_id": scope_hint,
            "rationale": "David's direction specific to a product line",
        }
    # Default: CEO-level values and decision frameworks are company-wide
    return {
        "asset_type": AssetType.COMPANY_KNOWLEDGE,
        "target_scope_type": "company",
        "target_scope_id": "ecovacs_company",
        "rationale": "Company-wide: CEO values, decision frameworks, org-level statements",
    }
