"""Vertical slice for knowledge sedimentation governance.

This covers the real in-process chain up to the provider boundary:
Feishu identity -> scope/routing -> knowledge_write ACL denial -> pending
capture -> permission repair -> replay -> terminal_state + metrics.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import yaml

from agent import sedimentation_metrics
from agent.asset_router import route_candidate
from agent.identity_resolver import resolve_identity
from agent.knowledge_models import KnowledgeCandidate
from agent.pending_capture import read_pending, replay_pending
from gateway.session_context import clear_session_vars, set_session_vars
from tools import knowledge_tool


def _write_registry(home, product_line_ids):
    registry_dir = home / "knowledge"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "users.yaml").write_text(
        yaml.safe_dump(
            {
                "users": [
                    {
                        "user_id": "feishu:ou_david_case",
                        "display_name": "David case owner",
                        "product_line_ids": product_line_ids,
                        "default_product_line_id": product_line_ids[0],
                        "finance_product_line_ids": [],
                        "role": "business_user",
                        "is_admin": False,
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def _mock_provider(monkeypatch):
    provider = MagicMock()
    provider.write.return_value = "david-company-value"
    provider.query.return_value = []
    monkeypatch.setattr(
        "plugins.knowledge.gbrain.provider.GBrainCLIKnowledgeProvider",
        lambda: provider,
    )
    return provider


def test_feishu_company_knowledge_pending_then_replay_vertical_slice(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    _write_registry(home, ["deebot"])
    monkeypatch.setenv("HERMES_HOME", str(home))
    provider = _mock_provider(monkeypatch)
    knowledge_tool._MANAGER_CACHE.clear()
    sedimentation_metrics.reset()

    tokens = set_session_vars(
        platform="feishu",
        user_id="ou_david_case",
        chat_id="oc_company_knowledge",
    )
    try:
        identity = resolve_identity()
        assert identity.user_id == "feishu:ou_david_case"

        candidate = KnowledgeCandidate(
            candidate_id="cand-david",
            candidate_type="knowledge",
            title="David company-level communication preference",
            summary="David prefers conclusion-first updates with explicit decision requests.",
            structured_content={
                "content": "David prefers conclusion-first updates with explicit decision requests.",
                "knowledge_type": "org_info",
            },
            source_uri="hermes://session/session-david",
            source_type="session",
            origin_session_id="session-david",
            origin_platform="feishu",
            origin_user_id=identity.user_id,
            asset_class="person",
            target_scope="david",
            confidence="unverified",
            sensitivity_level="internal",
            knowledge_type="org_info",
            routing_decision="",
            routing_reason="",
        )

        routing = route_candidate(candidate)
        assert routing.routing_decision == "route_to_knowledge"
        assert routing.canonical_scope == "ecovacs_company"

        denied = json.loads(
            knowledge_tool._knowledge_write(
                title=candidate.title,
                content=candidate.summary,
                product_line_id=routing.canonical_scope,
                knowledge_type=candidate.knowledge_type,
                source_uri=candidate.source_uri,
                finance_flag=False,
                sensitivity_level=candidate.sensitivity_level,
                confidence=candidate.confidence,
                doc_slug="",
                task_id="session-david",
            )
        )
        assert denied["error"] == "permission_denied"
        capture_id = denied["pending_capture_id"]

        pending = read_pending(capture_id, hermes_home=home)
        assert pending is not None
        assert pending["scope_id"] == "ecovacs_company"
        assert pending["terminal_state"] == "pending_created"

        _write_registry(home, ["deebot", "ecovacs_company"])
        knowledge_tool._MANAGER_CACHE.clear()

        replayed = replay_pending(capture_id, hermes_home=home)
        assert replayed["status"] == "replayed"
        final = read_pending(capture_id, hermes_home=home)
        assert final["terminal_state"] == "knowledge_saved"
        provider.write.assert_called_once()

        metrics = sedimentation_metrics.snapshot()
        assert metrics["candidate_detected"] >= 1
        assert metrics["routed_to_knowledge"] >= 1
        assert metrics["pending_created"] >= 1
        assert metrics["knowledge_write_failed"] >= 1
        assert metrics["knowledge_write_success"] >= 1
        assert metrics["replay_success"] >= 1
    finally:
        clear_session_vars(tokens)
        knowledge_tool._MANAGER_CACHE.clear()
        sedimentation_metrics.reset()
