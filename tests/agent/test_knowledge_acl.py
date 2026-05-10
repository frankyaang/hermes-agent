import pytest
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_models import KnowledgeUserContext, KnowledgeDoc
from datetime import datetime, timezone


def _ctx(**kw) -> KnowledgeUserContext:
    d = dict(user_id="u1", product_line_ids=["cleaning_robot"],
             default_product_line_id="cleaning_robot",
             finance_product_line_ids=[], role="user", is_admin=False)
    d.update(kw)
    return KnowledgeUserContext(**d)


def _doc(**kw) -> KnowledgeDoc:
    now = datetime.now(timezone.utc).isoformat()
    d = dict(slug="s", title="T", content="c", product_line_id="cleaning_robot",
             finance_flag=False, source_uri="feishu://doc/x",
             knowledge_type="product_spec", sensitivity_level="internal",
             confidence="unverified", owner="u1",
             created_at=now, updated_at=now, updated_by="u1")
    d.update(kw)
    return KnowledgeDoc(**d)


class TestCheckRead:
    def setup_method(self):
        self.g = KnowledgeACLGuard()

    def test_allow_authorized_product_line(self):
        assert self.g.check_read(_ctx(), "cleaning_robot", False).allowed

    def test_deny_unauthorized_product_line(self):
        r = self.g.check_read(_ctx(), "lawn_robot", False)
        assert not r.allowed
        assert r.reason == "product_line_not_authorized"

    def test_deny_finance_without_finance_permission(self):
        r = self.g.check_read(_ctx(finance_product_line_ids=[]), "cleaning_robot", True)
        assert not r.allowed
        assert r.reason == "finance_not_authorized"

    def test_allow_finance_with_finance_permission(self):
        r = self.g.check_read(_ctx(finance_product_line_ids=["cleaning_robot"]), "cleaning_robot", True)
        assert r.allowed

    def test_admin_bypasses_product_line(self):
        r = self.g.check_read(_ctx(product_line_ids=[], is_admin=True), "any", False)
        assert r.allowed

    def test_admin_bypasses_finance(self):
        r = self.g.check_read(_ctx(product_line_ids=[], is_admin=True), "any", True)
        assert r.allowed

    def test_deny_empty_user_id(self):
        r = self.g.check_read(_ctx(user_id=""), "cleaning_robot", False)
        assert not r.allowed
        assert r.reason == "user_identity_unknown"

    def test_deny_none_ctx(self):
        r = self.g.check_read(None, "cleaning_robot", False)
        assert not r.allowed


class TestCheckWrite:
    def setup_method(self):
        self.g = KnowledgeACLGuard()

    def test_allow_authorized(self):
        r = self.g.check_write(_ctx(), "cleaning_robot", False, "feishu://doc/x")
        assert r.allowed

    def test_deny_missing_source_uri(self):
        r = self.g.check_write(_ctx(), "cleaning_robot", False, "")
        assert not r.allowed
        assert r.reason == "source_uri_required"

    def test_deny_finance_without_finance_permission(self):
        r = self.g.check_write(_ctx(finance_product_line_ids=[]), "cleaning_robot", True, "feishu://doc/x")
        assert not r.allowed
        assert r.reason == "finance_write_not_authorized"

    def test_allow_finance_with_permission(self):
        r = self.g.check_write(_ctx(finance_product_line_ids=["cleaning_robot"]), "cleaning_robot", True, "feishu://doc/x")
        assert r.allowed

    def test_deny_unauthorized_product_line(self):
        r = self.g.check_write(_ctx(), "lawn_robot", False, "feishu://doc/x")
        assert not r.allowed


class TestFilterResults:
    def setup_method(self):
        self.g = KnowledgeACLGuard()

    def test_removes_unauthorized_product_line(self):
        ctx = _ctx(product_line_ids=["cleaning_robot"])
        docs = [_doc(product_line_id="cleaning_robot"), _doc(product_line_id="lawn_robot")]
        result = self.g.filter_results(ctx, docs)
        assert len(result) == 1
        assert result[0].product_line_id == "cleaning_robot"

    def test_removes_finance_without_permission(self):
        ctx = _ctx(finance_product_line_ids=[])
        docs = [_doc(finance_flag=False), _doc(finance_flag=True)]
        result = self.g.filter_results(ctx, docs)
        assert len(result) == 1
        assert not result[0].finance_flag

    def test_empty_input_returns_empty(self):
        assert self.g.filter_results(_ctx(), []) == []
