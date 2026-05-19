"""Cognitive Governance Kernel — Thin Vertical Slice + Scenario Golden Tests.

验收合同（Thin Vertical Slice）：
  user_message → session_capture → ExperienceCard hit → routing_hint
  → InsightGapScan → PromotionDecision scope → working_memory contains card hint

场景金测（Requirement I）：
  SC1: 多轮深度思考产生 InsightDelta 或明确停止
  SC2: 用户纠正专家层分权后不再误判
  SC3: KnowledgeOps pending → 风险经验路由到 staging
  SC4: ExperienceCard 命中后行为改变（routing hint 出现）
  SC5: 私聊内容不得搬运进正式材料（私聊 → staging，不是 knowledge）
"""
from __future__ import annotations

import pytest

from agent.insight_gap_scan import scan
from agent.memory_dispatcher import dispatch_event, DEST_STAGING, DEST_PERSONAL_MEMORY
from agent.memory_event import create_event
from agent.promotion_decision import classify
from agent.session_capture import capture_turn


def _evt(**kw):
    defaults = dict(
        source_type="session",
        source_uri="hermes://session/vs-test",
        actor_user_id="feishu:ou_test",
        subject="vertical slice 测试",
        risk_flags=[],
        recommended_destination="personal_memory",
    )
    defaults.update(kw)
    return create_event(**defaults)


# ─── Thin Vertical Slice ──────────────────────────────────────────────────────

def test_experience_card_hit_produces_routing_hint(tmp_path):
    """user_message 含 David → capture_turn 返回 routing_hint（非 None）。"""
    result = capture_turn(
        "David 分享了跨产品线对齐优先级",
        session_id="sess-vs-001",
        actor_user_id="feishu:ou_test",
        hermes_home=tmp_path,
    )
    assert result is not None
    event_id, hint = result
    assert hint is not None
    assert "usage_hint" in hint


def test_insight_gap_scan_integrates_with_promotion(tmp_path):
    """InsightGapScan promote → PromotionDecision scope 是 knowledge_ops_candidate。"""
    scan_result = scan(
        previous="",
        current="用户在首次使用时需要引导，来源：A/B 测试报告",
        generalizable=True,
        confidence="high",
    )
    assert scan_result.decision == "promote"

    evt = _evt(
        recommended_destination="knowledge",
        risk_flags=["user_correction"],
    )
    promo = classify(evt)
    assert promo.scope == "knowledge_ops_candidate"
    assert promo.can_auto_promote is False


def test_promotion_decision_never_auto_writes_long_term(tmp_path, monkeypatch):
    """PromotionDecision 分类后不自动写入任何持久化存储。"""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    evt = _evt(risk_flags=["user_correction"])
    classify(evt)
    assert not (tmp_path / "memory_events").exists()
    assert not (tmp_path / "knowledge").exists()
    assert not (tmp_path / "MEMORY.md").exists()


# ─── Scenario SC1: 多轮深度思考 ──────────────────────────────────────────────

def test_sc1_multi_round_thinking_produces_delta_or_stops():
    """多轮思考：round2 新增证据 → new_insight；round3 充分证据 → stop。"""
    r1 = scan(previous="", current="留存率下降")
    assert r1.decision == "new_insight"

    r2 = scan(
        previous="留存率下降",
        current="留存率下降 3pp，来源：第3周报告 P12",
    )
    assert r2.decision == "new_insight"

    r3 = scan(
        previous="留存率下降 3pp，来源：第3周报告",
        current="留存率下降 3pp，A/B 测试验证，3 轮用户访谈确认，置信度 high",
        has_sufficient_evidence=True,
    )
    assert r3.decision == "stop"


# ─── Scenario SC2: 用户纠正专家层分权 ────────────────────────────────────────

def test_sc2_user_correction_routes_correctly(tmp_path):
    """用户纠正 + 无 scope → staging（待确认，不直接进 knowledge）。
    PromotionDecision 分类为 user_long_term_preference，can_auto_promote=False。
    """
    evt = _evt(
        risk_flags=["user_correction"],
        recommended_destination="personal_memory",
    )
    result = dispatch_event(evt, hermes_home=tmp_path)
    # Rule 4: user_correction + 无 scope → staging（需要 scope 确认后才能 promote）
    assert result.destination == DEST_STAGING

    promo = classify(evt)
    assert promo.scope == "user_long_term_preference"
    assert promo.can_auto_promote is False


# ─── Scenario SC3: 私聊 → staging（不进 knowledge）────────────────────────────

def test_sc3_private_chat_goes_to_staging_not_knowledge(tmp_path):
    """私聊内容路由到 staging，PromotionDecision 拒绝自动沉淀。"""
    evt = _evt(
        risk_flags=["private_chat"],
        recommended_destination="knowledge",
    )
    result = dispatch_event(evt, hermes_home=tmp_path)
    assert result.destination == DEST_STAGING

    promo = classify(evt)
    assert promo.scope == "needs_human_review"
    assert promo.can_auto_promote is False


# ─── Scenario SC5: 私聊不搬运 ─────────────────────────────────────────────────

def test_sc5_private_verbatim_blocked(tmp_path):
    """私聊 + project_process → staging，不直接进 project_process。"""
    evt = _evt(
        risk_flags=["private_chat"],
        recommended_destination="project_process",
        project_hint="PBI_phase2",
    )
    result = dispatch_event(evt, hermes_home=tmp_path)
    assert result.destination == DEST_STAGING
    promo = classify(evt)
    assert promo.can_auto_promote is False
