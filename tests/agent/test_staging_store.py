"""Tests for agent/staging_store.py."""
from __future__ import annotations

import json

from agent.staging_store import (
    NEXT_ACTIONS,
    list_staging,
    read_staging,
    write_staging,
)


class TestNextActions:
    def test_at_least_five_next_actions(self):
        assert len(NEXT_ACTIONS) >= 5

    def test_required_next_actions_present(self):
        required = {
            "wait_for_source",
            "needs_user_confirmation",
            "needs_project_mapping",
            "retry_write",
            "archive_as_reference",
        }
        assert required <= NEXT_ACTIONS


class TestWriteStaging:
    def test_creates_jsonl_file(self, tmp_path):
        write_staging(
            event_id="evt-1",
            reason="identity_missing",
            next_action="needs_user_confirmation",
            source_uri="hermes://session/s1",
            hermes_home=tmp_path,
        )
        path = tmp_path / "staging" / "staging.jsonl"
        assert path.exists()

    def test_returns_staging_id(self, tmp_path):
        sid = write_staging(
            event_id="evt-1",
            reason="test",
            next_action="retry_write",
            source_uri="hermes://session/s1",
            hermes_home=tmp_path,
        )
        assert isinstance(sid, str)
        assert len(sid) == 36  # uuid4

    def test_record_is_parseable(self, tmp_path):
        sid = write_staging(
            event_id="evt-2",
            reason="tool_failure_fallback",
            next_action="retry_write",
            source_uri="feishu://doc/999",
            raw_content="临时保存的内容",
            hermes_home=tmp_path,
        )
        path = tmp_path / "staging" / "staging.jsonl"
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert record["staging_id"] == sid
        assert record["event_id"] == "evt-2"
        assert record["next_action"] == "retry_write"
        assert record["raw_content"] == "临时保存的内容"
        assert record["status"] == "staged"
        assert record["producer_runtime_path"] == "agent.staging_store.write_staging"
        assert record["source_capability"] == "staging_store"
        assert record["sanitized_summary"]

    def test_never_raises_on_bad_home(self, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", "/nonexistent/path/never")
        sid = write_staging(
            event_id="evt-x",
            reason="test",
            next_action="retry_write",
            source_uri="hermes://session/x",
        )
        assert isinstance(sid, str)
        assert len(sid) == 36

    def test_appends_multiple(self, tmp_path):
        for i in range(3):
            write_staging(
                event_id=f"evt-{i}",
                reason="test",
                next_action="retry_write",
                source_uri=f"hermes://session/s{i}",
                hermes_home=tmp_path,
            )
        path = tmp_path / "staging" / "staging.jsonl"
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 3


class TestListStaging:
    def test_empty_when_no_file(self, tmp_path):
        assert list_staging(hermes_home=tmp_path) == []

    def test_returns_all_written(self, tmp_path):
        write_staging(
            event_id="evt-a", reason="r", next_action="retry_write",
            source_uri="hermes://session/a", hermes_home=tmp_path,
        )
        write_staging(
            event_id="evt-b", reason="r", next_action="retry_write",
            source_uri="hermes://session/b", hermes_home=tmp_path,
        )
        records = list_staging(hermes_home=tmp_path)
        assert len(records) == 2

    def test_records_carry_usage_hint(self, tmp_path):
        write_staging(
            event_id="evt-hint", reason="test", next_action="retry_write",
            source_uri="hermes://session/hint", hermes_home=tmp_path,
        )
        records = list_staging(hermes_home=tmp_path)
        assert records[0].get("usage_hint") == "needs_source_check"


class TestReadStaging:
    def test_read_by_staging_id(self, tmp_path):
        sid = write_staging(
            event_id="evt-r", reason="test", next_action="retry_write",
            source_uri="hermes://session/r", hermes_home=tmp_path,
        )
        rec = read_staging(sid, hermes_home=tmp_path)
        assert rec is not None
        assert rec["staging_id"] == sid

    def test_returns_none_when_not_found(self, tmp_path):
        assert read_staging("nonexistent-id", hermes_home=tmp_path) is None


# ─── staging 进入条件验证（通过 dispatcher 触发，这里只测 write_staging 本身）──

class TestStagingTriggerConditions:
    """验证 7 类触发场景都能成功写入 staging。"""

    TRIGGER_CASES = [
        ("identity_missing", "needs_user_confirmation"),
        ("project_uncertain", "needs_user_confirmation"),
        ("permission_unclear", "needs_project_mapping"),
        ("private_chat_no_project_hint", "wait_for_source"),
        ("tool_failure_fallback", "retry_write"),
        ("stale_version", "needs_project_mapping"),
        ("user_correction_scope_unclear", "needs_user_confirmation"),
    ]

    def test_all_trigger_conditions_writable(self, tmp_path):
        for reason, next_action in self.TRIGGER_CASES:
            sid = write_staging(
                event_id=f"evt-{reason}",
                reason=reason,
                next_action=next_action,
                source_uri="hermes://session/test",
                hermes_home=tmp_path,
            )
            assert sid, f"write_staging should return non-empty id for reason={reason}"
