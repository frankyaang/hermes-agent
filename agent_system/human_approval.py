from __future__ import annotations

from typing import Any, Callable


ApprovalCallback = Callable[[str, list[str] | None], str | None]

APPROVAL_CHOICES = ["同意继续", "阻塞并补充资料", "退回复核", "确认可交付"]
BLOCKING_KEYWORDS = ("阻塞", "退回", "拒绝", "暂停", "补充资料", "不可交付", "不通过")
APPROVAL_KEYWORDS = ("同意", "继续", "确认", "可交付", "通过", "批准")


class AgentSystemApprovalUI:
    """Structured human approval adapter for agent_system user_gate nodes.

    The UI layer is independent from the runtime: it owns the approval prompt,
    choices, and decision normalization.  It can be backed by CLI, TUI, or
    Gateway callbacks without making the DAG runner know platform details.
    """

    channel = "agent_system_approval_ui"

    def __init__(self, callback: ApprovalCallback | None) -> None:
        self.callback = callback

    @property
    def available(self) -> bool:
        return self.callback is not None

    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.callback is None:
            return normalize_approval_response(
                None,
                channel="unavailable",
            )
        question = self._format_question(request)
        try:
            response = self.callback(question, APPROVAL_CHOICES)
        except Exception as exc:
            return normalize_approval_response(
                f"人工审批 UI 调用失败：{exc}",
                channel=self.channel,
                force_blocking=True,
            )
        return normalize_approval_response(response, channel=self.channel)

    @staticmethod
    def _format_question(request: dict[str, Any]) -> str:
        exceptions = request.get("exceptions") or []
        exception_text = "、".join(
            str(item.get("event") or item.get("audit_field") or "unknown")
            for item in exceptions
            if isinstance(item, dict)
        )
        return (
            "Hermes Agent System 人工审批\n"
            f"Pipeline：{request.get('pipeline_id')}\n"
            f"节点：{request.get('display_name')} ({request.get('node_id')})\n"
            f"异常：{exception_text or '无阻塞异常，仅需要用户确认'}\n"
            "请选择审批动作，或输入补充说明。"
        )


def normalize_approval_response(
    response: Any,
    *,
    channel: str = "manual_input",
    force_blocking: bool = False,
) -> dict[str, Any]:
    if isinstance(response, dict):
        summary = str(response.get("summary") or response.get("human_input_summary") or "").strip()
        decision = str(response.get("decision") or "").strip().lower()
        if not summary and response.get("raw_response") is not None:
            summary = str(response.get("raw_response")).strip()
        if decision in {"approved", "approve", "continue", "deliverable"}:
            normalized_decision = "approved"
        elif decision in {"blocked", "block", "rework", "rejected", "reject"}:
            normalized_decision = "blocked"
        else:
            normalized_decision = _decision_from_text(summary)
    else:
        summary = str(response or "").strip()
        normalized_decision = _decision_from_text(summary)

    if force_blocking:
        normalized_decision = "blocked"
    if not summary:
        normalized_decision = "missing"

    blocking = normalized_decision in {"blocked", "missing"}
    approved = normalized_decision == "approved"
    return {
        "decision": normalized_decision,
        "approved": approved,
        "blocking": blocking,
        "summary": summary,
        "raw_response": response,
        "channel": channel,
    }


def _decision_from_text(text: str) -> str:
    if not text:
        return "missing"
    if any(keyword in text for keyword in BLOCKING_KEYWORDS):
        return "blocked"
    if any(keyword in text for keyword in APPROVAL_KEYWORDS):
        return "approved"
    return "approved"
