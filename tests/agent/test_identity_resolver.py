"""Tests for identity_resolver — session-aware user ID resolution."""
from __future__ import annotations
from gateway.session_context import set_session_vars, clear_session_vars
from agent.identity_resolver import resolve_identity, IdentitySource, candidate_registry_ids


def test_feishu_identity_returns_prefixed():
    tokens = set_session_vars(platform="feishu", user_id="ou_abc123", chat_id="oc_chat")
    try:
        identity = resolve_identity()
    finally:
        clear_session_vars(tokens)
    assert identity.user_id == "feishu:ou_abc123"
    assert identity.platform == "feishu"
    assert identity.source == IdentitySource.SESSION


def test_feishu_already_prefixed_not_double_prefixed():
    tokens = set_session_vars(platform="feishu", user_id="feishu:ou_abc", chat_id="oc_chat")
    try:
        identity = resolve_identity()
    finally:
        clear_session_vars(tokens)
    assert identity.user_id == "feishu:ou_abc"


def test_cli_fallback_uses_getuser():
    tokens = set_session_vars()
    try:
        identity = resolve_identity()
    finally:
        clear_session_vars(tokens)
    assert identity.user_id.startswith("cli:")
    assert identity.source == IdentitySource.CLI_FALLBACK


def test_feishu_empty_user_id_falls_back_to_cli():
    tokens = set_session_vars(platform="feishu", user_id="", chat_id="oc_chat")
    try:
        identity = resolve_identity()
    finally:
        clear_session_vars(tokens)
    assert not identity.user_id.startswith("feishu:")


def test_candidate_registry_ids_feishu():
    ids = candidate_registry_ids("feishu", "ou_xyz")
    assert "feishu:ou_xyz" in ids
    assert "ou_xyz" in ids


def test_candidate_registry_ids_empty_falls_back_to_cli():
    import getpass, os
    profile = os.getenv("HERMES_PROFILE", "default")
    ids = candidate_registry_ids("", "")
    assert f"cli:{getpass.getuser()}:{profile}" in ids
