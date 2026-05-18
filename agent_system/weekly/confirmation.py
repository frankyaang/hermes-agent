"""
Platform-neutral confirmation event schema + Feishu reply adapter.

make_confirmation_event() — create ConfirmationEvent (test mock / CLI)
parse_feishu_reply()       — pure function: Feishu reply text → ConfirmationEvent
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .models import ConfirmationEvent

_CONFIRM_KEYWORDS = frozenset({"confirm", "confirmed", "yes", "approve", "ok", "好的", "确认", "同意"})
_REJECT_KEYWORDS = frozenset({"reject", "rejected", "no", "deny", "拒绝", "否"})
_INCOMPLETE_KEYWORDS = frozenset({"incomplete", "missing", "need more", "补充", "需要"})


def make_confirmation_event(
    issue_id: str,
    decision: str,
    owner_id: str,
    channel: str = "test_mock",
    payload: dict | None = None,
) -> ConfirmationEvent:
    """Create a ConfirmationEvent — platform-neutral factory."""
    allowed = {"confirmed", "rejected", "incomplete"}
    if decision not in allowed:
        raise ValueError(f"decision must be one of {allowed}, got {decision!r}")
    return ConfirmationEvent(
        issue_id=issue_id,
        decision=decision,  # type: ignore[arg-type]
        owner_id=owner_id,
        channel=channel,
        payload=payload or {},
        received_at=datetime.now(timezone.utc).isoformat(),
    )


def parse_feishu_reply(
    issue_id: str,
    owner_id: str,
    reply_text: str,
    raw_payload: dict[str, Any] | None = None,
) -> ConfirmationEvent:
    """
    Parse a Feishu reply message into a ConfirmationEvent.

    Pure function — no network calls, no side effects.
    Detects: confirmed / rejected / incomplete from keyword matching.
    Falls back to "incomplete" if ambiguous.
    """
    normalized = reply_text.strip().lower()

    if any(kw in normalized for kw in _CONFIRM_KEYWORDS):
        decision = "confirmed"
    elif any(kw in normalized for kw in _REJECT_KEYWORDS):
        decision = "rejected"
    else:
        decision = "incomplete"

    return ConfirmationEvent(
        issue_id=issue_id,
        decision=decision,  # type: ignore[arg-type]
        owner_id=owner_id,
        channel="feishu",
        payload={"raw_text": reply_text, **(raw_payload or {})},
        received_at=datetime.now(timezone.utc).isoformat(),
    )
