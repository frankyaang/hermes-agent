from __future__ import annotations
import logging
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_audit import KnowledgeAuditLogger
from agent.knowledge_models import KnowledgeDoc, KnowledgeUserContext
from agent.knowledge_provider import KnowledgeProvider

logger = logging.getLogger(__name__)


class PermissionDenied(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class KnowledgeManager:

    def __init__(
        self,
        ctx: KnowledgeUserContext,
        provider: KnowledgeProvider,
        acl: KnowledgeACLGuard | None = None,
        audit: KnowledgeAuditLogger | None = None,
    ):
        self._ctx = ctx
        self._provider = provider
        self._acl = acl or KnowledgeACLGuard()
        self._audit = audit or KnowledgeAuditLogger()

    def query(
        self,
        query: str,
        product_line_id: str,
        finance_ok: bool = False,
    ) -> list[KnowledgeDoc]:
        decision = self._acl.check_read(self._ctx, product_line_id, finance_ok)
        event = self._audit.make_event(
            user_id=self._ctx.user_id,
            action="query",
            product_line_id=product_line_id,
            finance_flag=finance_ok,
            granted=decision.allowed,
            deny_reason=decision.reason,
            query_text=query,
        )
        if not decision.allowed:
            self._audit.log(event)
            return []
        try:
            raw = self._provider.query(query, product_line_id, finance_ok)
            results = self._acl.filter_results(self._ctx, raw)
            event.knowledge_slugs = [d.slug for d in results]
            event.source_uris = [d.source_uri for d in results if d.source_uri]
            self._audit.log(event)
            return results
        except Exception as exc:
            logger.error("knowledge query backend error: %s", exc)
            event.granted = False
            event.deny_reason = f"backend_error:{type(exc).__name__}"
            self._audit.log(event)
            return []

    def write(self, doc: KnowledgeDoc) -> str:
        decision = self._acl.check_write(
            self._ctx, doc.product_line_id, doc.finance_flag, doc.source_uri
        )
        event = self._audit.make_event(
            user_id=self._ctx.user_id,
            action="write",
            product_line_id=doc.product_line_id,
            finance_flag=doc.finance_flag,
            granted=decision.allowed,
            deny_reason=decision.reason,
            knowledge_slugs=[doc.slug],
            source_uris=[doc.source_uri] if doc.source_uri else [],
        )
        self._audit.log(event)
        if not decision.allowed:
            raise PermissionDenied(decision.reason)
        return self._provider.write(doc, self._ctx.user_id)
