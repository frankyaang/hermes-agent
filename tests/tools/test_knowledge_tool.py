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
