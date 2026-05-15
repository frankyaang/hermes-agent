# agent/asset_router.py
"""Deterministic asset routing rules for knowledge sedimentation governance."""
from __future__ import annotations
from dataclasses import dataclass, field
from agent.knowledge_models import KnowledgeCandidate
from agent.scope_resolver import resolve_scope, ScopeType

_RAW_CHAT_SOURCES = frozenset({"raw_chat_log", "raw_transcript"})
_MEMORY_ASSET_CLASSES = frozenset({"user_pref", "user_preference", "personal_convention"})
_SKILL_ASSET_CLASSES = frozenset({"workflow", "playbook", "template", "procedure"})


@dataclass
class RoutingResult:
    routing_decision: str   # route_to_knowledge / route_to_memory / route_to_skill / pending / no_action
    canonical_scope: str
    scope_type: str
    routing_reason: str
    missing_fields: list[str] = field(default_factory=list)


def route_candidate(candidate: KnowledgeCandidate) -> RoutingResult:
    """Apply deterministic routing rules. Returns RoutingResult."""
    try:
        from agent import sedimentation_metrics
        sedimentation_metrics.increment("candidate_detected")
    except Exception:
        pass

    # Rule 0: Raw chat log → no_action
    if candidate.source_type in _RAW_CHAT_SOURCES:
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("no_action_with_reason")
        except Exception:
            pass
        return RoutingResult(
            routing_decision="no_action",
            canonical_scope="",
            scope_type=ScopeType.UNKNOWN,
            routing_reason="raw_chat_log not allowed for direct knowledge write",
        )

    # Rule 1: User preference → memory
    if (candidate.asset_class in _MEMORY_ASSET_CLASSES
            or candidate.candidate_type == "memory"):
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("routed_to_memory")
        except Exception:
            pass
        return RoutingResult(
            routing_decision="route_to_memory",
            canonical_scope="",
            scope_type="user_pref",
            routing_reason="user preference routes to memory tool",
        )

    # Rule 2: Workflow / playbook → skill
    if (candidate.asset_class in _SKILL_ASSET_CLASSES
            or candidate.candidate_type == "skill"):
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("routed_to_skill")
        except Exception:
            pass
        return RoutingResult(
            routing_decision="route_to_skill",
            canonical_scope="",
            scope_type="workflow",
            routing_reason="reusable workflow routes to skill_manage",
        )

    # Rule 3: Missing source_uri → pending
    if not candidate.source_uri:
        try:
            from agent import sedimentation_metrics
            sedimentation_metrics.increment("pending_created")
        except Exception:
            pass
        return RoutingResult(
            routing_decision="pending",
            canonical_scope="",
            scope_type=ScopeType.UNKNOWN,
            routing_reason="source_uri required for knowledge write",
            missing_fields=["source_uri"],
        )

    # Rule 4: Resolve scope via alias + ScopeType
    canonical_scope, scope_type = resolve_scope(
        candidate.target_scope, candidate.asset_class
    )

    # Rule 5: Route to knowledge (product_line, company, project all go here)
    try:
        from agent import sedimentation_metrics
        sedimentation_metrics.increment("routed_to_knowledge")
    except Exception:
        pass
    return RoutingResult(
        routing_decision="route_to_knowledge",
        canonical_scope=canonical_scope,
        scope_type=scope_type,
        routing_reason=f"knowledge fact → knowledge_write (scope: {canonical_scope})",
    )
