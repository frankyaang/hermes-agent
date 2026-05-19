"""Tests for agent/memory_dispatcher.py."""
from __future__ import annotations

import pytest

from agent.memory_dispatcher import (
    DEST_EXPERIENCE_CARD,
    DEST_KNOWLEDGE,
    DEST_PERSONAL_MEMORY,
    DEST_PROJECT_PROCESS,
    DEST_STAGING,
    DispatchResult,
    dispatch_event,
    dispatch_tool_failure,
)
from agent.memory_event import create_event


def _evt(**kw):
    """Helper：创建最小 MemoryEvent。"""
    defaults = dict(
        source_type="session",
        source_uri="hermes://session/s1",
        actor_user_id="feishu:ou_test",
        subject="测试",
        risk_flags=[],
        recommended_destination="personal_memory",
    )
    defaults.update(kw)
    return create_event(**defaults)


# ─── 规则 1：identity_missing 或 project_uncertain → staging ─────────────────

class TestRule1IdentityOrProjectUncertain:
    def test_identity_missing_to_staging(self, tmp_path):
        evt = _evt(risk_flags=["identity_missing"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_STAGING
        assert result.staging_id  # 非空
        assert "identity_missing" in result.reason

    def test_project_uncertain_to_staging(self, tmp_path):
        evt = _evt(risk_flags=["project_uncertain"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_STAGING
        assert result.staging_id

    def test_staging_next_action_is_needs_user_confirmation(self, tmp_path):
        from agent.staging_store import read_staging
        evt = _evt(risk_flags=["identity_missing"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        rec = read_staging(result.staging_id, hermes_home=tmp_path)
        assert rec["next_action"] == "needs_user_confirmation"


# ─── 规则 2：private_chat + 无 project_hint → staging(wait_for_source) ────────

class TestRule2PrivateChatNoProject:
    def test_private_chat_no_hint_to_staging(self, tmp_path):
        evt = _evt(risk_flags=["private_chat"], project_hint="")
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_STAGING
        assert result.staging_id

    def test_private_chat_staging_next_action_wait_for_source(self, tmp_path):
        from agent.staging_store import read_staging
        evt = _evt(risk_flags=["private_chat"], project_hint="")
        result = dispatch_event(evt, hermes_home=tmp_path)
        rec = read_staging(result.staging_id, hermes_home=tmp_path)
        assert rec["next_action"] == "wait_for_source"

    def test_private_chat_with_project_hint_and_project_process_dest_goes_to_staging(self, tmp_path):
        # Rule 2a（PR 2）：private_chat + recommended_destination=project_process
        # → staging(needs_user_confirmation)，无论有无 project_hint
        from agent.staging_store import read_staging
        evt = _evt(risk_flags=["private_chat"], project_hint="PBI_phase2",
                   recommended_destination="project_process")
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_STAGING
        rec = read_staging(result.staging_id, hermes_home=tmp_path)
        assert rec["next_action"] == "needs_user_confirmation"


# ─── 规则 3：tool_failure → staging(retry_write) + 关系记录 ───────────────────

class TestRule3ToolFailure:
    def test_tool_failure_to_staging(self, tmp_path):
        evt = _evt(risk_flags=["tool_failure"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_STAGING
        assert result.staging_id

    def test_tool_failure_staging_next_action_retry_write(self, tmp_path):
        from agent.staging_store import read_staging
        evt = _evt(risk_flags=["tool_failure"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        rec = read_staging(result.staging_id, hermes_home=tmp_path)
        assert rec["next_action"] == "retry_write"

    def test_tool_failure_creates_relation(self, tmp_path):
        evt = _evt(risk_flags=["tool_failure"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert len(result.relation_ids) >= 1


# ─── 规则 4：user_correction + 无 scope → staging + 关系 ─────────────────────

class TestRule4UserCorrectionNoScope:
    def test_user_correction_no_scope_to_staging(self, tmp_path):
        evt = _evt(
            risk_flags=["user_correction"],
            project_hint="",
            product_line_hint="",
        )
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_STAGING
        assert len(result.relation_ids) >= 1


# ─── 规则 5：permission_unclear 或 stale_version → staging ───────────────────

class TestRule5PermissionOrStale:
    def test_permission_unclear_to_staging(self, tmp_path):
        evt = _evt(risk_flags=["permission_unclear"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_STAGING

    def test_stale_version_to_staging(self, tmp_path):
        evt = _evt(risk_flags=["stale_version"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_STAGING

    def test_staging_next_action_needs_project_mapping(self, tmp_path):
        from agent.staging_store import read_staging
        evt = _evt(risk_flags=["permission_unclear"])
        result = dispatch_event(evt, hermes_home=tmp_path)
        rec = read_staging(result.staging_id, hermes_home=tmp_path)
        assert rec["next_action"] == "needs_project_mapping"


# ─── 规则 6：user_correction + 有 scope → personal_memory ────────────────────

class TestRule6UserCorrectionWithScope:
    def test_user_correction_with_project_hint_to_personal(self, tmp_path):
        evt = _evt(
            source_type="user_correction",
            risk_flags=["user_correction"],
            project_hint="PBI_phase2",
        )
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_PERSONAL_MEMORY
        assert result.staging_id == ""


# ─── 规则 7-9：recommended_destination 路由 ──────────────────────────────────

class TestRecommendedDestinationRouting:
    def test_recommended_experience_card(self, tmp_path):
        evt = _evt(recommended_destination="experience_card")
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_EXPERIENCE_CARD

    def test_recommended_project_process(self, tmp_path):
        evt = _evt(recommended_destination="project_process")
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_PROJECT_PROCESS

    def test_recommended_knowledge(self, tmp_path):
        evt = _evt(recommended_destination="knowledge")
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_KNOWLEDGE


# ─── 规则 10：默认 → personal_memory ─────────────────────────────────────────

class TestDefaultPersonalMemory:
    def test_no_flags_no_hint_to_personal(self, tmp_path):
        evt = _evt(risk_flags=[], recommended_destination="personal_memory")
        result = dispatch_event(evt, hermes_home=tmp_path)
        assert result.destination == DEST_PERSONAL_MEMORY
        assert result.staging_id == ""


# ─── dispatch_tool_failure 便捷入口 ──────────────────────────────────────────

class TestDispatchToolFailure:
    def test_creates_staging_entry(self, tmp_path):
        result = dispatch_tool_failure(
            title="David 公司级偏好",
            source_uri="hermes://session/david-test",
            actor_user_id="feishu:ou_david",
            session_id="sess-001",
            product_line_hint="ecovacs_company",
            hermes_home=tmp_path,
        )
        assert result.destination == DEST_STAGING
        assert result.staging_id

    def test_creates_memory_event_file(self, tmp_path):
        dispatch_tool_failure(
            title="写入失败示例",
            source_uri="hermes://session/fail-test",
            actor_user_id="feishu:ou_test",
            hermes_home=tmp_path,
        )
        from agent.memory_event import list_events
        events = list_events(hermes_home=tmp_path)
        assert len(events) >= 1
        assert events[0]["source_type"] == "write_failure"
        assert "tool_failure" in events[0]["risk_flags"]

    def test_creates_relation_record(self, tmp_path):
        result = dispatch_tool_failure(
            title="权限失败",
            source_uri="hermes://session/perm-fail",
            actor_user_id="feishu:ou_test",
            hermes_home=tmp_path,
        )
        assert len(result.relation_ids) >= 1


# ─── write_to_store=False（纯逻辑模式，不写文件）────────────────────────────

class TestDryRun:
    def test_dry_run_no_file_written(self, tmp_path):
        evt = _evt(risk_flags=["tool_failure"])
        result = dispatch_event(evt, hermes_home=tmp_path, write_to_store=False)
        assert result.destination == DEST_STAGING
        staging_path = tmp_path / "staging" / "staging.jsonl"
        assert not staging_path.exists()
