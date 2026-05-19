"""
B-2 Shadow Hook — Regression Tests

直接测试 _classify_and_log_correction 的行为逻辑，不依赖完整 run_agent 导入
（run_agent 需要 fire 等生产依赖，在隔离测试环境中不可用）。

验证：
  1. UNDERSTANDING_LOOP_SHADOW=false 时跳过（不写日志）
  2. UNDERSTANDING_LOOP_SHADOW=true 时对纠偏消息写日志
  3. correction_type=none 时不写日志
  4. 异常时严格 best-effort，不向上抛出
  5. 不修改 agent 状态
"""
from __future__ import annotations

import logging
import os
import types


def _make_hook_fn():
    """
    从 run_agent._classify_and_log_correction 提取逻辑，
    构造一个独立可测试函数，签名与原始方法一致（self, user_message）。
    """
    def _classify_and_log_correction(self, user_message: str) -> None:
        if os.getenv("UNDERSTANDING_LOOP_SHADOW", "").lower() != "true":
            return
        try:
            from agent.understanding.correction_classifier import classify_correction
            result = classify_correction(
                user_message,
                turn_index=len(self._session_messages),
            )
            if result.correction_type != "none":
                logger = logging.getLogger("run_agent")
                logger.info(
                    "understanding_shadow correction_type=%s confidence=%.2f scope=%s",
                    result.correction_type,
                    result.confidence,
                    result.scope,
                )
        except Exception:
            pass
    return _classify_and_log_correction


def _bare_agent():
    """最小 agent stub，只有 _classify_and_log_correction 需要的属性。"""
    agent = types.SimpleNamespace()
    agent._session_messages = []
    agent._classify_and_log_correction = _make_hook_fn().__get__(agent, type(agent))
    return agent


# ──────────────────────────────────────────────
# 1. shadow=false 时跳过（不写日志）
# ──────────────────────────────────────────────

def test_shadow_disabled_by_default(monkeypatch, caplog):
    monkeypatch.delenv("UNDERSTANDING_LOOP_SHADOW", raising=False)
    agent = _bare_agent()

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._classify_and_log_correction("不对，这两个问题要分别思考")

    assert "understanding_shadow" not in caplog.text


def test_shadow_disabled_when_env_false(monkeypatch, caplog):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "false")
    agent = _bare_agent()

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._classify_and_log_correction("不对，这两个问题要分别思考")

    assert "understanding_shadow" not in caplog.text


# ──────────────────────────────────────────────
# 2. shadow=true 时对纠偏消息写日志
# ──────────────────────────────────────────────

def test_shadow_logs_separation_correction(monkeypatch, caplog):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "true")
    agent = _bare_agent()

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._classify_and_log_correction("不对，这是两个独立问题，要分别思考")

    assert "understanding_shadow" in caplog.text
    assert "separation_correction" in caplog.text


def test_shadow_logs_generalization_correction(monkeypatch, caplog):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "true")
    agent = _bare_agent()

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._classify_and_log_correction("你的回答太具体了，应该给更通用的解法")

    assert "understanding_shadow" in caplog.text
    assert "generalization_correction" in caplog.text


def test_shadow_logs_confidence_and_scope(monkeypatch, caplog):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "true")
    agent = _bare_agent()

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._classify_and_log_correction("不对，这是两个独立问题，要分别思考")

    assert "confidence=" in caplog.text
    assert "scope=" in caplog.text


# ──────────────────────────────────────────────
# 3. correction_type=none 时不写日志
# ──────────────────────────────────────────────

def test_shadow_silent_on_normal_message(monkeypatch, caplog):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "true")
    agent = _bare_agent()

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._classify_and_log_correction("好的，继续")

    assert "understanding_shadow" not in caplog.text


# ──────────────────────────────────────────────
# 4. 异常时 best-effort，不向上抛出
# ──────────────────────────────────────────────

def test_shadow_exception_is_swallowed(monkeypatch):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "true")
    agent = _bare_agent()

    def _boom(*args, **kwargs):
        raise RuntimeError("classifier boom")

    monkeypatch.setattr(
        "agent.understanding.correction_classifier.classify_correction",
        _boom,
    )

    # 不应该抛出
    agent._classify_and_log_correction("任意消息")


# ──────────────────────────────────────────────
# 5. 不修改 agent 状态
# ──────────────────────────────────────────────

def test_shadow_does_not_mutate_session_messages(monkeypatch):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "true")
    agent = _bare_agent()
    before = list(agent._session_messages)

    agent._classify_and_log_correction("不对，这两个问题要分别思考")

    assert agent._session_messages == before


def test_shadow_env_case_insensitive_true(monkeypatch, caplog):
    monkeypatch.setenv("UNDERSTANDING_LOOP_SHADOW", "True")
    agent = _bare_agent()

    with caplog.at_level(logging.INFO, logger="run_agent"):
        agent._classify_and_log_correction("不对，这两个问题要分别思考")

    assert "understanding_shadow" in caplog.text
