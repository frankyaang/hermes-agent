from __future__ import annotations

from typing import Any


BUSINESS_DELEGATE_SKILLS = frozenset(
    {
        "voc_insight",
        "ops_dashboard",
        "dashboard_html",
        "audit",
        "briefing",
    }
)


BUSINESS_DELEGATE_OUTPUT_CONTRACT = (
    "structured delegate_task output containing artifact_path, main_report_path, "
    "result_summary, quality_flags"
)


def normalize_business_delegate_output(
    *,
    skill_id: str,
    output: dict[str, Any],
    completed: bool,
    main_report_path: str,
    child_status: str,
    api_calls: int,
    credential_status: str,
) -> dict[str, Any]:
    """Normalize business Skill delegate output to a stable contract.

    Business generation Skills can be authored by different child agents, so the
    parent runtime must receive the same shape every time. The contract is
    intentionally small and auditable; richer child output remains available in
    delegate_results.
    """
    normalized = dict(output)
    summary = str(normalized.get("result_summary") or "").strip()
    if not summary:
        summary = f"{skill_id} 已通过 delegate_task 执行" if completed else f"{skill_id} 执行失败"

    artifact_path = str(normalized.get("artifact_path") or main_report_path or "").strip()
    report_path = str(normalized.get("main_report_path") or main_report_path or artifact_path).strip()

    quality_flags = _coerce_quality_flags(normalized.get("quality_flags"))
    if completed:
        quality_flags.append("delegate_completed")
    else:
        quality_flags.append("delegate_failed")
    if artifact_path:
        quality_flags.append("artifact_path_present")
    else:
        quality_flags.append("artifact_path_missing")
    if api_calls > 0:
        quality_flags.append("online_llm_observed")
    else:
        quality_flags.append("online_llm_not_observed")
    if credential_status == "missing":
        quality_flags.append("credential_missing")
    if child_status and child_status not in {"completed", "success"}:
        quality_flags.append(f"delegate_status:{child_status}")

    normalized.update(
        {
            "artifact_path": artifact_path,
            "main_report_path": report_path,
            "result_summary": summary,
            "quality_flags": list(dict.fromkeys(quality_flags)),
        }
    )
    return normalized


def _coerce_quality_flags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
