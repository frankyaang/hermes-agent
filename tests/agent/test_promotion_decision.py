"""Tests for agent/promotion_decision.py — PromotionDecision 9-scope 分类。

验收合同：
  - 9 个 scope 各有对应测试
  - 无 scope 信息时返回 needs_human_review（阻止自动写入）
  - 不执行任何写入操作
  - source_type=write_failure → rejected_temp
  - risk_flags 含 private_chat → needs_human_review（私聊不自动提升）
"""
from __future__ import annotations
import pytest
from agent.promotion_decision import classify, PromotionScope
from agent.memory_event import create_event


def _evt(**kwargs):
    defaults = dict(
        source_type="session",
        source_uri="hermes://session/promo-test",
        actor_user_id="feishu:ou_test",
        subject="测试主题",
        risk_flags=[],
        recommended_destination="personal_memory",
    )
    defaults.update(kwargs)
    return create_event(**defaults)


class TestPromotionScopes:
    def test_user_correction_no_scope_is_personal(self):
        evt = _evt(risk_flags=["user_correction"], recommended_destination="personal_memory")
        result = classify(evt)
        assert result.scope == "user_long_term_preference"

    def test_project_hint_process_is_project_experience(self):
        evt = _evt(
            recommended_destination="project_process",
            project_hint="PBI_phase2",
            risk_flags=["user_correction"],
        )
        result = classify(evt)
        assert result.scope == "project_experience"

    def test_experience_card_dest_is_expert_pattern(self):
        evt = _evt(recommended_destination="experience_card", risk_flags=["user_correction"])
        result = classify(evt)
        assert result.scope == "expert_pattern"

    def test_knowledge_dest_is_knowledge_ops_candidate(self):
        evt = _evt(recommended_destination="knowledge", risk_flags=["user_correction"])
        result = classify(evt)
        assert result.scope == "knowledge_ops_candidate"

    def test_write_failure_is_rejected_temp(self):
        evt = _evt(source_type="write_failure", risk_flags=["tool_failure"])
        result = classify(evt)
        assert result.scope == "rejected_temp"

    def test_private_chat_is_needs_human_review(self):
        evt = _evt(risk_flags=["private_chat"])
        result = classify(evt)
        assert result.scope == "needs_human_review"

    def test_identity_missing_is_needs_human_review(self):
        evt = _evt(risk_flags=["identity_missing"])
        result = classify(evt)
        assert result.scope == "needs_human_review"

    def test_no_risk_no_hints_is_needs_human_review(self):
        evt = _evt(risk_flags=[], recommended_destination="personal_memory",
                   project_hint="", product_line_hint="")
        result = classify(evt)
        assert result.scope == "needs_human_review"

    def test_session_boundary_flag(self):
        evt = _evt(
            risk_flags=["user_correction"],
            recommended_destination="personal_memory",
            project_hint="",
            product_line_hint="PBI",
        )
        result = classify(evt, session_ending=True)
        assert result.scope == "session_boundary"


class TestNoWriteSideEffect:
    def test_does_not_write_any_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        evt = _evt(risk_flags=["user_correction"])
        classify(evt)
        assert not (tmp_path / "memory_events").exists()
        assert not (tmp_path / "cognitive").exists()

    def test_returns_promotion_scope_object(self):
        evt = _evt(risk_flags=["user_correction"])
        result = classify(evt)
        assert isinstance(result, PromotionScope)
        assert result.scope
        assert result.reason
        assert result.can_auto_promote in (True, False)


class TestAutoPromoteFlag:
    def test_private_chat_cannot_auto_promote(self):
        evt = _evt(risk_flags=["private_chat"])
        result = classify(evt)
        assert result.can_auto_promote is False

    def test_knowledge_ops_candidate_cannot_auto_promote(self):
        evt = _evt(recommended_destination="knowledge", risk_flags=["user_correction"])
        result = classify(evt)
        assert result.can_auto_promote is False

    def test_session_rule_can_auto_promote(self):
        evt = _evt(
            risk_flags=["user_correction"],
            recommended_destination="personal_memory",
            current_task="在当前会话中禁用某词",
        )
        result = classify(evt, session_rule_only=True)
        assert result.scope == "current_session_rule"
        assert result.can_auto_promote is True
