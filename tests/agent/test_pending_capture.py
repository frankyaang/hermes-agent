"""Tests for agent/pending_capture.py."""
from __future__ import annotations
import json
from pathlib import Path
from agent.pending_capture import write_pending_capture


def _write(tmp_path, **kw):
    defaults = dict(
        title="Test title", summary="Test summary",
        candidate_type="knowledge", scope_id="deebot",
        source_uri="feishu://doc/abc", confidence="medium",
        missing_fields=[], failure_reason="product_line_not_authorized",
        session_id="task-123", user_id="feishu:ou_abc",
        hermes_home=tmp_path,
    )
    defaults.update(kw)
    return write_pending_capture(**defaults)


def test_write_pending_capture_creates_file(tmp_path):
    _write(tmp_path)
    assert (tmp_path / "knowledge" / "pending_captures.jsonl").exists()


def test_write_pending_capture_content_is_json_parseable(tmp_path):
    _write(tmp_path)
    line = (tmp_path / "knowledge" / "pending_captures.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["title"] == "Test title"
    assert record["status"] == "pending"
    assert record["candidate_type"] == "knowledge"


def test_write_pending_capture_returns_capture_id(tmp_path):
    capture_id = _write(tmp_path)
    assert isinstance(capture_id, str)
    assert len(capture_id) == 36  # uuid4


def test_write_pending_capture_appends_multiple(tmp_path):
    _write(tmp_path, title="First")
    _write(tmp_path, title="Second")
    lines = [l for l in (tmp_path / "knowledge" / "pending_captures.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["title"] == "First"
    assert json.loads(lines[1])["title"] == "Second"


def test_write_pending_capture_capture_id_in_file(tmp_path):
    capture_id = _write(tmp_path)
    record = json.loads((tmp_path / "knowledge" / "pending_captures.jsonl")
                        .read_text(encoding="utf-8").strip())
    assert record["capture_id"] == capture_id


def test_write_pending_capture_never_raises_on_bad_home(monkeypatch):
    monkeypatch.setenv("HERMES_HOME", "/nonexistent/path/that/does/not/exist")
    result = write_pending_capture(
        title="T", summary="S", candidate_type="knowledge",
        scope_id="deebot", source_uri="", confidence="low",
        missing_fields=[], failure_reason="test",
        session_id="", user_id="",
    )
    assert isinstance(result, str)
    assert len(result) == 36


def test_write_pending_capture_missing_fields_stored(tmp_path):
    _write(tmp_path, missing_fields=["product_line_id", "source_uri"])
    record = json.loads((tmp_path / "knowledge" / "pending_captures.jsonl")
                        .read_text(encoding="utf-8").strip())
    assert record["missing_fields"] == ["product_line_id", "source_uri"]
