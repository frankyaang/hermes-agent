"""三层经验写入 ACL — system_mem / expert_mem / skill_mem 隔离。

写入规则：
  system_mem:  仅 caller_id="hermes_main" 可写；gstack 任何输出均禁止直接写
  expert_mem:  仅 caller_id 与 expert_id 匹配可写；gstack lesson → candidate，须经 dispatcher
  skill_mem:   仅 caller_id 与 skill_id 匹配可写；gstack playbook → Skill asset，须经 experience_layer

任何违反 ACL 的写入尝试均返回 AccessDenied，内容进入 staging。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Layer = Literal["system_mem", "expert_mem", "skill_mem"]

GSTACK_CALLER_IDS = {"gstack", "gstack_control", "gstack_bridge"}
HERMES_MAIN_CALLER_ID = "hermes_main"


@dataclass
class WriteResult:
    success: bool
    layer: str
    caller_id: str
    reason: str
    staging_id: str = ""


def write_to_layer(
    layer: Layer,
    content: str,
    caller_id: str,
    *,
    expert_id: str = "",
    skill_id: str = "",
    hermes_home: Path | None = None,
) -> WriteResult:
    """写入三层经验之一，执行 ACL 检查。

    Returns WriteResult(success=False) + 进入 staging 若 ACL 拒绝。
    """
    # system_mem: 仅 hermes_main 可写
    if layer == "system_mem":
        if caller_id != HERMES_MAIN_CALLER_ID:
            reason = f"system_mem_acl_denied: caller={caller_id!r} must be hermes_main"
            logger.warning("experience_layer: %s", reason)
            staging_id = _route_to_staging(content, reason, caller_id, hermes_home)
            return WriteResult(success=False, layer=layer, caller_id=caller_id, reason=reason, staging_id=staging_id)

    # expert_mem: 仅对应 expert 自身
    elif layer == "expert_mem":
        if caller_id in GSTACK_CALLER_IDS:
            reason = f"expert_mem_acl_denied: gstack cannot write directly, use candidate"
            logger.warning("experience_layer: %s", reason)
            staging_id = _route_to_staging(content, reason, caller_id, hermes_home)
            return WriteResult(success=False, layer=layer, caller_id=caller_id, reason=reason, staging_id=staging_id)
        if expert_id and caller_id != expert_id:
            reason = f"expert_mem_acl_denied: caller={caller_id!r} != expert={expert_id!r}"
            logger.warning("experience_layer: %s", reason)
            staging_id = _route_to_staging(content, reason, caller_id, hermes_home)
            return WriteResult(success=False, layer=layer, caller_id=caller_id, reason=reason, staging_id=staging_id)

    # skill_mem: 仅对应 skill 自身
    elif layer == "skill_mem":
        if caller_id in GSTACK_CALLER_IDS:
            reason = f"skill_mem_acl_denied: gstack cannot write directly, use skill_asset"
            logger.warning("experience_layer: %s", reason)
            staging_id = _route_to_staging(content, reason, caller_id, hermes_home)
            return WriteResult(success=False, layer=layer, caller_id=caller_id, reason=reason, staging_id=staging_id)
        if skill_id and caller_id != skill_id:
            reason = f"skill_mem_acl_denied: caller={caller_id!r} != skill={skill_id!r}"
            logger.warning("experience_layer: %s", reason)
            staging_id = _route_to_staging(content, reason, caller_id, hermes_home)
            return WriteResult(success=False, layer=layer, caller_id=caller_id, reason=reason, staging_id=staging_id)

    logger.info("experience_layer: write approved layer=%s caller=%s", layer, caller_id)
    return WriteResult(success=True, layer=layer, caller_id=caller_id, reason="acl_passed")


def _route_to_staging(
    content: str,
    reason: str,
    caller_id: str,
    hermes_home: Path | None,
) -> str:
    try:
        from agent.memory_event import create_event, write_event
        from agent.staging_store import write_staging

        evt = create_event(
            source_type="tool_result",
            source_uri=f"hermes://experience_layer/{caller_id}",
            actor_user_id=caller_id,
            subject=reason[:120],
            risk_flags=["permission_unclear"],
            recommended_destination="staging",
        )
        write_event(evt, hermes_home=hermes_home)
        return write_staging(
            event_id=evt.id,
            reason=reason,
            next_action="archive_as_reference",
            source_uri=f"hermes://experience_layer/{caller_id}",
            raw_content=content[:500],
            hermes_home=hermes_home,
        )
    except Exception as exc:
        logger.warning("experience_layer._route_to_staging failed: %s", exc)
        return ""
