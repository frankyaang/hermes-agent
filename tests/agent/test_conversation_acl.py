from agent.conversation_acl import ConversationACLGuard
from agent.knowledge_models import KnowledgeUserContext


def _ctx(**kw) -> KnowledgeUserContext:
    data = dict(
        user_id="u1",
        product_line_ids=[],
        default_product_line_id="",
        finance_product_line_ids=[],
        role="user",
        is_admin=False,
        conversation_access="default",
    )
    data.update(kw)
    return KnowledgeUserContext(**data)


class TestConversationACLGuard:
    def setup_method(self):
        self.guard = ConversationACLGuard()

    def test_admin_with_all_users_gets_all_session_access(self):
        ctx = _ctx(is_admin=True, conversation_access="all_users")
        assert self.guard.has_all_session_access(ctx) is True

    def test_admin_without_conversation_access_does_not_get_all_sessions(self):
        ctx = _ctx(is_admin=True, conversation_access="default")
        assert self.guard.has_all_session_access(ctx) is False

    def test_regular_user_with_all_users_does_not_get_all_sessions(self):
        ctx = _ctx(is_admin=False, conversation_access="all_users")
        assert self.guard.has_all_session_access(ctx) is False

    def test_unknown_conversation_access_is_not_all_sessions(self):
        ctx = _ctx(is_admin=True, conversation_access="unknown_scope")
        assert self.guard.has_all_session_access(ctx) is False

    def test_none_context_is_not_all_sessions(self):
        assert self.guard.has_all_session_access(None) is False
