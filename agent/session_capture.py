"""会话记忆捕获入口 — 从 run_agent.py 消息处理后自动调用。

触发条件（满足任一即创建 MemoryEvent 并写入 JSONL）：
  - 用户消息含用户纠正关键词 → risk_flags=["user_correction"]
  - 用户消息含 ExperienceCard 触发词（如"David"）→ risk_flags=["identity_missing"]

不在每轮强制触发，只在检测到 risk pattern 时创建事件。
never raises — 所有失败均静默。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

from agent.memory_event import create_event, write_event

logger = logging.getLogger(__name__)

_CORRECTION_PATTERNS: List[str] = [
    r"不要用",
    r"请不要用",
    r"别用",
    r"不该用",
    r"不用这个词",
]


def _extract_text(message: object) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for item in message:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(filter(None, parts))
    return str(message) if message else ""


def _detect_risk_flags(text: str) -> List[str]:
    flags: List[str] = []
    for pattern in _CORRECTION_PATTERNS:
        if re.search(pattern, text):
            flags.append("user_correction")
            break
    try:
        from agent.experience_card import trigger_check
        if trigger_check(text) is not None:
            flags.append("identity_missing")
    except Exception:
        pass
    return flags


def capture_turn(
    text: str,
    *,
    session_id: str = "",
    actor_user_id: str = "",
    platform: str = "",
    hermes_home: Optional[Path] = None,
) -> Optional[str]:
    """分析会话轮次文本，若检测到 risk pattern 则创建并持久化 MemoryEvent。

    返回 event_id（已创建）或 None（无 risk pattern 或写入失败）。never raises。
    """
    try:
        if not text or not text.strip():
            return None
        flags = _detect_risk_flags(text)
        if not flags:
            return None
        dest = "personal_memory" if "user_correction" in flags else "staging"
        evt = create_event(
            source_type="session",
            source_uri=f"hermes://session/{session_id}" if session_id else "hermes://session/unknown",
            actor_user_id=actor_user_id or "unknown",
            subject=text[:120].strip(),
            risk_flags=flags,
            recommended_destination=dest,
            session_id=session_id,
        )
        return write_event(evt, hermes_home=hermes_home)
    except Exception as exc:
        logger.debug("capture_turn failed (non-fatal): %s", exc)
        return None
