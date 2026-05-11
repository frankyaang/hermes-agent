"""
Builder Mode Dispatcher — entry/exit detection for 深度养马模式.

This module is the thin pre-LLM hook that intercepts user messages to handle
the skill creation mode (builder_expert). It is designed to be called from
cli_bridge.maybe_run_agent_system_from_message before any pipeline routing.

Responsibilities (Task #7 scope):
  - Detect entry/exit phrases (substring match, case-insensitive)
  - Create / remove the per-(user_id, channel_id) state file
  - When mode is active, route message to the state machine handler

The actual state machine logic (Stage 2-9) lives in the builder_expert package
and is wired in by Task #8. For now this module provides the entry/exit
plumbing and a stub for the in-mode handler.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Phrases must be loaded from expert.json so they stay in one place.
_EXPERT_MANIFEST_PATH = (
    Path(__file__).parent / "experts" / "builder_expert" / "expert.json"
)


def _load_phrases() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Load entry/exit phrases from builder_expert manifest. Cache on first call."""
    try:
        manifest = json.loads(_EXPERT_MANIFEST_PATH.read_text(encoding="utf-8"))
        phrases = manifest.get("mode_phrases", {})
        entry = tuple(phrases.get("entry", []))
        exit_ = tuple(phrases.get("exit", []))
        if not entry or not exit_:
            raise ValueError("mode_phrases missing entry/exit lists")
        return entry, exit_
    except Exception as exc:
        logger.warning("builder_expert manifest unreadable, mode disabled: %s", exc)
        return (), ()


_ENTRY_PHRASES, _EXIT_PHRASES = _load_phrases()


def _state_dir(project_root: Path) -> Path:
    """State files live under <agent_system_root>/temp/.

    `project_root` here matches cli_bridge's _find_agent_system_root return:
    the directory containing scheduler/main_scheduler/routes.json (i.e., the
    agent_system/ dir itself, not the repo root).
    """
    return project_root / "temp"


def _state_file_path(
    project_root: Path, user_id: str | None, channel_id: str | None
) -> Path:
    user = user_id or "default"
    channel = channel_id or "default"
    return _state_dir(project_root) / f"skill_creation_{user}_{channel}.json"


def _match_phrase(message: str, phrases: tuple[str, ...]) -> bool:
    if not phrases:
        return False
    lowered = message.lower()
    return any(p.lower() in lowered for p in phrases)


def _enter_mode(state_path: Path, user_id: str, channel_id: str) -> dict[str, Any]:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    initial_state = {
        "stage": "INTAKE",
        "mode_started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_id": user_id,
        "channel_id": channel_id,
        "intake": {"_current_question": "INTENT_CHOICE"},
        "architect_proposal": None,
        "drafts": {},
        "validation": {},
        "dry_run": {},
        "trial_run": {},
        "history": [],
    }
    state_path.write_text(
        json.dumps(initial_state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return _final_response(
        "🐎 **深度养马模式已启动**\n\n"
        "本模式用于让 Hermes 沉淀新能力。随时可说"
        "【退出深度养马模式】结束。\n\n"
        "**你想做什么？**\n\n"
        "1️⃣ **数据分析能力** — 创建一个能分析 VOC / 工单 / 评论 / 竞品等数据的新能力\n"
        "2️⃣ **自动化任务** — 创建一个定时或事件触发的能力（每天 / 每周 / 异常告警）\n"
        "3️⃣ **新决策视角** — 让 Hermes 学会一个新的判断角度（多用于业务决策类）\n"
        "4️⃣ **现有能力扩展** — 在已有能力之上加新功能\n"
        "5️⃣ **知识固化** — 把你反复在做的事沉淀成可调用的能力\n"
        "6️⃣ **自由描述** — 不知道选哪类，直接用自然语言说需求，我来判断\n\n"
        "回复数字（1-6）或直接描述。"
    )


def _exit_mode(state_path: Path) -> dict[str, Any]:
    had_state = state_path.exists()
    if had_state:
        try:
            state_path.unlink()
        except OSError as exc:
            logger.warning("failed to remove builder state file: %s", exc)
    msg = (
        "🐎 已退出深度养马模式。本次未完成的 draft 已保留在 _drafts/ 目录。"
        if had_state
        else "🐎 当前并未处于深度养马模式。"
    )
    return _final_response(msg)


def _dispatch_to_state_machine(
    state_path: Path, user_message: str, parent_agent: Any
) -> dict[str, Any]:
    """Hand off to builder_expert state machine."""
    try:
        from agent_system.experts.builder_expert.builder import handle as builder_handle
    except Exception as exc:
        logger.exception("failed to import builder state machine: %s", exc)
        return _final_response(
            "🐎 状态机模块加载失败，已为你保留 mode 状态。请说 "
            "\"退出深度养马模式\" 重置后重试。"
        )
    try:
        text = builder_handle(user_message, state_path, parent_agent)
    except Exception as exc:
        logger.exception("builder.handle raised: %s", exc)
        text = (
            "🐎 状态机执行异常，状态已保留以便恢复。"
            f"\n错误：{exc.__class__.__name__}: {exc}"
        )
    return _final_response(text)


def _final_response(text: str) -> dict[str, Any]:
    return {
        "final_response": text,
        "agent_system_result": None,
        "completed": True,
        "agent_system_status": "builder_mode",
        "interrupted": False,
        "api_calls": 0,
        "model": None,
        "provider": None,
        "task_id": None,
    }


def maybe_handle_builder_mode(
    user_message: str,
    *,
    parent_agent: Any,
    project_root: Path,
    task_id: str | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict[str, Any] | None:
    """Pre-LLM hook for 深度养马模式.

    Returns:
        dict with `final_response` if the message was handled by this dispatcher;
        None if normal cli_bridge / LLM flow should continue.
    """
    if not isinstance(user_message, str) or not user_message.strip():
        return None
    if not _ENTRY_PHRASES:
        return None  # manifest unreadable, mode disabled

    user_id = getattr(parent_agent, "user_id", None) or "default"
    channel_id = getattr(parent_agent, "chat_id", None) or "default"
    state_path = _state_file_path(project_root, user_id, channel_id)

    # Exit takes precedence even when not in mode (idempotent).
    if _match_phrase(user_message, _EXIT_PHRASES):
        return _exit_mode(state_path)

    if _match_phrase(user_message, _ENTRY_PHRASES):
        if state_path.exists():
            return _final_response(
                "🐎 深度养马模式已经在进行中。继续上次未完成的创建任务，"
                "或先说【退出深度养马模式】再重新开始。"
            )
        return _enter_mode(state_path, user_id, channel_id)

    if state_path.exists():
        return _dispatch_to_state_machine(state_path, user_message, parent_agent)

    return None
