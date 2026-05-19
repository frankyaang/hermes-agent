"""usage_hint — 所有进入 Agent prompt 的历史内容的用法标注。

所有读回内容（memory、knowledge、project_process、experience_card、session_search）
必须携带 usage_hint，告知 Agent 该内容的可用范围和注意事项。

usage_hint 不进入 frozen system prompt snapshot（保护 prefix cache），
只附加在 Tool Result JSON 字段或动态注入段中。
"""
from __future__ import annotations

USAGE_HINTS = {
    "private_reference_only",
    "project_material_usable",
    "old_version_background",
    "needs_source_check",
    "do_not_forward_source",
    "action_rule_for_next_task",
}

_KNOWLEDGE_TYPE_HINTS: dict[str, str] = {
    "financial_report": "do_not_forward_source",
    "financial_kpi": "do_not_forward_source",
    "financial_forecast": "do_not_forward_source",
}

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
    confidence = (doc.get("confidence") or "").lower()
    if confidence in _CONFIDENCE_HINTS:
        return _CONFIDENCE_HINTS[confidence]
    knowledge_type = (doc.get("knowledge_type") or "").lower()
    if knowledge_type in _KNOWLEDGE_TYPE_HINTS:
        return _KNOWLEDGE_TYPE_HINTS[knowledge_type]
    return "project_material_usable"


def hint_for_session_search(_result: dict | None = None) -> str:
    return "needs_source_check"


def hint_for_experience_card(_card: dict | None = None) -> str:
    return "action_rule_for_next_task"


def hint_for_staging(_entry: dict | None = None) -> str:
    return "needs_source_check"


def hint_for_project_process(_entry: dict | None = None) -> str:
    return "project_material_usable"
