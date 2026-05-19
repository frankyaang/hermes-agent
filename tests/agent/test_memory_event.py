"""Tests for agent/memory_event.py."""
from __future__ import annotations

import json
import pytest
from agent.memory_event import (
    RISK_FLAGS,
    MemoryEvent,
    create_event,
    list_events,
    write_event,
)


# ─── create_event ────────────────────────────────────────────────────────────

class TestCreateEvent:
    def test_returns_memory_event(self):
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/s1",
            actor_user_id="feishu:ou_abc",
            subject="测试主题",
            risk_flags=[],
            recommended_destination="personal_memory",
        )
        assert isinstance(evt, MemoryEvent)

    def test_auto_fills_id(self):
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/s1",
            actor_user_id="feishu:ou_abc",
            subject="主题",
            risk_flags=[],
            recommended_destination="personal_memory",
        )
        assert len(evt.id) == 36  # UUID4

    def test_auto_fills_created_at(self):
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/s1",
            actor_user_id="feishu:ou_abc",
            subject="主题",
            risk_flags=[],
            recommended_destination="personal_memory",
        )
        assert evt.created_at  # 非空

    def test_risk_flags_stored(self):
        evt = create_event(
            source_type="write_failure",
            source_uri="hermes://session/s2",
            actor_user_id="feishu:ou_xyz",
            subject="写入失败",
            risk_flags=["tool_failure", "permission_unclear"],
            recommended_destination="staging",
        )
        assert "tool_failure" in evt.risk_flags
        assert "permission_unclear" in evt.risk_flags

    def test_optional_fields_default_empty(self):
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/s3",
            actor_user_id="feishu:ou_abc",
            subject="主题",
            risk_flags=[],
            recommended_destination="knowledge",
        )
        assert evt.project_hint == ""
        assert evt.product_line_hint == ""
        assert evt.current_task == ""
        assert evt.raw_excerpt_ref == ""
        assert evt.session_id == ""

    def test_optional_fields_set(self):
        evt = create_event(
            source_type="document",
            source_uri="feishu://doc/123",
            actor_user_id="feishu:ou_abc",
            subject="主题",
            risk_flags=["project_uncertain"],
            recommended_destination="staging",
            session_id="sess-99",
            project_hint="PBI_phase2",
            product_line_hint="deebot",
            current_task="需求评审",
            raw_excerpt_ref="excerpt://chunk-1",
        )
        assert evt.session_id == "sess-99"
        assert evt.project_hint == "PBI_phase2"
        assert evt.product_line_hint == "deebot"
        assert evt.current_task == "需求评审"


# ─── RISK_FLAGS 覆盖 ─────────────────────────────────────────────────────────

class TestRiskFlags:
    def test_all_seven_risk_flags_defined(self):
        expected = {
            "private_chat",
            "project_uncertain",
            "permission_unclear",
            "stale_version",
            "user_correction",
            "tool_failure",
            "identity_missing",
        }
        assert expected <= RISK_FLAGS

    def test_at_least_seven_flags(self):
        assert len(RISK_FLAGS) >= 7


# ─── write_event ─────────────────────────────────────────────────────────────

class TestWriteEvent:
    def test_creates_jsonl_file(self, tmp_path):
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/s1",
            actor_user_id="feishu:ou_abc",
            subject="test",
            risk_flags=[],
            recommended_destination="personal_memory",
        )
        write_event(evt, hermes_home=tmp_path)
        path = tmp_path / "memory_events" / "events.jsonl"
        assert path.exists()

    def test_written_record_is_json_parseable(self, tmp_path):
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/s1",
            actor_user_id="feishu:ou_abc",
            subject="test",
            risk_flags=["private_chat"],
            recommended_destination="staging",
        )
        write_event(evt, hermes_home=tmp_path)
        path = tmp_path / "memory_events" / "events.jsonl"
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert record["id"] == evt.id
        assert record["risk_flags"] == ["private_chat"]
        assert record["status"] == "captured"
        assert record["producer_runtime_path"] == "agent.memory_event.write_event"
        assert record["source_capability"] == "memory_event"
        assert record["sanitized_summary"]

    def test_appends_multiple(self, tmp_path):
        for i in range(3):
            evt = create_event(
                source_type="session",
                source_uri=f"hermes://session/s{i}",
                actor_user_id="feishu:ou_abc",
                subject=f"主题{i}",
                risk_flags=[],
                recommended_destination="personal_memory",
            )
            write_event(evt, hermes_home=tmp_path)
        path = tmp_path / "memory_events" / "events.jsonl"
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 3

    def test_never_raises_on_bad_home(self, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", "/nonexistent/path/never")
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/x",
            actor_user_id="feishu:ou_abc",
            subject="test",
            risk_flags=[],
            recommended_destination="personal_memory",
        )
        result = write_event(evt)
        assert result == evt.id  # 返回 id，不抛出

    def test_returns_event_id(self, tmp_path):
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/s1",
            actor_user_id="feishu:ou_abc",
            subject="test",
            risk_flags=[],
            recommended_destination="personal_memory",
        )
        returned_id = write_event(evt, hermes_home=tmp_path)
        assert returned_id == evt.id


# ─── list_events ─────────────────────────────────────────────────────────────

class TestListEvents:
    def test_empty_when_no_file(self, tmp_path):
        assert list_events(hermes_home=tmp_path) == []

    def test_returns_all_written(self, tmp_path):
        for i in range(2):
            evt = create_event(
                source_type="session",
                source_uri=f"hermes://session/s{i}",
                actor_user_id="feishu:ou_abc",
                subject=f"主题{i}",
                risk_flags=[],
                recommended_destination="personal_memory",
            )
            write_event(evt, hermes_home=tmp_path)
        records = list_events(hermes_home=tmp_path)
        assert len(records) == 2
