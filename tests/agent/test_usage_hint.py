"""Tests for agent/usage_hint.py."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from agent.usage_hint import (
    USAGE_HINTS,
    hint_for_experience_card,
    hint_for_knowledge,
    hint_for_project_process,
    hint_for_session_search,
    hint_for_staging,
    wrap_with_hint,
)


# ─── USAGE_HINTS 枚举 ────────────────────────────────────────────────────────

class TestUsageHints:
    def test_at_least_six_hints(self):
        assert len(USAGE_HINTS) >= 6

    def test_required_hints_present(self):
        required = {
            "private_reference_only",
            "project_material_usable",
            "old_version_background",
            "needs_source_check",
            "do_not_forward_source",
            "action_rule_for_next_task",
        }
        assert required <= USAGE_HINTS


# ─── wrap_with_hint ──────────────────────────────────────────────────────────

class TestWrapWithHint:
    def test_prepends_hint_line(self):
        result = wrap_with_hint("内容文字", "needs_source_check")
        assert result.startswith("[usage_hint: needs_source_check]")

    def test_content_preserved(self):
        content = "这是内容"
        result = wrap_with_hint(content, "project_material_usable")
        assert content in result

    def test_empty_content_returns_empty(self):
        assert wrap_with_hint("", "needs_source_check") == ""

    def test_all_hints_can_be_wrapped(self):
        for hint in USAGE_HINTS:
            result = wrap_with_hint("test", hint)
            assert hint in result


# ─── hint_for_knowledge ──────────────────────────────────────────────────────

class TestHintForKnowledge:
    def test_deprecated_confidence_returns_old_version(self):
        assert hint_for_knowledge({"confidence": "deprecated"}) == "old_version_background"

    def test_draft_confidence_returns_needs_source_check(self):
        assert hint_for_knowledge({"confidence": "draft"}) == "needs_source_check"

    def test_financial_report_type_returns_do_not_forward(self):
        assert hint_for_knowledge({"knowledge_type": "financial_report"}) == "do_not_forward_source"

    def test_financial_kpi_returns_do_not_forward(self):
        assert hint_for_knowledge({"knowledge_type": "financial_kpi"}) == "do_not_forward_source"

    def test_financial_forecast_returns_do_not_forward(self):
        assert hint_for_knowledge({"knowledge_type": "financial_forecast"}) == "do_not_forward_source"

    def test_normal_doc_returns_project_material_usable(self):
        assert hint_for_knowledge({
            "confidence": "verified",
            "knowledge_type": "org_info",
        }) == "project_material_usable"

    def test_empty_doc_returns_project_material_usable(self):
        assert hint_for_knowledge({}) == "project_material_usable"

    def test_confidence_takes_priority_over_knowledge_type(self):
        # deprecated confidence 优先于 knowledge_type
        assert hint_for_knowledge({
            "confidence": "deprecated",
            "knowledge_type": "financial_report",
        }) == "old_version_background"


# ─── hint_for_session_search ─────────────────────────────────────────────────

class TestHintForSessionSearch:
    def test_always_needs_source_check(self):
        assert hint_for_session_search() == "needs_source_check"
        assert hint_for_session_search({}) == "needs_source_check"
        assert hint_for_session_search({"anything": "value"}) == "needs_source_check"


# ─── hint_for_experience_card ────────────────────────────────────────────────

class TestHintForExperienceCard:
    def test_always_action_rule(self):
        assert hint_for_experience_card() == "action_rule_for_next_task"


# ─── hint_for_staging ────────────────────────────────────────────────────────

class TestHintForStaging:
    def test_always_needs_source_check(self):
        assert hint_for_staging() == "needs_source_check"


# ─── hint_for_project_process ────────────────────────────────────────────────

class TestHintForProjectProcess:
    def test_always_project_material_usable(self):
        assert hint_for_project_process() == "project_material_usable"


# ─── session_search tool JSON 结果含 usage_hint ──────────────────────────────

class TestSessionSearchToolHint:
    def test_session_search_result_contains_usage_hint(self, monkeypatch):
        """session_search 返回 JSON 的每条 result 必须含 usage_hint: needs_source_check。"""
        from unittest.mock import MagicMock, AsyncMock, patch as _patch
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "current-session-xxx"
        other_sid = "other-session-yyy"

        mock_db.search_messages.return_value = [
            {"session_id": other_sid, "content": "test match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]
        mock_db.get_session.return_value = {"parent_session_id": None}
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]

        with _patch(
            "tools.session_search_tool.async_call_llm",
            new_callable=AsyncMock,
            side_effect=RuntimeError("no provider"),
        ):
            raw = session_search(
                query="test",
                db=mock_db,
                current_session_id=current_sid,
            )

        result = json.loads(raw)
        assert result["success"] is True
        for item in result.get("results", []):
            assert "usage_hint" in item, f"result item missing usage_hint: {item}"
            assert item["usage_hint"] == "needs_source_check"


# ─── knowledge_query tool JSON 结果含 usage_hint ─────────────────────────────

class TestKnowledgeQueryToolHint:
    def test_knowledge_query_result_contains_usage_hint(self, tmp_path, monkeypatch):
        """knowledge_query 返回 JSON 的每条 result 必须含 usage_hint 字段。"""
        import yaml
        from gateway.session_context import clear_session_vars, set_session_vars
        from tools import knowledge_tool

        registry_dir = tmp_path / "knowledge"
        registry_dir.mkdir(parents=True)
        (registry_dir / "users.yaml").write_text(
            yaml.safe_dump({"users": [{
                "user_id": "feishu:ou_hint_test",
                "display_name": "hint test",
                "product_line_ids": ["deebot"],
                "default_product_line_id": "deebot",
                "finance_product_line_ids": [],
                "role": "business_user",
                "is_admin": False,
            }]}),
            encoding="utf-8",
        )
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        knowledge_tool._MANAGER_CACHE.clear()

        mock_doc = MagicMock()
        mock_doc.slug = "test-slug"
        mock_doc.title = "测试标题"
        mock_doc.snippet = "片段"
        mock_doc.content = "内容"
        mock_doc.source_uri = "feishu://doc/test"
        mock_doc.confidence = "verified"
        mock_doc.knowledge_type = "org_info"

        provider = MagicMock()
        provider.query.return_value = [mock_doc]
        provider.write.return_value = "test-slug"
        monkeypatch.setattr(
            "plugins.knowledge.gbrain.provider.GBrainCLIKnowledgeProvider",
            lambda: provider,
        )

        tokens = set_session_vars(platform="feishu", user_id="ou_hint_test", chat_id="oc_test")
        try:
            raw = knowledge_tool._knowledge_query(
                query="测试", product_line_id="deebot", finance=False, task_id="task-hint"
            )
        finally:
            clear_session_vars(tokens)
            knowledge_tool._MANAGER_CACHE.clear()

        result = json.loads(raw)
        for item in result.get("results", []):
            assert "usage_hint" in item, f"result item missing usage_hint: {item}"
