"""Tests for agent/experience_card.py."""
from __future__ import annotations

import json
import pytest
from dataclasses import asdict

from agent.experience_card import (
    DAVID_CARD,
    ExperienceCard,
    create_card,
    render_card,
    trigger_check,
    write_card,
)


# ─── DAVID_CARD 内置卡 ────────────────────────────────────────────────────────

class TestDavidCard:
    def test_id_is_set(self):
        assert DAVID_CARD.id == "david-001"

    def test_trigger_is_david(self):
        assert DAVID_CARD.trigger == "David"

    def test_trigger_patterns_include_david(self):
        assert "David" in DAVID_CARD.trigger_patterns

    def test_retrieval_order_has_three_levels(self):
        assert len(DAVID_CARD.retrieval_order) >= 3

    def test_judgment_steps_has_four_steps(self):
        assert len(DAVID_CARD.judgment_steps) >= 4

    def test_avoid_actions_include_private_chat_rule(self):
        joined = " ".join(DAVID_CARD.avoid_actions)
        assert "私聊" in joined

    def test_avoid_actions_include_company_level_rule(self):
        joined = " ".join(DAVID_CARD.avoid_actions)
        assert "公司级" in joined

    def test_frontstage_expression_no_system_jargon(self):
        expr = DAVID_CARD.frontstage_expression
        for bad_word in ["晋升", "生命周期", "已决策结论"]:
            assert bad_word not in expr, f"系统腔词 '{bad_word}' 出现在前台表达中"

    def test_scope_contains_david(self):
        assert "David" in DAVID_CARD.scope

    def test_invalid_when_not_empty(self):
        assert DAVID_CARD.invalid_when


# ─── trigger_check ────────────────────────────────────────────────────────────

class TestTriggerCheck:
    def test_david_name_triggers(self, tmp_path):
        card = trigger_check("David 在飞书提到跨产品线对齐需求", hermes_home=tmp_path)
        assert card is not None
        assert card.id == "david-001"

    def test_david_lowercase_triggers(self, tmp_path):
        card = trigger_check("david 的偏好是结论先行", hermes_home=tmp_path)
        assert card is not None

    def test_unrelated_text_no_trigger(self, tmp_path):
        card = trigger_check("完全不相关的文字，产品线评审会议纪要", hermes_home=tmp_path)
        assert card is None

    def test_empty_text_no_trigger(self, tmp_path):
        card = trigger_check("", hermes_home=tmp_path)
        assert card is None

    def test_persisted_card_triggers(self, tmp_path):
        custom_card = create_card(
            trigger="Alice",
            trigger_patterns=["Alice", "alice"],
            retrieval_order=["项目材料", "个人偏好"],
            judgment_steps=["确认项目", "确认角色"],
            avoid_actions=["不要猜测"],
            frontstage_expression="简洁直接",
            scope="Alice/product",
            invalid_when="Alice 离职后",
        )
        write_card(custom_card, hermes_home=tmp_path)
        found = trigger_check("Alice 确认了产品需求", hermes_home=tmp_path)
        assert found is not None
        assert found.trigger == "Alice"


# ─── render_card ─────────────────────────────────────────────────────────────

class TestRenderCard:
    def test_includes_usage_hint(self):
        rendered = render_card(DAVID_CARD)
        assert "usage_hint: action_rule_for_next_task" in rendered

    def test_includes_trigger(self):
        rendered = render_card(DAVID_CARD)
        assert "David" in rendered

    def test_includes_avoid_actions(self):
        rendered = render_card(DAVID_CARD)
        assert "私聊" in rendered

    def test_includes_judgment_steps(self):
        rendered = render_card(DAVID_CARD)
        assert "判断步骤" in rendered

    def test_includes_retrieval_order(self):
        rendered = render_card(DAVID_CARD)
        assert "读取优先级" in rendered


# ─── write_card / list ───────────────────────────────────────────────────────

class TestWriteCard:
    def test_creates_jsonl_file(self, tmp_path):
        write_card(DAVID_CARD, hermes_home=tmp_path)
        path = tmp_path / "experience_cards" / "cards.jsonl"
        assert path.exists()

    def test_record_parseable(self, tmp_path):
        write_card(DAVID_CARD, hermes_home=tmp_path)
        path = tmp_path / "experience_cards" / "cards.jsonl"
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert record["id"] == "david-001"
        assert "避免" in " ".join(record["avoid_actions"]) or "私聊" in " ".join(record["avoid_actions"])
        assert record["status"] == "active"
        assert record["producer_runtime_path"] == "agent.experience_card.write_card"
        assert record["source_capability"] == "experience_card"
        assert record["sanitized_summary"]

    def test_never_raises_on_bad_home(self, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", "/nonexistent/path/never")
        result = write_card(DAVID_CARD)
        assert result == "david-001"


# ─── create_card ─────────────────────────────────────────────────────────────

class TestCreateCard:
    def test_auto_fills_id(self):
        card = create_card(
            trigger="TestPerson",
            trigger_patterns=["TestPerson"],
            retrieval_order=["step1"],
            judgment_steps=["step1"],
            avoid_actions=["don't do X"],
            frontstage_expression="简洁",
            scope="TestPerson/test",
            invalid_when="条件变化后",
        )
        assert len(card.id) == 36  # UUID4

    def test_auto_fills_created_at(self):
        card = create_card(
            trigger="TestPerson",
            trigger_patterns=["TestPerson"],
            retrieval_order=["step1"],
            judgment_steps=["step1"],
            avoid_actions=["don't do X"],
            frontstage_expression="简洁",
            scope="TestPerson/test",
            invalid_when="条件变化后",
        )
        assert card.created_at
