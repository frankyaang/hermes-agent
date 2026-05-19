"""
quality_loop_gated — QUALITY_LOOP_GATED 特性门控。

QUALITY_LOOP_GATED=false（默认）：原样返回，不做任何评估。
QUALITY_LOOP_GATED=true：
  - pass → 原始答案
  - fail + rewrite + llm_rewrite_fn provided → llm_rewrite_fn(original, guidance) 的干净结果
  - fail + rewrite + llm_rewrite_fn=None → 原始答案（streaming fallback）
  - fail + clarify → 格式化澄清问题（不含原始答案）
  - llm_rewrite_fn 抛异常 → fallback 原始答案
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from agent.understanding.candidate_answer_evaluator import CandidateAnswerEvaluation
    from agent.understanding.schemas import BoundaryMemory, UnderstandingState
    from agent.understanding.user_quality_function import UserQualityFunction

logger = logging.getLogger(__name__)


def apply_quality_gate(
    candidate_answer: str,
    prior_response: str,
    understanding_state: "UnderstandingState",
    boundary_memory: "list[BoundaryMemory]",
    quality_fn: "UserQualityFunction",
    llm_rewrite_fn: Callable[[str, str], str] | None = None,
) -> "tuple[str, CandidateAnswerEvaluation]":
    """
    Returns (final_answer, evaluation).

    行为矩阵：
    - QUALITY_LOOP_GATED=false → (原始答案, noop evaluation)
    - true + pass → (原始答案, evaluation)
    - true + fail + rewrite + fn provided → (fn(original, guidance), evaluation)
    - true + fail + rewrite + fn=None → (原始答案, evaluation)  # streaming fallback
    - true + fail + clarify → (格式化澄清问题, evaluation)      # 不含原始答案
    - true + fail + fn raises → (原始答案, evaluation)           # exception fallback
    """
    from agent.understanding.candidate_answer_evaluator import (
        CandidateAnswerEvaluation,
        evaluate_candidate_answer,
    )

    if os.getenv("QUALITY_LOOP_GATED", "").lower() != "true":
        noop = CandidateAnswerEvaluation(
            overall_pass=True,
            failed_checks=[],
            reason="",
            rewrite_guidance="",
            rewrite_or_clarify="pass",
        )
        return candidate_answer, noop

    evaluation = evaluate_candidate_answer(
        candidate_answer=candidate_answer,
        prior_response=prior_response,
        understanding_state=understanding_state,
        boundary_memory=boundary_memory,
        quality_fn=quality_fn,
    )

    if evaluation.overall_pass:
        return candidate_answer, evaluation

    logger.info("quality_gate: failed checks=%s rewrite_or_clarify=%s",
                evaluation.failed_checks, evaluation.rewrite_or_clarify)

    if evaluation.rewrite_or_clarify == "clarify":
        clarify_text = _format_clarify(evaluation.rewrite_guidance)
        return clarify_text, evaluation

    # rewrite 路径
    if llm_rewrite_fn is None:
        # streaming fallback: 不修改，只记录
        return candidate_answer, evaluation

    try:
        rewritten = llm_rewrite_fn(candidate_answer, evaluation.rewrite_guidance)
        return rewritten, evaluation
    except Exception as exc:
        logger.warning("quality_gate: rewrite failed, fallback to original: %s", exc)
        return candidate_answer, evaluation


def _format_clarify(rewrite_guidance: str) -> str:
    """从 rewrite_guidance 提取问题，输出干净澄清文本（不含原始答案）。"""
    lines = []
    for line in rewrite_guidance.splitlines():
        line = line.strip()
        if line.startswith("- [") and "]:" in line:
            # 提取括号后面的说明部分
            after_bracket = line.split("]:", 1)[-1].strip()
            if after_bracket:
                lines.append(f"- {after_bracket}")
    if not lines:
        return "为了给出更准确的回答，我需要先确认您的具体需求，请进一步说明。"
    return "为了给出更准确的回答，我需要先确认：\n" + "\n".join(lines)
