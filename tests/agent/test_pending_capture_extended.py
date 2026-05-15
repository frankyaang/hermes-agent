"""Tests for extended pending_capture fields and list/mark_terminal."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock
import yaml
from agent.pending_capture import (
    write_pending_capture,
    list_pending,
    mark_terminal,
    read_pending,
    replay_pending,
)
from gateway.session_context import get_session_env, set_session_vars
from tools import knowledge_tool


def _write(tmp_path, **kw):
    defaults = dict(
        title="Test", summary="Sum", candidate_type="knowledge",
        scope_id="deebot", source_uri="feishu://doc/x",
        confidence="unverified", missing_fields=[],
        failure_reason="product_line_not_authorized",
        session_id="sess-1", user_id="feishu:ou_abc",
        hermes_home=tmp_path,
    )
    defaults.update(kw)
    return write_pending_capture(**defaults)


def test_write_includes_platform_field(tmp_path):
    _write(tmp_path, platform="feishu")
    rec = json.loads((tmp_path / "knowledge" / "pending_captures.jsonl").read_text())
    assert rec["platform"] == "feishu"


def test_write_platform_defaults_empty(tmp_path):
    _write(tmp_path)
    rec = json.loads((tmp_path / "knowledge" / "pending_captures.jsonl").read_text())
    assert "platform" in rec


def test_write_includes_suggested_next_action(tmp_path):
    _write(tmp_path, suggested_next_action="Add deebot to product_line_ids")
    rec = json.loads((tmp_path / "knowledge" / "pending_captures.jsonl").read_text())
    assert "Add deebot" in rec["suggested_next_action"]


def test_write_includes_terminal_state_empty(tmp_path):
    _write(tmp_path)
    rec = json.loads((tmp_path / "knowledge" / "pending_captures.jsonl").read_text())
    assert rec["terminal_state"] == ""


def test_write_includes_structured_candidate(tmp_path):
    _write(tmp_path, structured_candidate={"knowledge_type": "product_spec"})
    rec = json.loads((tmp_path / "knowledge" / "pending_captures.jsonl").read_text())
    assert json.loads(rec["structured_candidate"])["knowledge_type"] == "product_spec"


def test_list_pending_returns_all(tmp_path):
    _write(tmp_path, title="A")
    _write(tmp_path, title="B")
    records = list_pending(hermes_home=tmp_path)
    assert len(records) == 2
    assert records[0]["title"] == "A"


def test_list_pending_empty_when_no_file(tmp_path):
    records = list_pending(hermes_home=tmp_path)
    assert records == []


def test_mark_terminal_updates_record(tmp_path):
    capture_id = _write(tmp_path, title="ToMark")
    mark_terminal(capture_id, "knowledge_saved", hermes_home=tmp_path)
    records = list_pending(hermes_home=tmp_path)
    marked = [r for r in records if r["capture_id"] == capture_id]
    assert len(marked) == 1
    assert marked[0]["terminal_state"] == "knowledge_saved"
    assert marked[0]["status"] == "written"


def test_mark_terminal_noop_on_unknown_id(tmp_path):
    _write(tmp_path)
    mark_terminal("nonexistent-id", "blocked", hermes_home=tmp_path)
    records = list_pending(hermes_home=tmp_path)
    assert len(records) == 1


def test_read_pending_returns_single_record(tmp_path):
    capture_id = _write(tmp_path, title="A")
    _write(tmp_path, title="B")

    record = read_pending(capture_id, hermes_home=tmp_path)

    assert record is not None
    assert record["capture_id"] == capture_id
    assert record["title"] == "A"


def test_read_pending_returns_none_for_unknown_id(tmp_path):
    _write(tmp_path)

    assert read_pending("missing", hermes_home=tmp_path) is None


def test_replay_pending_marks_knowledge_saved_on_success(tmp_path, monkeypatch):
    capture_id = _write(tmp_path, title="Replay", scope_id="deebot")
    monkeypatch.setattr(
        "agent.pending_capture._replay_write_knowledge",
        lambda record: {"success": True, "slug": "replayed"},
    )

    result = replay_pending(capture_id, hermes_home=tmp_path)
    record = read_pending(capture_id, hermes_home=tmp_path)

    assert result["status"] == "replayed"
    assert record["terminal_state"] == "knowledge_saved"
    assert record["status"] == "written"


def test_replay_pending_marks_blocked_on_failure(tmp_path, monkeypatch):
    capture_id = _write(tmp_path, title="ReplayFail", scope_id="deebot")
    monkeypatch.setattr(
        "agent.pending_capture._replay_write_knowledge",
        lambda record: {"error": "permission_denied", "reason": "product_line_not_authorized"},
    )

    result = replay_pending(capture_id, hermes_home=tmp_path)
    record = read_pending(capture_id, hermes_home=tmp_path)

    assert result["status"] == "blocked"
    assert record["terminal_state"] == "blocked"
    assert record["status"] == "blocked"


def test_replay_pending_returns_not_found_for_unknown_id(tmp_path):
    result = replay_pending("missing", hermes_home=tmp_path)

    assert result["status"] == "not_found"


def test_replay_pending_uses_captured_session_identity(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    registry_dir = home / "knowledge"
    registry_dir.mkdir(parents=True)
    (registry_dir / "users.yaml").write_text(
        yaml.safe_dump({
            "users": [
                {
                    "user_id": "feishu:ou_original",
                    "display_name": "Original",
                    "product_line_ids": ["deebot"],
                    "default_product_line_id": "deebot",
                    "finance_product_line_ids": [],
                    "role": "business_user",
                    "is_admin": False,
                },
                {
                    "user_id": "cli:runner:default",
                    "display_name": "Runner",
                    "product_line_ids": [],
                    "default_product_line_id": "",
                    "finance_product_line_ids": [],
                    "role": "business_user",
                    "is_admin": False,
                },
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    provider = MagicMock()
    provider.write.return_value = "replayed-by-original"
    provider.query.return_value = []
    monkeypatch.setattr(
        "plugins.knowledge.gbrain.provider.GBrainCLIKnowledgeProvider",
        lambda: provider,
    )
    knowledge_tool._MANAGER_CACHE.clear()

    capture_id = _write(
        home,
        platform="feishu",
        user_id="feishu:ou_original",
        structured_candidate={
            "content": "Structured replay content",
            "knowledge_type": "meeting_conclusion",
        },
    )
    set_session_vars(platform="cli", user_id="cli:runner:default")
    try:
        result = replay_pending(capture_id, hermes_home=home)
        record = read_pending(capture_id, hermes_home=home)
        restored_platform = get_session_env("HERMES_SESSION_PLATFORM")
        restored_user_id = get_session_env("HERMES_SESSION_USER_ID")
    finally:
        knowledge_tool._MANAGER_CACHE.clear()
        set_session_vars()

    assert result["status"] == "replayed"
    assert record["terminal_state"] == "knowledge_saved"
    assert restored_platform == "cli"
    assert restored_user_id == "cli:runner:default"
    written_doc = provider.write.call_args.args[0]
    assert written_doc.owner == "feishu:ou_original"
    assert written_doc.content == "Structured replay content"
    assert written_doc.knowledge_type == "meeting_conclusion"
