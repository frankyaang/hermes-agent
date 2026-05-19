"""PromotionDecision — 9-scope 沉淀分类器。

只做分类，不执行任何写入。
没有明确 scope 判断依据时，返回 needs_human_review。

9 个 scope：
  current_session_rule     — 当前会话内临时规则
  session_boundary         — 会话结束时的边界归档
  user_long_term_preference — 用户长期偏好（user_correction + personal_memory）
  project_experience       — 项目经验（project_hint 清晰 + project_process）
  expert_pattern           — 专家层模式（experience_card dest）
  skill_usage_hint         — Skill 使用提示（source_type=tool_result + usage_hint 关键词）
  knowledge_ops_candidate  — KnowledgeOps 候选（knowledge dest）
  rejected_temp            — 被拒绝的临时笔记（write_failure / tool_failure）
  needs_human_review       — 条件不足，需人工确认（默认兜底）
"""
from __future__ import annotations

from dataclasses import dataclass

from agent.memory_event import MemoryEvent


@dataclass
class PromotionScope:
    scope: str          # 9 scopes 之一
    reason: str
    can_auto_promote: bool  # True: 可自动执行；False: 必须人工确认


def classify(
    event: MemoryEvent,
    *,
    session_ending: bool = False,
    session_rule_only: bool = False,
) -> PromotionScope:
    """对 MemoryEvent 做 PromotionDecision scope 分类。

    优先级（从高到低）：
      1. write_failure / tool_failure → rejected_temp
      2. private_chat / identity_missing → needs_human_review
      3. session_rule_only=True → current_session_rule
      4. session_ending=True → session_boundary
      5. experience_card dest → expert_pattern
      6. knowledge dest → knowledge_ops_candidate
      7. project_process dest + project_hint → project_experience
      8. user_correction + personal_memory → user_long_term_preference
      9. tool_result + usage_hint 关键词 → skill_usage_hint
      10. 其他 → needs_human_review
    """
    flags = set(event.risk_flags or [])
    dest = (event.recommended_destination or "").strip()
    source_type = (event.source_type or "").strip()

    # 1. 写入失败 / 工具失败 → 被拒绝的临时记录
    if source_type == "write_failure" or "tool_failure" in flags:
        return PromotionScope(
            scope="rejected_temp",
            reason="来源为写入失败或工具失败，不应升级为正式知识",
            can_auto_promote=False,
        )

    # 2. 私聊 / 身份不清 → 必须人工确认
    if "private_chat" in flags or "identity_missing" in flags:
        return PromotionScope(
            scope="needs_human_review",
            reason="私聊内容或身份不清，不允许自动沉淀",
            can_auto_promote=False,
        )

    # 3. 当前会话规则（session_rule_only 显式标记）
    if session_rule_only:
        return PromotionScope(
            scope="current_session_rule",
            reason="调用方标记为当前会话规则，可在会话内自动应用",
            can_auto_promote=True,
        )

    # 4. 会话边界归档
    if session_ending:
        return PromotionScope(
            scope="session_boundary",
            reason="会话结束边界，归档本次会话洞察",
            can_auto_promote=False,
        )

    # 5. ExperienceCard dest → 专家层模式
    if dest == "experience_card":
        return PromotionScope(
            scope="expert_pattern",
            reason="recommended_destination=experience_card，归类为专家层模式",
            can_auto_promote=False,
        )

    # 6. knowledge dest → KnowledgeOps 候选
    if dest == "knowledge":
        return PromotionScope(
            scope="knowledge_ops_candidate",
            reason="recommended_destination=knowledge，需经 KnowledgeOps 写入流程",
            can_auto_promote=False,
        )

    # 7. project_process + project_hint → 项目经验
    if dest == "project_process" and (event.project_hint or "").strip():
        return PromotionScope(
            scope="project_experience",
            reason=f"project_process + project_hint={event.project_hint}，归类为项目经验",
            can_auto_promote=False,
        )

    # 8. user_correction + personal_memory → 用户长期偏好
    if "user_correction" in flags and dest == "personal_memory":
        return PromotionScope(
            scope="user_long_term_preference",
            reason="user_correction + personal_memory，归类为用户长期偏好",
            can_auto_promote=False,
        )

    # 9. tool_result + usage_hint 关键词 → skill 使用提示
    if source_type == "tool_result" and "usage_hint" in (event.subject or "").lower():
        return PromotionScope(
            scope="skill_usage_hint",
            reason="tool_result 含 usage_hint 关键词，归类为 Skill 使用提示",
            can_auto_promote=True,
        )

    # 10. 兜底 → 需人工确认
    return PromotionScope(
        scope="needs_human_review",
        reason="无足够分类依据，归类为需人工确认",
        can_auto_promote=False,
    )
