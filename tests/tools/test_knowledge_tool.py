"""Tests for knowledge tool session identity resolution."""

from __future__ import annotations

import yaml

from gateway.session_context import clear_session_vars, set_session_vars
from tools import knowledge_tool


def _write_registry(home, users):
    registry_dir = home / "knowledge"
    registry_dir.mkdir(parents=True)
    (registry_dir / "users.yaml").write_text(
        yaml.safe_dump({"users": users}, allow_unicode=True),
        encoding="utf-8",
    )


def _user(user_id, product_line_ids=None):
    product_line_ids = product_line_ids or ["yang_ma"]
    return {
        "user_id": user_id,
        "display_name": user_id,
        "platform": user_id.split(":", 1)[0] if ":" in user_id else "",
        "product_line_ids": product_line_ids,
        "default_product_line_id": product_line_ids[0],
        "finance_product_line_ids": [],
        "role": "business_user",
        "is_admin": False,
    }


def setup_function():
    knowledge_tool._MANAGER_CACHE.clear()
    set_session_vars()


def teardown_function():
    knowledge_tool._MANAGER_CACHE.clear()
    set_session_vars()


def test_candidate_user_ids_prefixes_feishu_open_id():
    assert knowledge_tool._candidate_user_ids("ou_abc", "feishu") == [
        "feishu:ou_abc",
        "ou_abc",
    ]


