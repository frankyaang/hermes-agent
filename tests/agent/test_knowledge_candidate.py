"""Tests for KnowledgeCandidate contract and TerminalState."""
from __future__ import annotations
from agent.knowledge_models import (
    KnowledgeCandidate, TerminalState, CandidateType,
)

def test_terminal_state_values():
    assert TerminalState.KNOWLEDGE_SAVED == "knowledge_saved"
    assert TerminalState.MEMORY_SAVED == "memory_saved"
    assert TerminalState.SKILL_SAVED_OR_UPDATED == "skill_saved_or_updated"
    assert TerminalState.PENDING_CREATED == "pending_created"
    assert TerminalState.NO_ACTION_WITH_REASON == "no_action_with_reason"
    assert TerminalState.BLOCKED == "blocked"

def test_candidate_type_values():
    assert CandidateType.KNOWLEDGE == "knowledge"
    assert CandidateType.MEMORY == "memory"
    assert CandidateType.SKILL == "skill"

def test_knowledge_candidate_required_fields():
    c = KnowledgeCandidate(
        candidate_id="abc-123",
        candidate_type=CandidateType.KNOWLEDGE,
        title="Test",
        summary="A test fact",
        structured_content={"body": "content"},
        source_uri="feishu://doc/abc",
        source_type="feishu_doc",
        origin_session_id="sess-1",
        origin_platform="feishu",
        origin_user_id="feishu:ou_abc",
        asset_class="product_line",
        target_scope="deebot",
        confidence="unverified",
        sensitivity_level="internal",
        knowledge_type="product_spec",
        routing_decision="route_to_knowledge",
        routing_reason="product-line fact",
        missing_fields=[],
        failure_reason="",
        terminal_state="",
        created_at="2026-05-15T00:00:00Z",
    )
    assert c.candidate_id == "abc-123"
    assert c.target_scope == "deebot"
    assert c.terminal_state == ""

def test_knowledge_candidate_defaults():
    c = KnowledgeCandidate(
        candidate_id="x", candidate_type=CandidateType.KNOWLEDGE,
        title="T", summary="S", structured_content={},
        source_uri="manual://", source_type="manual",
        origin_session_id="", origin_platform="", origin_user_id="",
        asset_class="", target_scope="",
        confidence="unverified", sensitivity_level="internal",
        knowledge_type="other",
        routing_decision="", routing_reason="",
        missing_fields=[], failure_reason="", terminal_state="", created_at="",
    )
    assert c.missing_fields == []
    assert c.terminal_state == ""
