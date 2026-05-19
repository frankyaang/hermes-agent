"""
Feishu card action payload → ConfirmationEvent 纯函数适配器。
无 LLM 调用，无副作用。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_system.schemas.weekly_schemas import ConfirmationEvent


def parse_feishu_confirmation(payload: dict) -> "ConfirmationEvent | None":
    """
    Pure function: Feishu card action payload → ConfirmationEvent。

    预期 payload 格式：
    {
        "action": {
            "value": {
                "issue_id": "...",
                "decision": "...",
                "execution_owner": "...",
                "committed_action": "...",
                "deadline": "...",
                "acceptance_criteria": "...",
                "verification_evidence": "..."
            }
        }
    }

    缺少 issue_id 时返回 None。其他字段允许为 None（导致 incomplete）。
    """
    from agent_system.schemas.weekly_schemas import ConfirmationEvent

    try:
        value = payload.get("action", {}).get("value", {})
        if not isinstance(value, dict):
            return None
        issue_id = value.get("issue_id")
        if not issue_id:
            return None
        return ConfirmationEvent(
            issue_id=str(issue_id),
            decision=str(value.get("decision") or ""),
            execution_owner=value.get("execution_owner") or None,
            committed_action=value.get("committed_action") or None,
            deadline=value.get("deadline") or None,
            acceptance_criteria=value.get("acceptance_criteria") or None,
            verification_evidence=value.get("verification_evidence") or None,
        )
    except Exception:
        return None