def test_get_manager_resolves_feishu_prefixed_registry_user(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    _write_registry(home, [_user("feishu:ou_abc")])
    monkeypatch.setenv("HERMES_HOME", str(home))

    tokens = set_session_vars(platform="feishu", user_id="ou_abc", chat_id="oc_chat")
    try:
        mgr = knowledge_tool._get_manager("task-1")
    finally:
        clear_session_vars(tokens)

    assert mgr is not None
    assert mgr._ctx.user_id == "feishu:ou_abc"


def test_get_manager_falls_back_to_raw_registry_user(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    _write_registry(home, [_user("ou_legacy")])
    monkeypatch.setenv("HERMES_HOME", str(home))

    tokens = set_session_vars(platform="feishu", user_id="ou_legacy", chat_id="oc_chat")
    try:
        mgr = knowledge_tool._get_manager("task-raw")
    finally:
        clear_session_vars(tokens)

    assert mgr is not None
    assert mgr._ctx.user_id == "ou_legacy"


def test_get_manager_cache_is_scoped_by_resolved_identity(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    _write_registry(home, [_user("feishu:ou_one"), _user("feishu:ou_two")])
    monkeypatch.setenv("HERMES_HOME", str(home))

    tokens = set_session_vars(platform="feishu", user_id="ou_one", chat_id="oc_chat")
    try:
        mgr_one = knowledge_tool._get_manager("shared-task")
    finally:
        clear_session_vars(tokens)

    tokens = set_session_vars(platform="feishu", user_id="ou_two", chat_id="oc_chat")
    try:
        mgr_two = knowledge_tool._get_manager("shared-task")
    finally:
        clear_session_vars(tokens)

    assert mgr_one is not None
    assert mgr_two is not None
    assert mgr_one._ctx.user_id == "feishu:ou_one"
    assert mgr_two._ctx.user_id == "feishu:ou_two"


def test_get_manager_denies_unknown_feishu_user(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    _write_registry(home, [_user("feishu:ou_known")])
    monkeypatch.setenv("HERMES_HOME", str(home))

    tokens = set_session_vars(platform="feishu", user_id="ou_unknown", chat_id="oc_chat")
    try:
        mgr = knowledge_tool._get_manager("task-denied")
    finally:
        clear_session_vars(tokens)

    assert mgr is None


# ─── Additional tests for alias normalization and pending capture ──────────────

import json as _json
from unittest.mock import MagicMock


def _write_registry_pl(home, user_id, product_line_ids):
    import yaml
    rd = home / "knowledge"
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "users.yaml").write_text(yaml.safe_dump({"users": [{
        "user_id": user_id,
        "display_name": user_id,
        "product_line_ids": product_line_ids,
        "default_product_line_id": product_line_ids[0] if product_line_ids else "",
        "finance_product_line_ids": [],
        "role": "business_user",
        "is_admin": False,
    }]}), encoding="utf-8")


def _mock_gbrain(monkeypatch, slug="saved-slug"):
    provider = MagicMock()
    provider.write.return_value = slug
    provider.query.return_value = []
    monkeypatch.setattr(
        "plugins.knowledge.gbrain.provider.GBrainCLIKnowledgeProvider",
        lambda: provider,
    )
    return provider


def test_alias_cleaning_robot_normalized_before_acl(tmp_path, monkeypatch):
    """cleaning_robot alias resolves to deebot before ACL check; write succeeds."""
    home = tmp_path / "hermes"
    _write_registry_pl(home, "feishu:ou_alias", ["deebot"])
    monkeypatch.setenv("HERMES_HOME", str(home))
    knowledge_tool._MANAGER_CACHE.clear()
    provider = _mock_gbrain(monkeypatch)

    tokens = set_session_vars(platform="feishu", user_id="ou_alias", chat_id="oc_chat")
    try:
        result = _json.loads(knowledge_tool._knowledge_write(
            title="Deebot spec", content="content",
            product_line_id="cleaning_robot",
            knowledge_type="product_spec",
            source_uri="feishu://doc/123",
            finance_flag=False, sensitivity_level="internal",
            confidence="unverified", doc_slug="", task_id="t1",
        ))
    finally:
        clear_session_vars(tokens)
        knowledge_tool._MANAGER_CACHE.clear()

    assert result.get("success") is True
    assert result.get("product_line_id") == "deebot"
    provider.write.assert_called_once()


def test_acl_failure_creates_pending_capture(tmp_path, monkeypatch):
    """ACL denial writes pending capture and returns pending_capture_id."""
    home = tmp_path / "hermes"
    _write_registry_pl(home, "feishu:ou_acl", ["deebot"])
    monkeypatch.setenv("HERMES_HOME", str(home))
    knowledge_tool._MANAGER_CACHE.clear()
    _mock_gbrain(monkeypatch)

    tokens = set_session_vars(platform="feishu", user_id="ou_acl", chat_id="oc_chat")
    try:
        result = _json.loads(knowledge_tool._knowledge_write(
            title="Unknown PL", content="content",
            product_line_id="unknown_pl",
            knowledge_type="product_spec",
            source_uri="feishu://doc/456",
            finance_flag=False, sensitivity_level="internal",
            confidence="unverified", doc_slug="", task_id="t2",
        ))
    finally:
        clear_session_vars(tokens)
        knowledge_tool._MANAGER_CACHE.clear()

    assert result["error"] == "permission_denied"
    assert "pending_capture_id" in result
    assert len(result["pending_capture_id"]) == 36
    pc_path = home / "knowledge" / "pending_captures.jsonl"
    assert pc_path.exists()
    record = _json.loads(pc_path.read_text(encoding="utf-8").strip())
    assert record["failure_reason"] == "product_line_not_authorized"


def test_missing_source_uri_creates_pending_capture(tmp_path, monkeypatch):
    """source_uri='' triggers source_uri_required ACL denial, creates pending capture."""
    home = tmp_path / "hermes"
    _write_registry_pl(home, "feishu:ou_uri", ["deebot"])
    monkeypatch.setenv("HERMES_HOME", str(home))
    knowledge_tool._MANAGER_CACHE.clear()
    _mock_gbrain(monkeypatch)

    tokens = set_session_vars(platform="feishu", user_id="ou_uri", chat_id="oc_chat")
    try:
        result = _json.loads(knowledge_tool._knowledge_write(
            title="No URI", content="content",
            product_line_id="deebot",
            knowledge_type="product_spec",
            source_uri="",
            finance_flag=False, sensitivity_level="internal",
            confidence="unverified", doc_slug="", task_id="t3",
        ))
    finally:
        clear_session_vars(tokens)
        knowledge_tool._MANAGER_CACHE.clear()

    assert result["error"] == "permission_denied"
    assert result["reason"] == "source_uri_required"
    assert "pending_capture_id" in result
    assert "source_uri" in result["next_action"]


def test_no_product_line_creates_pending_capture(tmp_path, monkeypatch):
    """No product_line_id and no default creates pending capture with missing field."""
    home = tmp_path / "hermes"
    import yaml
    (home / "knowledge").mkdir(parents=True)
    (home / "knowledge" / "users.yaml").write_text(yaml.safe_dump({"users": [{
        "user_id": "feishu:ou_nopl",
        "display_name": "nopl",
        "product_line_ids": ["deebot"],
        "default_product_line_id": "",
        "finance_product_line_ids": [],
        "role": "business_user",
        "is_admin": False,
    }]}), encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    knowledge_tool._MANAGER_CACHE.clear()
    _mock_gbrain(monkeypatch)

    tokens = set_session_vars(platform="feishu", user_id="ou_nopl", chat_id="oc_chat")
    try:
        result = _json.loads(knowledge_tool._knowledge_write(
            title="No PL", content="content",
            product_line_id="",
            knowledge_type="product_spec",
            source_uri="feishu://doc/789",
            finance_flag=False, sensitivity_level="internal",
            confidence="unverified", doc_slug="", task_id="t4",
        ))
    finally:
        clear_session_vars(tokens)
        knowledge_tool._MANAGER_CACHE.clear()

    assert result["error"] == "no_product_line"
    assert "pending_capture_id" in result
    pc_path = home / "knowledge" / "pending_captures.jsonl"
    assert pc_path.exists()
    record = _json.loads(pc_path.read_text(encoding="utf-8").strip())
    assert "product_line_id" in record["missing_fields"]
