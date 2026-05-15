from __future__ import annotations

from agent.knowledge_models import KnowledgeUserContext


class ConversationACLGuard:
    """Conversation-history access checks kept separate from knowledge ACL."""

    ALL_USERS = "all_users"

    def has_all_session_access(self, ctx: KnowledgeUserContext | None) -> bool:
        if not ctx or not ctx.user_id:
            return False
        access = (ctx.conversation_access or "default").strip().lower()
        return bool(ctx.is_admin and access == self.ALL_USERS)
