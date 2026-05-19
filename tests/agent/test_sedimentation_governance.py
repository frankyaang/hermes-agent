"""Sedimentation Governance Contract Tests (S1–S12)

These tests prove the governance contracts for the Hermes Sedimentation Backbone.
They verify that all content sources (David private chat, PBI, user correction,
gstack output, tool failure) are routed correctly by the dispatcher.

HERMES_HOME is automatically isolated by conftest.py _hermetic_environment fixture.
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path


# ── S1 ─────────────────────────────────────────────────────────────────────────

def test_david_private_chat_goes_to_staging(tmp_path):
    """David 私聊 → staging，不进 knowledge 或 project_process。"""
    from agent.memory_event import create_event
    from agent.memory_dispatcher import dispatch_event, DEST_STAGING

    event = create_event(
        source_type="session",
        source_uri="hermes://session/test-s1",
        actor_user_id="david",
        subject="David 说他个人偏好不要用系统腔",
        risk_flags=["private_chat"],
        recommended_destination="personal_memory",
    )
    result = dispatch_event(event, hermes_home=tmp_path)

    assert result.destination == DEST_STAGING, (
        f"David 私聊必须进 staging，实际: {result.destination}"
    )
    assert result.staging_id, "staging_id 必须非空"


# ── S2 ─────────────────────────────────────────────────────────────────────────

def test_pbi_goes_to_project_process(tmp_path):
    """PBI 内容（有 project_hint）→ project_process。"""
    from agent.memory_event import create_event
    from agent.memory_dispatcher import dispatch_event, DEST_PROJECT_PROCESS
    from agent.project_process_store import list_records

    event = create_event(
        source_type="document",
        source_uri="hermes://feishu/pbi-2026-001",
        actor_user_id="pm_user",
        subject="PBI: 添加用户偏好设置功能",
        risk_flags=[],
        recommended_destination="project_process",
        project_hint="project-alpha-v2",
    )
    result = dispatch_event(event, hermes_home=tmp_path)

    assert result.destination == DEST_PROJECT_PROCESS, (
        f"PBI 内容应进 project_process，实际: {result.destination}"
    )
    records = list_records(hermes_home=tmp_path)
    assert any(r["event_id"] == event.id for r in records), (
        "project_process_store 应有对应记录"
    )


# ── S3 ─────────────────────────────────────────────────────────────────────────

def test_private_to_project_needs_confirmation(tmp_path):
    """私聊内容推荐进 project_process → 必须进 staging(needs_user_confirmation)。"""
    from agent.memory_event import create_event
    from agent.memory_dispatcher import dispatch_event, DEST_STAGING
    from agent.staging_store import read_staging

    event = create_event(
        source_type="session",
        source_uri="hermes://session/test-s3",
        actor_user_id="david",
        subject="David 说这个功能应该放到下一个版本",
        risk_flags=["private_chat"],
        recommended_destination="project_process",
        project_hint="project-beta",
    )
    result = dispatch_event(event, hermes_home=tmp_path)

    assert result.destination == DEST_STAGING
    entry = read_staging(result.staging_id, hermes_home=tmp_path)
    assert entry is not None
    assert entry["next_action"] == "needs_user_confirmation", (
        f"私聊→项目需要用户确认，实际 next_action: {entry['next_action']}"
    )


# ── S4 ─────────────────────────────────────────────────────────────────────────

def test_user_correction_creates_experience_card(tmp_path):
    """用户纠正（有明确 scope）→ personal_memory，写入 user_correction 关系。"""
    from agent.memory_event import create_event
    from agent.memory_dispatcher import dispatch_event, DEST_PERSONAL_MEMORY
    from agent.memory_relations import list_relations

    event = create_event(
        source_type="user_correction",
        source_uri="hermes://session/test-s4",
        actor_user_id="user_alice",
        subject="用户纠正：不要用'晋升'这个词",
        risk_flags=["user_correction"],
        recommended_destination="experience_card",
        project_hint="project-gamma",
    )
    result = dispatch_event(event, hermes_home=tmp_path)

    assert result.destination == DEST_PERSONAL_MEMORY
    relations = list_relations(hermes_home=tmp_path)
    correction_rels = [r for r in relations if r["relation_type"] == "user_correction"]
    assert len(correction_rels) >= 1, "应有 user_correction 关系记录"


# ── S5 ─────────────────────────────────────────────────────────────────────────

def test_failed_knowledge_write_goes_to_pending_replay(tmp_path):
    """knowledge write 失败 → staging(retry_write)，内容不丢失。"""
    from agent.memory_dispatcher import dispatch_tool_failure, DEST_STAGING
    from agent.staging_store import list_staging

    result = dispatch_tool_failure(
        title="无权限写入 product_line_id=secret",
        source_uri="hermes://knowledge/write-attempt-1",
        actor_user_id="agent_system",
        session_id="sess-s5",
        hermes_home=tmp_path,
    )

    assert result.destination == DEST_STAGING
    entries = list_staging(hermes_home=tmp_path)
    assert any(e["event_id"] == result.event_id for e in entries), (
        "staging 应有对应记录"
    )
    matching = [e for e in entries if e["event_id"] == result.event_id]
    assert matching[0]["next_action"] == "retry_write", (
        f"tool_failure 应标记 retry_write，实际: {matching[0]['next_action']}"
    )


# ── S6 ─────────────────────────────────────────────────────────────────────────

def test_access_denied_not_discarded(tmp_path):
    """权限拒绝（permission_unclear）→ staging，内容不被丢弃。"""
    from agent.memory_event import create_event
    from agent.memory_dispatcher import dispatch_event, DEST_STAGING
    from agent.staging_store import list_staging

    event = create_event(
        source_type="tool_result",
        source_uri="hermes://tool/knowledge_write",
        actor_user_id="agent",
        subject="无权限内容：finance KPI Q1",
        risk_flags=["permission_unclear"],
        recommended_destination="staging",
    )
    result = dispatch_event(event, hermes_home=tmp_path)

    assert result.destination == DEST_STAGING
    entries = list_staging(hermes_home=tmp_path)
    assert any(e["event_id"] == event.id for e in entries), (
        "权限拒绝内容必须进 staging，不能被丢弃"
    )


# ── S7 ─────────────────────────────────────────────────────────────────────────

def test_readback_has_usage_hint():
    """所有回读内容携带 usage_hint（wrap_with_hint）。"""
    from agent.usage_hint import wrap_with_hint, hint_for_knowledge, USAGE_HINTS

    doc = {"confidence": "high", "knowledge_type": "business_fact"}
    hint = hint_for_knowledge(doc)
    assert hint in USAGE_HINTS

    content = "这是一段知识库内容。"
    wrapped = wrap_with_hint(content, hint)
    assert wrapped.startswith("[usage_hint:"), (
        f"回读内容必须有 usage_hint 前缀，实际: {wrapped[:40]}"
    )
    assert content in wrapped, "原始内容不能被修改"

    # financial 类型 → do_not_forward_source
    fin_doc = {"confidence": "high", "knowledge_type": "financial_kpi"}
    fin_hint = hint_for_knowledge(fin_doc)
    assert fin_hint == "do_not_forward_source"

    # deprecated → old_version_background
    dep_doc = {"confidence": "deprecated"}
    dep_hint = hint_for_knowledge(dep_doc)
    assert dep_hint == "old_version_background"


# ── S8 ─────────────────────────────────────────────────────────────────────────

def test_expert_mem_only_expert_experience(tmp_path):
    """expert_mem 仅接受对应 expert 自身写入；gstack 被拒绝。"""
    from agent_system.sedimentation.experience_layer import write_to_layer

    # gstack 尝试直接写 expert_mem → 被拒
    result = write_to_layer(
        layer="expert_mem",
        content="gstack lesson: always verify before writing",
        caller_id="gstack_bridge",
        expert_id="audit_expert",
        hermes_home=tmp_path,
    )
    assert not result.success, "gstack 不能直接写 expert_mem"
    assert result.staging_id, "被拒内容必须进 staging"

    # 对应 expert 自身写入 → 成功
    result_ok = write_to_layer(
        layer="expert_mem",
        content="audit_expert lesson: cross-validate sources",
        caller_id="audit_expert",
        expert_id="audit_expert",
        hermes_home=tmp_path,
    )
    assert result_ok.success, "audit_expert 可以写 expert_mem"

    # 其他 expert 写入 → 被拒
    result_other = write_to_layer(
        layer="expert_mem",
        content="builder_expert content",
        caller_id="builder_expert",
        expert_id="audit_expert",
        hermes_home=tmp_path,
    )
    assert not result_other.success, "builder_expert 不能写 audit_expert 的 expert_mem"


# ── S9 ─────────────────────────────────────────────────────────────────────────

def test_skill_mem_only_skill_history(tmp_path):
    """skill_mem 仅接受对应 skill 自身写入；gstack 被拒绝。"""
    from agent_system.sedimentation.experience_layer import write_to_layer

    # gstack 尝试直接写 skill_mem → 被拒
    result = write_to_layer(
        layer="skill_mem",
        content="gstack playbook: use batch queries",
        caller_id="gstack_control",
        skill_id="sql_skill",
        hermes_home=tmp_path,
    )
    assert not result.success, "gstack 不能直接写 skill_mem"
    assert result.staging_id, "被拒内容必须进 staging"

    # 对应 skill 自身写入 → 成功
    result_ok = write_to_layer(
        layer="skill_mem",
        content="sql_skill execution: batched 100 queries in 2s",
        caller_id="sql_skill",
        skill_id="sql_skill",
        hermes_home=tmp_path,
    )
    assert result_ok.success, "sql_skill 可以写自己的 skill_mem"


# ── S10 ────────────────────────────────────────────────────────────────────────

def test_gstack_review_goes_to_audit_only(tmp_path, monkeypatch):
    """gstack review → audit/evidence，不进 expert_mem。"""
    monkeypatch.setenv("GSTACK_SEDIMENTATION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)

    from agent_system.sedimentation.gstack_bridge import route

    result = route(
        output="Code review: no issues found in PR #42",
        output_type="review",
        source_uri="hermes://gstack/review/pr-42",
        actor_id="gstack",
        hermes_home=tmp_path,
    )

    assert not result.skipped
    assert result.destination == "audit_evidence", (
        f"gstack review 必须去 audit_evidence，实际: {result.destination}"
    )
    assert result.destination != "expert_mem"
    assert result.destination != "system_mem"


# ── S11 ────────────────────────────────────────────────────────────────────────

def test_gstack_playbook_becomes_skill_asset(tmp_path, monkeypatch):
    """gstack playbook → Skill asset（feature flag 守卫）。"""
    # feature flag OFF → skipped
    monkeypatch.delenv("GSTACK_SEDIMENTATION_ENABLED", raising=False)

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)

    from agent_system.sedimentation.gstack_bridge import route

    result_off = route(
        output="Playbook: deploy rollback steps",
        output_type="playbook",
        source_uri="hermes://gstack/playbook/deploy",
        hermes_home=tmp_path,
    )
    assert result_off.skipped, "GSTACK_SEDIMENTATION_ENABLED=false 必须 skip"

    # feature flag ON → skill_asset
    monkeypatch.setenv("GSTACK_SEDIMENTATION_ENABLED", "true")
    importlib.reload(ff)

    from agent_system.sedimentation import gstack_bridge as gb
    importlib.reload(gb)

    result_on = gb.route(
        output="Playbook: deploy rollback steps",
        output_type="playbook",
        source_uri="hermes://gstack/playbook/deploy",
        hermes_home=tmp_path,
    )
    assert not result_on.skipped
    assert result_on.destination == "skill_asset", (
        f"gstack playbook 应为 skill_asset，实际: {result_on.destination}"
    )


# ── S12 ────────────────────────────────────────────────────────────────────────

def test_gstack_retrospective_becomes_expert_mem_candidate(tmp_path, monkeypatch):
    """gstack 专家复盘（lesson）→ expert_mem candidate，不直接写 expert_mem。"""
    monkeypatch.setenv("GSTACK_SEDIMENTATION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)
    import agent_system.sedimentation.gstack_bridge as gb
    importlib.reload(gb)

    result = gb.route(
        output="Retrospective: we should have validated inputs earlier",
        output_type="lesson",
        source_uri="hermes://gstack/retro/sprint-10",
        actor_id="gstack",
        hermes_home=tmp_path,
    )

    assert not result.skipped
    assert result.destination == "expert_mem_candidate", (
        f"gstack lesson 必须为 candidate，实际: {result.destination}"
    )
    # 验证没有直接写 expert_mem（experience_layer ACL 保护）
    from agent_system.sedimentation.experience_layer import write_to_layer
    acl_result = write_to_layer(
        layer="expert_mem",
        content="gstack retrospective",
        caller_id="gstack",
        hermes_home=tmp_path,
    )
    assert not acl_result.success, "gstack 不能直接写 expert_mem（ACL 保护）"
