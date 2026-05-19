"""gstack_bridge — gstack 输出 → 统一沉淀链，映射到专家层。

gstack 是 Hermes Agent System 的专家层支撑，不是第二大脑，不是共享内存。

路由规则（output_type → destination）：
  review       → audit/evidence only（记录但不进 expert_mem）
  fact         → KnowledgeCandidate payload → knowledge dispatcher（不直接写）
  lesson       → expert_mem candidate → dispatcher（不直接写 system_mem）
  playbook     → Skill asset（agent_system/experts/ 下的结构化资产）
  action_rule  → ExperienceCard candidate
  uncertain    → staging(needs_project_mapping)

feature flag: GSTACK_SEDIMENTATION_ENABLED（默认 false）
所有生产路径必须先检查此 flag。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

GstackOutputType = Literal["review", "fact", "lesson", "playbook", "action_rule", "uncertain"]

# gstack 永不直接写的目标
_FORBIDDEN_DIRECT_DESTINATIONS = {"system_mem", "expert_mem", "skill_mem"}


@dataclass
class BridgeResult:
    output_type: str
    destination: str
    event_id: str
    staging_id: str
    reason: str
    skipped: bool = False


def route(
    output: str,
    output_type: GstackOutputType,
    *,
    source_uri: str = "",
    actor_id: str = "gstack",
    project_hint: str = "",
    hermes_home: Path | None = None,
) -> BridgeResult:
    """将 gstack output 路由到对应沉淀目标。

    当 GSTACK_SEDIMENTATION_ENABLED=false 时，直接返回 skipped=True（no-op）。
    """
    from agent_system.sedimentation.feature_flags import GSTACK_SEDIMENTATION_ENABLED

    if not GSTACK_SEDIMENTATION_ENABLED:
        logger.debug("gstack_bridge: GSTACK_SEDIMENTATION_ENABLED=false, skipping")
        return BridgeResult(
            output_type=output_type,
            destination="noop",
            event_id="",
            staging_id="",
            reason="feature_flag_disabled",
            skipped=True,
        )

    from agent.memory_event import create_event, write_event

    if output_type == "review":
        return _route_review(output, source_uri, actor_id, project_hint, hermes_home)

    if output_type == "fact":
        return _route_fact(output, source_uri, actor_id, project_hint, hermes_home)

    if output_type == "lesson":
        return _route_lesson(output, source_uri, actor_id, project_hint, hermes_home)

    if output_type == "playbook":
        return _route_playbook(output, source_uri, actor_id, project_hint, hermes_home)

    if output_type == "action_rule":
        return _route_action_rule(output, source_uri, actor_id, project_hint, hermes_home)

    # uncertain → staging
    return _route_uncertain(output, source_uri, actor_id, project_hint, hermes_home)


def _make_event(
    output: str,
    source_uri: str,
    actor_id: str,
    project_hint: str,
    risk_flags: list[str],
    recommended_destination: str,
    hermes_home: Path | None,
) -> str:
    from agent.memory_event import create_event, write_event
    evt = create_event(
        source_type="tool_result",
        source_uri=source_uri or f"hermes://gstack/{actor_id}",
        actor_user_id=actor_id,
        subject=output[:120].strip(),
        risk_flags=risk_flags,
        recommended_destination=recommended_destination,
        project_hint=project_hint,
    )
    write_event(evt, hermes_home=hermes_home)
    return evt.id


def _route_review(output, source_uri, actor_id, project_hint, hermes_home) -> BridgeResult:
    """review → audit/evidence only，不进 expert_mem。"""
    event_id = _make_event(
        output, source_uri, actor_id, project_hint,
        risk_flags=["permission_unclear"],
        recommended_destination="staging",
        hermes_home=hermes_home,
    )
    logger.info("gstack_bridge: review → audit record (event_id=%s)", event_id)
    return BridgeResult(
        output_type="review",
        destination="audit_evidence",
        event_id=event_id,
        staging_id="",
        reason="gstack_review_goes_to_audit_only",
    )


def _route_fact(output, source_uri, actor_id, project_hint, hermes_home) -> BridgeResult:
    """fact → KnowledgeCandidate payload → knowledge dispatcher（不直接写）。"""
    event_id = _make_event(
        output, source_uri, actor_id, project_hint,
        risk_flags=[],
        recommended_destination="knowledge",
        hermes_home=hermes_home,
    )
    logger.info("gstack_bridge: fact → knowledge candidate (event_id=%s)", event_id)
    return BridgeResult(
        output_type="fact",
        destination="knowledge_candidate",
        event_id=event_id,
        staging_id="",
        reason="gstack_fact_as_knowledge_candidate",
    )


def _route_lesson(output, source_uri, actor_id, project_hint, hermes_home) -> BridgeResult:
    """lesson → expert_mem candidate（不直接写 system_mem）。"""
    event_id = _make_event(
        output, source_uri, actor_id, project_hint,
        risk_flags=["permission_unclear"],
        recommended_destination="experience_card",
        hermes_home=hermes_home,
    )
    logger.info("gstack_bridge: lesson → expert_mem candidate (event_id=%s)", event_id)
    return BridgeResult(
        output_type="lesson",
        destination="expert_mem_candidate",
        event_id=event_id,
        staging_id="",
        reason="gstack_lesson_as_expert_mem_candidate",
    )


def _route_playbook(output, source_uri, actor_id, project_hint, hermes_home) -> BridgeResult:
    """playbook → Skill asset（agent_system/experts/ 结构化资产）。"""
    event_id = _make_event(
        output, source_uri, actor_id, project_hint,
        risk_flags=[],
        recommended_destination="experience_card",
        hermes_home=hermes_home,
    )
    logger.info("gstack_bridge: playbook → skill_asset (event_id=%s)", event_id)
    return BridgeResult(
        output_type="playbook",
        destination="skill_asset",
        event_id=event_id,
        staging_id="",
        reason="gstack_playbook_becomes_skill_asset",
    )


def _route_action_rule(output, source_uri, actor_id, project_hint, hermes_home) -> BridgeResult:
    """action_rule → ExperienceCard candidate。"""
    event_id = _make_event(
        output, source_uri, actor_id, project_hint,
        risk_flags=[],
        recommended_destination="experience_card",
        hermes_home=hermes_home,
    )
    logger.info("gstack_bridge: action_rule → experience_card candidate (event_id=%s)", event_id)
    return BridgeResult(
        output_type="action_rule",
        destination="experience_card_candidate",
        event_id=event_id,
        staging_id="",
        reason="gstack_action_rule_as_experience_card",
    )


def _route_uncertain(output, source_uri, actor_id, project_hint, hermes_home) -> BridgeResult:
    """uncertain → staging(needs_project_mapping)。"""
    from agent.staging_store import write_staging
    event_id = _make_event(
        output, source_uri, actor_id, project_hint,
        risk_flags=["project_uncertain", "permission_unclear"],
        recommended_destination="staging",
        hermes_home=hermes_home,
    )
    staging_id = write_staging(
        event_id=event_id,
        reason="gstack_output_uncertain",
        next_action="needs_project_mapping",
        source_uri=source_uri or f"hermes://gstack/{actor_id}",
        hermes_home=hermes_home,
    )
    return BridgeResult(
        output_type="uncertain",
        destination="staging",
        event_id=event_id,
        staging_id=staging_id,
        reason="gstack_uncertain_needs_project_mapping",
    )
