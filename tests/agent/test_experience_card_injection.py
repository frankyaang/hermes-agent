"""ExperienceCard prompt-injection runtime wiring tests.

Verifies trigger_check() + render_card() behavior that is now called from
run_agent.py's user-message injection loop on every API turn.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# trigger_check
# ---------------------------------------------------------------------------

def test_david_card_triggers_on_david(tmp_path):
    from agent.experience_card import trigger_check, DAVID_CARD
    card = trigger_check("David 说要重新审视这个产品方向", hermes_home=tmp_path)
    assert card is not None
    assert card.id == DAVID_CARD.id


def test_trigger_case_insensitive(tmp_path):
    from agent.experience_card import trigger_check
    card = trigger_check("david asked about the roadmap", hermes_home=tmp_path)
    assert card is not None


def test_no_trigger_unrelated_message(tmp_path):
    from agent.experience_card import trigger_check
    card = trigger_check("请帮我分析一下竞品数据", hermes_home=tmp_path)
    assert card is None


def test_no_trigger_empty_message(tmp_path):
    from agent.experience_card import trigger_check
    card = trigger_check("", hermes_home=tmp_path)
    assert card is None


# ---------------------------------------------------------------------------
# render_card
# ---------------------------------------------------------------------------

def test_render_card_has_usage_hint_prefix():
    from agent.experience_card import render_card, DAVID_CARD
    rendered = render_card(DAVID_CARD)
    assert rendered.startswith("[usage_hint: action_rule_for_next_task]")


def test_render_card_contains_retrieval_order():
    from agent.experience_card import render_card, DAVID_CARD
    rendered = render_card(DAVID_CARD)
    assert "读取优先级" in rendered
    for step in DAVID_CARD.retrieval_order:
        assert step in rendered


def test_render_card_contains_avoid_actions():
    from agent.experience_card import render_card, DAVID_CARD
    rendered = render_card(DAVID_CARD)
    assert "禁止动作" in rendered
    for action in DAVID_CARD.avoid_actions:
        assert action in rendered


def test_render_card_contains_scope():
    from agent.experience_card import render_card, DAVID_CARD
    rendered = render_card(DAVID_CARD)
    assert DAVID_CARD.scope in rendered


# ---------------------------------------------------------------------------
# trigger_check respects custom cards persisted to disk
# ---------------------------------------------------------------------------

def test_custom_card_on_disk_is_found(tmp_path):
    from agent.experience_card import create_card, write_card, trigger_check

    card = create_card(
        trigger="UniqueProjectAlpha",
        trigger_patterns=["UniqueProjectAlpha"],
        retrieval_order=["项目材料优先"],
        judgment_steps=["确认版本号"],
        avoid_actions=["不要绕过评审"],
        frontstage_expression="简洁表达",
        scope="test_scope",
        invalid_when="项目结束后",
    )
    write_card(card, hermes_home=tmp_path)

    found = trigger_check("关于 UniqueProjectAlpha 的进展", hermes_home=tmp_path)
    assert found is not None
    assert found.id == card.id


def test_custom_card_does_not_affect_other_triggers(tmp_path):
    from agent.experience_card import create_card, write_card, trigger_check

    card = create_card(
        trigger="OnlyThisKeyword",
        trigger_patterns=["OnlyThisKeyword"],
        retrieval_order=[],
        judgment_steps=[],
        avoid_actions=[],
        frontstage_expression="",
        scope="test",
        invalid_when="never",
    )
    write_card(card, hermes_home=tmp_path)

    # DAVID_CARD still triggers on "David"
    found = trigger_check("David 提到了新需求", hermes_home=tmp_path)
    assert found is not None
