from __future__ import annotations
from agent.knowledge_models import KnowledgeUserContext, KnowledgeDoc, AccessDecision


class KnowledgeACLGuard:

    def check_read(
        self,
        ctx: KnowledgeUserContext | None,
        product_line_id: str,
        finance_flag: bool,
    ) -> AccessDecision:
        if not ctx or not ctx.user_id:
            return AccessDecision.deny("user_identity_unknown")
        if not ctx.is_admin:
            if product_line_id not in ctx.product_line_ids:
                return AccessDecision.deny("product_line_not_authorized")
        if finance_flag:
            if not ctx.is_admin and product_line_id not in ctx.finance_product_line_ids:
                return AccessDecision.deny("finance_not_authorized")
        return AccessDecision.allow()

    def check_write(
        self,
        ctx: KnowledgeUserContext | None,
        product_line_id: str,
        finance_flag: bool,
        source_uri: str,
    ) -> AccessDecision:
        if not source_uri:
            return AccessDecision.deny("source_uri_required")
        if not ctx or not ctx.user_id:
            return AccessDecision.deny("user_identity_unknown")
        if not ctx.is_admin:
            if product_line_id not in ctx.product_line_ids:
                return AccessDecision.deny("product_line_not_authorized")
        if finance_flag:
            if not ctx.is_admin and product_line_id not in ctx.finance_product_line_ids:
                return AccessDecision.deny("finance_write_not_authorized")
        return AccessDecision.allow()

    def filter_results(
        self,
        ctx: KnowledgeUserContext | None,
        results: list[KnowledgeDoc],
    ) -> list[KnowledgeDoc]:
        return [
            doc for doc in results
            if self.check_read(ctx, doc.product_line_id, doc.finance_flag).allowed
        ]
