"""MemoryDispatcher — 分流器，将 MemoryEvent 路由到 5 个目标之一。

目标：
  personal_memory   — 用户偏好、私下判断、协作习惯
  project_process   — 当前版本、待确认项、下一步动作、项目变化
  knowledge         — 来源清楚、范围清楚、当前仍可复用
  experience_card   — 下次怎么查、怎么写、怎么确认、什么不能做
  staging           — 条件不足、归属不清、权限不清

分流规则（优先级从高到低）：
  1. identity_missing 或 project_uncertain → staging(needs_user_confirmation)
  2. private_chat + 无 project_hint → staging(wait_for_source)
  3. tool_failure → staging(retry_write) + tool_failure 关系记录
  4. user_correction + 无明确 scope → staging(needs_user_confirmation) + user_correction 关系
  5. permission_unclear 或 stale_version → staging(needs_project_mapping)
  6. source_type==user_correction + 有明确 scope → personal_memory
  7. recommended_destination==experience_card → experience_card
  8. recommended_destination==project_process → project_process
  9. recommended_destination==knowledge → knowledge
  10. 默认 → personal_memory
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from agent.memory_event import MemoryEvent, write_event
from agent.memory_relations import write_relation
from agent.staging_store import write_staging

logger = logging.getLogger(__name__)

# 分流目标常量
DEST_PERSONAL_MEMORY = "personal_memory"
DEST_PROJECT_PROCESS = "project_process"
DEST_KNOWLEDGE = "knowledge"
DEST_EXPERIENCE_CARD = "experience_card"
DEST_STAGING = "staging"

DESTINATIONS = {
    DEST_PERSONAL_MEMORY,
    DEST_PROJECT_PROCESS,
    DEST_KNOWLEDGE,
    DEST_EXPERIENCE_CARD,
    DEST_STAGING,
}


@dataclass
class DispatchResult:
    event_id: str
    destination: str            # DESTINATIONS 之一
    staging_id: str             # 非空当且仅当 destination==staging
    reason: str
    relation_ids: List[str] = field(default_factory=list)  # 写入的关系记录 id


def dispatch_event(
    event: MemoryEvent,
    *,
    hermes_home: Path | None = None,
    write_to_store: bool = True,
) -> DispatchResult:
    """分流 MemoryEvent 到 5 个目标之一。

    Args:
        event: 要分流的 MemoryEvent
        hermes_home: 覆盖默认的 HERMES_HOME（测试用）
        write_to_store: 是否实际写入文件（测试时可设为 False 做纯逻辑断言）

    Returns:
        DispatchResult，包含 destination、staging_id（如有）、reason、relation_ids
    """
    flags = set(event.risk_flags or [])
    dest_hint = (event.recommended_destination or "").strip()

    staging_id = ""
    relation_ids: list[str] = []
    reason = ""

    # ── 规则 1：身份不清 或 项目不清 ────────────────────────────────────────
    if "identity_missing" in flags or "project_uncertain" in flags:
        reason = "identity_missing_or_project_uncertain"
        if write_to_store:
            staging_id = write_staging(
                event_id=event.id,
                reason=reason,
                next_action="needs_user_confirmation",
                source_uri=event.source_uri,
                hermes_home=hermes_home,
            )
        return DispatchResult(
            event_id=event.id,
            destination=DEST_STAGING,
            staging_id=staging_id,
            reason=reason,
        )

    # ── 规则 2：私聊 ─────────────────────────────────────────────────────────
    # 2a：私聊 + recommended_destination=project_process → staging(needs_user_confirmation)
    #     私聊内容即使有明确 project_hint 也不能直接进 project_process，必须先人工确认
    # 2b：私聊 + 无 project_hint → staging(wait_for_source)
    if "private_chat" in flags:
        if dest_hint == DEST_PROJECT_PROCESS:
            reason = "private_chat_requires_confirmation_before_project_process"
            if write_to_store:
                staging_id = write_staging(
                    event_id=event.id,
                    reason=reason,
                    next_action="needs_user_confirmation",
                    source_uri=event.source_uri,
                    visibility_scope="private",
                    retrieval_scope="owner_only",
                    hermes_home=hermes_home,
                )
            return DispatchResult(
                event_id=event.id,
                destination=DEST_STAGING,
                staging_id=staging_id,
                reason=reason,
            )
        if not event.project_hint:
            reason = "private_chat_no_project_hint"
            if write_to_store:
                staging_id = write_staging(
                    event_id=event.id,
                    reason=reason,
                    next_action="wait_for_source",
                    source_uri=event.source_uri,
                    visibility_scope="private",
                    retrieval_scope="owner_only",
                    hermes_home=hermes_home,
                )
            return DispatchResult(
                event_id=event.id,
                destination=DEST_STAGING,
                staging_id=staging_id,
                reason=reason,
            )

    # ── 规则 3：工具写入失败 ─────────────────────────────────────────────────
    if "tool_failure" in flags:
        reason = "tool_failure_fallback"
        if write_to_store:
            staging_id = write_staging(
                event_id=event.id,
                reason=reason,
                next_action="retry_write",
                source_uri=event.source_uri,
                hermes_home=hermes_home,
            )
            rel_id = write_relation(
                relation_type="tool_failure",
                source_id=event.id,
                target_id=staging_id,
                note=f"写入失败后进入 staging，来源: {event.source_uri}",
                hermes_home=hermes_home,
            )
            relation_ids.append(rel_id)
        return DispatchResult(
            event_id=event.id,
            destination=DEST_STAGING,
            staging_id=staging_id,
            reason=reason,
            relation_ids=relation_ids,
        )

    # ── 规则 4：用户纠正 + 无明确 scope ──────────────────────────────────────
    if "user_correction" in flags and not event.project_hint and not event.product_line_hint:
        reason = "user_correction_scope_unclear"
        if write_to_store:
            staging_id = write_staging(
                event_id=event.id,
                reason=reason,
                next_action="needs_user_confirmation",
                source_uri=event.source_uri,
                hermes_home=hermes_home,
            )
            rel_id = write_relation(
                relation_type="user_correction",
                source_id=event.id,
                target_id=staging_id,
                note="用户纠正，影响范围待确认",
                hermes_home=hermes_home,
            )
            relation_ids.append(rel_id)
        return DispatchResult(
            event_id=event.id,
            destination=DEST_STAGING,
            staging_id=staging_id,
            reason=reason,
            relation_ids=relation_ids,
        )

    # ── 规则 5：权限不清 或 旧版本 ───────────────────────────────────────────
    if "permission_unclear" in flags or "stale_version" in flags:
        reason = "permission_unclear_or_stale_version"
        if write_to_store:
            staging_id = write_staging(
                event_id=event.id,
                reason=reason,
                next_action="needs_project_mapping",
                source_uri=event.source_uri,
                hermes_home=hermes_home,
            )
        return DispatchResult(
            event_id=event.id,
            destination=DEST_STAGING,
            staging_id=staging_id,
            reason=reason,
        )

    # ── 规则 6：用户纠正 + 有明确 scope → personal_memory ───────────────────
    if event.source_type == "user_correction" and (event.project_hint or event.product_line_hint):
        reason = "user_correction_with_scope"
        if write_to_store:
            rel_id = write_relation(
                relation_type="user_correction",
                source_id=event.id,
                target_id=event.project_hint or event.product_line_hint,
                note="用户纠正，已知范围，写入 personal_memory",
                hermes_home=hermes_home,
            )
            relation_ids.append(rel_id)
            # 写入 version_supersedes 关系：标记旧内容被当前纠正覆盖
            vs_id = write_relation(
                relation_type="version_supersedes",
                source_id=event.id,
                target_id=event.project_hint or event.product_line_hint,
                note=f"用户纠正覆盖旧版本内容，scope={event.project_hint or event.product_line_hint}",
                hermes_home=hermes_home,
            )
            relation_ids.append(vs_id)
        return DispatchResult(
            event_id=event.id,
            destination=DEST_PERSONAL_MEMORY,
            staging_id="",
            reason=reason,
            relation_ids=relation_ids,
        )

    # ── 规则 7-9：按 recommended_destination 路由 ────────────────────────────
    if dest_hint in (DEST_EXPERIENCE_CARD, DEST_PROJECT_PROCESS, DEST_KNOWLEDGE):
        if dest_hint == DEST_PROJECT_PROCESS and write_to_store:
            from agent.project_process_store import write_record as _write_pp_record
            _write_pp_record(
                event_id=event.id,
                subject=event.subject or "",
                project_hint=event.project_hint or "",
                source_uri=event.source_uri or "",
                actor_user_id=event.actor_user_id or "",
                hermes_home=hermes_home,
            )
        return DispatchResult(
            event_id=event.id,
            destination=dest_hint,
            staging_id="",
            reason=f"recommended_destination={dest_hint}",
        )

    # ── 规则 10：默认 → personal_memory ─────────────────────────────────────
    return DispatchResult(
        event_id=event.id,
        destination=DEST_PERSONAL_MEMORY,
        staging_id="",
        reason="default_personal_memory",
    )


def dispatch_tool_failure(
    title: str,
    source_uri: str,
    actor_user_id: str,
    session_id: str = "",
    product_line_hint: str = "",
    hermes_home: Path | None = None,
) -> DispatchResult:
    """knowledge_write permission_denied 后调用的便捷入口。

    生成 tool_failure MemoryEvent 并分流到 staging(retry_write)。
    """
    from agent.memory_event import create_event

    event = create_event(
        source_type="write_failure",
        source_uri=source_uri,
        actor_user_id=actor_user_id,
        subject=title,
        risk_flags=["tool_failure", "permission_unclear"],
        recommended_destination=DEST_STAGING,
        session_id=session_id,
        product_line_hint=product_line_hint,
    )
    write_event(event, hermes_home=hermes_home)
    return dispatch_event(event, hermes_home=hermes_home)
