"""usage_hint — 所有进入 Agent prompt 的历史内容的用法标注。

所有读回内容（memory、knowledge、project_process、experience_card、session_search）
必须携带 usage_hint，告知 Agent 该内容的可用范围和注意事项。

usage_hint 不进入 frozen system prompt snapshot（保护 prefix cache），
只附加在 Tool Result JSON 字段或动态注入段中。
"""
from __future__ import annotations

# 支持的 usage_hint 值
USAGE_HINTS = {
    "private_reference_only",       # 仅供私下参考，不可转发或写入项目材料
    "project_material_usable",      # 已确认可用于项目材料
    "old_version_background",       # 旧版本背景信息，仅供参考，勿直接引用
    "needs_source_check",           # 来源待确认，使用前需核实
    "do_not_forward_source",        # 内容可用但来源不可对外透露
    "action_rule_for_next_task",    # 下次执行的行动规则（来自 ExperienceCard）
}

# knowledge_type → usage_hint 的映射规则
_KNOWLEDGE_TYPE_HINTS: dict[str, str] = {
    "financial_report": "do_not_forward_source",
    "financial_kpi": "do_not_forward_source",
    "financial_forecast": "do_not_forward_source",
}

# confidence → usage_hint 的映射规则
_CONFIDENCE_HINTS: dict[str, str] = {
    "deprecated": "old_version_background",
    "draft": "needs_source_check",
}


def wrap_with_hint(content: str, hint: str) -> str:
    """在内容前追加用法提示行，不修改内容本身。"""
    if not content:
        return content
    return f"[usage_hint: {hint}]\n{content}"


def hint_for_knowledge(doc: dict) -> str:
    """根据 knowledge doc 的 confidence / knowledge_type 推断 usage_hint。"""
    confidence = (doc.get("confidence") or "").lower()
    if confidence in _CONFIDENCE_HINTS:
        return _CONFIDENCE_HINTS[confidence]
    knowledge_type = (doc.get("knowledge_type") or "").lower()
    if knowledge_type in _KNOWLEDGE_TYPE_HINTS:
        return _KNOWLEDGE_TYPE_HINTS[knowledge_type]
    return "project_material_usable"


def hint_for_session_search(_result: dict | None = None) -> str:
    """session_search 结果默认 needs_source_check（来源待确认）。"""
    return "needs_source_check"


def hint_for_experience_card(_card: dict | None = None) -> str:
    """ExperienceCard 内容标记为 action_rule_for_next_task。"""
    return "action_rule_for_next_task"


def hint_for_staging(_entry: dict | None = None) -> str:
    """Staging 内容默认 needs_source_check。"""
    return "needs_source_check"


def hint_for_project_process(_entry: dict | None = None) -> str:
    """project_process 内容默认 project_material_usable。"""
    return "project_material_usable"
