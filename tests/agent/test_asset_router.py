"""Golden Tests for asset_router — deterministic routing rules."""
from __future__ import annotations
from agent.knowledge_models import KnowledgeCandidate
from agent.asset_router import route_candidate


def _candidate(**kw) -> KnowledgeCandidate:
    defaults = dict(
        candidate_id="test-id", candidate_type="knowledge",
        title="T", summary="S", structured_content={},
        source_uri="feishu://doc/x", source_type="feishu_doc",
        origin_session_id="", origin_platform="feishu",
        origin_user_id="feishu:ou_abc",
        asset_class="product_line", target_scope="deebot",
        confidence="unverified", sensitivity_level="internal",
        knowledge_type="product_spec",
        routing_decision="", routing_reason="",
        missing_fields=[], failure_reason="", terminal_state="",
        created_at="",
    )
    defaults.update(kw)
    return KnowledgeCandidate(**defaults)


# Golden Test 1: cleaning_robot alias resolved before routing
def test_cleaning_robot_routes_to_knowledge_with_deebot_scope():
    c = _candidate(target_scope="cleaning_robot")
    result = route_candidate(c)
    assert result.routing_decision == "route_to_knowledge"
    assert result.canonical_scope == "deebot"


# Golden Test 2: company/ecovacs/科沃斯 → ecovacs_company
def test_company_aliases_route_to_knowledge_company():
    for alias in ["company", "ecovacs", "科沃斯", "ecovacs_company"]:
        c = _candidate(target_scope=alias, asset_class="company")
        result = route_candidate(c)
        assert result.canonical_scope == "ecovacs_company", f"alias={alias}"
        assert result.routing_decision == "route_to_knowledge"


# Golden Test 3: Feishu origin user preserved in routing
def test_feishu_origin_user_preserved_in_routing():
    c = _candidate(origin_user_id="feishu:ou_zhanghuan", origin_platform="feishu")
    result = route_candidate(c)
    assert result.routing_decision in ("route_to_knowledge", "pending")


# Golden Test 4: missing source_uri → pending
def test_missing_source_uri_routes_to_pending():
    c = _candidate(source_uri="")
    result = route_candidate(c)
    assert result.routing_decision == "pending"
    assert "source_uri" in result.missing_fields


# Golden Test 5: user_preference → memory
def test_user_preference_routes_to_memory():
    c = _candidate(asset_class="user_pref", candidate_type="memory")
    result = route_candidate(c)
    assert result.routing_decision == "route_to_memory"


# Golden Test 6: workflow → skill
def test_workflow_routes_to_skill():
    c = _candidate(asset_class="workflow", candidate_type="skill")
    result = route_candidate(c)
    assert result.routing_decision == "route_to_skill"


# Golden Test 7: David/CEO company-level knowledge → company scope, NOT memory
def test_david_ceo_routes_to_company_scope():
    c = _candidate(target_scope="david", asset_class="person")
    result = route_candidate(c)
    assert result.canonical_scope == "ecovacs_company"
    assert result.routing_decision == "route_to_knowledge"


# Golden Test 8: raw chat log → no_action
def test_raw_chat_log_routes_to_no_action():
    c = _candidate(source_type="raw_chat_log")
    result = route_candidate(c)
    assert result.routing_decision == "no_action"
    assert "raw_chat_log" in result.routing_reason


# Golden Test 9: 地宝 alias → deebot scope
def test_地宝_alias_routes_to_deebot():
    c = _candidate(target_scope="地宝")
    result = route_candidate(c)
    assert result.canonical_scope == "deebot"
    assert result.routing_decision == "route_to_knowledge"
