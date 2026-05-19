"""
平台中立 weekly confirmation 入口。

handle_weekly_confirmation_payload(payload, issue_lookup, store) 供各平台调用：
  - type != "weekly_confirmation" → None（安全忽略）
  - issue_id 缺失 → None
  - issue 不在 issue_lookup → None
  - fake_closure_detected route → None（拦截，不写 ledger）
  - 否则 → store.apply_event(event, issue) 返回 contract
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_system.schemas.weekly_schemas import ExecutionContract, Issue
    from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore

logger = logging.getLogger(__name__)


def handle_weekly_confirmation_payload(
    payload: dict,
    issue_lookup: "dict[str, Issue]",
    store: "WeeklyLedgerStore",
) -> "ExecutionContract | None":
    """
    处理 weekly confirmation payload，返回 ExecutionContract 或 None。

    payload["action"]["value"]["type"] 必须为 "weekly_confirmation"，否则返回 None。
    """
    try:
        value = (payload.get("action") or {}).get("value") or {}
        if not isinstance(value, dict):
            return None
        if value.get("type") != "weekly_confirmation":
            return None

        issue_id = value.get("issue_id")
        if not issue_id:
            return None

        issue = issue_lookup.get(issue_id)
        if issue is None:
            logger.warning("weekly_confirmation: issue_id=%s not found in lookup", issue_id)
            return None

        # 检查是否 fake_closure
        from agent_system.evaluators.decision_gate import route_issue
        route = route_issue(issue)
        if route == "fake_closure_detected":
            logger.info("weekly_confirmation: fake_closure intercepted for issue_id=%s", issue_id)
            return None

        from agent_system.adapters.feishu_confirmation import parse_feishu_confirmation
        event = parse_feishu_confirmation(payload)
        if event is None:
            return None

        # 使用 payload 中的 event_id（如有），覆盖 parse 生成的随机 id
        explicit_event_id = value.get("event_id")
        if explicit_event_id:
            event.event_id = str(explicit_event_id)

        return store.apply_event(event, issue, route=route)

    except Exception as exc:
        logger.warning("handle_weekly_confirmation_payload failed: %s", exc)
        return None
