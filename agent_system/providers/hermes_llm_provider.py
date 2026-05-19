"""Hermes-aware LLM provider for agent_system skills."""
from __future__ import annotations

import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)


def make_hermes_llm_call() -> Callable[[str], str]:
    """返回一个封装了 Anthropic 客户端的 LLM 调用函数。

    读取 ANTHROPIC_API_KEY 和 HERMES_SKILL_LLM_MODEL 环境变量。
    初始化失败时返回 noop（→ "[]"），不抛异常。
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("HERMES_SKILL_LLM_MODEL", "claude-haiku-4-5-20251001")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        def call(prompt: str) -> str:
            resp = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()

        return call
    except Exception as exc:
        logger.error("hermes_llm_provider: failed to init Anthropic client: %s", exc)
        return lambda p: "[]"
