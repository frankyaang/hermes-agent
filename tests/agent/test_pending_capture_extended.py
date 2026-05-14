"""Tests for extended pending_capture fields and list/mark_terminal."""
from __future__ import annotations
import json
from pathlib import Path
from agent.pending_capture import write_pending_capture, list_pending, mark_terminal


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


def test_mark_terminal_noop_on_unknown_id(tmp_path):
    _write(tmp_path)
    mark_terminal("nonexistent-id", "blocked", hermes_home=tmp_path)
    records = list_pending(hermes_home=tmp_path)
    assert len(records) == 1
