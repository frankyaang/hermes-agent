import pytest
from unittest.mock import MagicMock
from agent.knowledge_manager import KnowledgeManager, PermissionDenied
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_models import KnowledgeUserContext, KnowledgeDoc
from datetime import datetime, timezone


def _ctx(**kw):
    d = dict(user_id="feishu:ou_xxx",
             product_line_ids=["cleaning_robot"],
             default_product_line_id="cleaning_robot",
             finance_product_line_ids=["cleaning_robot"],
             role="senior_business", is_admin=False)
    d.update(kw)
    return KnowledgeUserContext(**d)


def _doc(**kw):
    now = datetime.now(timezone.utc).isoformat()
    d = dict(slug="test-slug", title="T", content="c",
             product_line_id="cleaning_robot", finance_flag=False,
             source_uri="feishu://doc/x", knowledge_type="product_spec",
             sensitivity_level="internal", confidence="unverified",
             owner="feishu:ou_xxx", created_at=now, updated_at=now,
             updated_by="feishu:ou_xxx")
    d.update(kw)
    return KnowledgeDoc(**d)


def _manager(ctx=None, provider_docs=None, provider_slug="saved-slug"):
    ctx = ctx or _ctx()
    provider = MagicMock()
    provider.query.return_value = provider_docs or []
    provider.write.return_value = provider_slug
    audit = MagicMock()
    audit.make_event.return_value = MagicMock(
        knowledge_slugs=[], source_uris=[], granted=True, deny_reason="",
        action="", user_id="", product_line_id="", finance_flag=False,
        query_text="",
    )
    mgr = KnowledgeManager(ctx=ctx, provider=provider,
                           acl=KnowledgeACLGuard(), audit=audit)
    return mgr, provider, audit


# --- query ---

def test_query_authorized_returns_results():
    doc = _doc()
    mgr, provider, _ = _manager(provider_docs=[doc])
    results = mgr.query("test", "cleaning_robot")
    assert len(results) == 1
    provider.query.assert_called_once_with("test", "cleaning_robot", False)


def test_query_unauthorized_product_line_returns_empty():
    mgr, provider, _ = _manager()
    results = mgr.query("test", "lawn_robot")
    assert results == []
    provider.query.assert_not_called()


def test_query_finance_without_permission_returns_empty():
    mgr, provider, _ = _manager(ctx=_ctx(finance_product_line_ids=[]))
    results = mgr.query("revenue", "cleaning_robot", finance_ok=True)
    assert results == []
    provider.query.assert_not_called()


def test_query_finance_with_permission_calls_provider():
    doc = _doc(finance_flag=True)
    mgr, provider, _ = _manager(provider_docs=[doc])
    results = mgr.query("revenue", "cleaning_robot", finance_ok=True)
    assert len(results) == 1
    provider.query.assert_called_once_with("revenue", "cleaning_robot", True)


def test_query_filters_out_wrong_product_line_from_provider():
    bad_doc = _doc(product_line_id="lawn_robot")
    mgr, provider, _ = _manager(provider_docs=[bad_doc])
    results = mgr.query("test", "cleaning_robot")
    assert results == []


def test_query_provider_exception_returns_empty():
    mgr, provider, _ = _manager()
    provider.query.side_effect = RuntimeError("backend down")
    results = mgr.query("test", "cleaning_robot")
    assert results == []


def test_query_logs_audit_event():
    mgr, _, audit = _manager()
    mgr.query("test", "cleaning_robot")
    audit.log.assert_called_once()


# --- write ---

def test_write_authorized_calls_provider():
    mgr, provider, _ = _manager()
    slug = mgr.write(_doc())
    assert slug == "saved-slug"
    provider.write.assert_called_once()


def test_write_unauthorized_product_line_raises():
    mgr, provider, _ = _manager()
    with pytest.raises(PermissionDenied):
        mgr.write(_doc(product_line_id="lawn_robot"))
    provider.write.assert_not_called()


def test_write_finance_without_permission_raises():
    mgr, provider, _ = _manager(ctx=_ctx(finance_product_line_ids=[]))
    with pytest.raises(PermissionDenied):
        mgr.write(_doc(finance_flag=True))
    provider.write.assert_not_called()


def test_write_missing_source_uri_raises():
    mgr, provider, _ = _manager()
    with pytest.raises(PermissionDenied):
        mgr.write(_doc(source_uri=""))
    provider.write.assert_not_called()


def test_write_logs_audit_event():
    mgr, _, audit = _manager()
    mgr.write(_doc())
    audit.log.assert_called_once()
