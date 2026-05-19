"""
DecisionGate skill — pipeline node wrapper。

接收 issue_extractor 输出的 List[Issue] JSON，
调用 route_issues() 纯函数，输出路由表 JSON，
并将每条路由记录写入 audit.jsonl。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from agent_system.evaluators.decision_gate import route_issues
from agent_system.schemas.weekly_schemas import Issue

logger = logging.getLogger(__name__)

_AUDIT_PATH = Path(__file__).parents[3] / "agent_system" / "audit" / "audit.jsonl"


def run(issues_json: str, pipeline_run_id: str = "unknown") -> str:
    """
    Pipeline node entry point。

    Args:
        issues_json: JSON 字符串，表示 List[Issue]-like dict 列表
        pipeline_run_id: 当前 pipeline 运行 ID（用于 audit 追踪）

    Returns:
        JSON 字符串，格式：{"routes": {issue_id: route, ...}}
    """
    try:
        raw = json.loads(issues_json)
    except json.JSONDecodeError as e:
        logger.error("decision_gate: invalid JSON input: %s", e)
        return json.dumps({"routes": {}, "error": "invalid_json"})

    if not isinstance(raw, list):
        logger.error("decision_gate: expected list, got %s", type(raw))
        return json.dumps({"routes": {}, "error": "expected_list"})

    issues: list[Issue] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            issues.append(Issue(
                title=str(item.get("title", "")),
                background=str(item.get("background", "")),
                source_ref=str(item.get("source_ref", "weekly_unknown")),
                urgency=item.get("urgency", "medium"),
                options=item.get("options", []),
                recommended_option=item.get("recommended_option"),
                owner_candidate=item.get("owner_candidate"),
                acceptance_criteria=item.get("acceptance_criteria"),
                issue_id=item.get("issue_id", ""),
            ))
        except Exception as e:
            logger.warning("decision_gate: skipping malformed issue: %s", e)

    routes = route_issues(issues)

    _write_audit(routes, pipeline_run_id)

    logger.info(
        "decision_gate: routed %d issues: %s",
        len(routes),
        {k: v for k, v in routes.items()},
    )
    return json.dumps({"routes": routes})


def _write_audit(routes: dict[str, str], pipeline_run_id: str) -> None:
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        with _AUDIT_PATH.open("a", encoding="utf-8") as f:
            for issue_id, route in routes.items():
                record = {
                    "ts": ts,
                    "event": "decision_gate_route",
                    "pipeline_id": "weekly_flow",
                    "pipeline_run_id": pipeline_run_id,
                    "issue_id": issue_id,
                    "route": route,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("decision_gate: audit write failed: %s", e)
