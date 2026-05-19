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

from agent.experience_card import render_card as _render_card
from agent.experience_card import trigger_check as _ec_trigger_check
from agent.memory_event import create_event, write_event

logger = logging.getLogger(__name__)

# 用户纠正关键词模式（中文）
_CORRECTION_PATTERNS: List[str] = [
    r"不要用",
    r"请不要用",
    r"别用",
    r"不该用",
    r"不用这个词",
]


def _extract_text(message: object) -> str:
    """从 message 对象提取纯文本（兼容 str、list[dict] 两种格式）。"""
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
    """检测 text 中的 risk pattern，返回 risk_flags 列表（不重复）。"""
    flags: List[str] = []
    # 用户纠正模式
    for pattern in _CORRECTION_PATTERNS:
        if re.search(pattern, text):
            flags.append("user_correction")
            break
    # ExperienceCard 触发词（如 David）
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
) -> Optional[tuple[str, Optional[str]]]:
    """分析会话轮次文本，若检测到 risk pattern 则创建并持久化 MemoryEvent。

    返回 (event_id, routing_hint) 或 None。
    routing_hint: ExperienceCard 命中时的 rendered 文本（可注入 working memory）；无命中时为 None。
    never raises。
    """
    try:
        if not text or not text.strip():
            return None
        flags = _detect_risk_flags(text)
        if not flags:
            return None
        routing_hint: Optional[str] = None
        try:
            card = _ec_trigger_check(text, hermes_home=hermes_home)
            if card is not None:
                routing_hint = _render_card(card)
        except Exception:
            pass
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
        event_id = write_event(evt, hermes_home=hermes_home)
        if event_id is None:
            return None
        return (event_id, routing_hint)
    except Exception as exc:
        logger.debug("capture_turn failed (non-fatal): %s", exc)
        return None
