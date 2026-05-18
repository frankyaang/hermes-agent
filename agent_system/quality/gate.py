"""
Quality gate — integrates CandidateAnswerEvaluator into the final_response path.

apply_quality_gate_if_enabled(candidate, already_streamed) → str

Behavior:
  QUALITY_LOOP_GATED=false (default) → return candidate unchanged (zero overhead)
  already_streamed=True → log evaluation only, return candidate unchanged (safe degradation)
  verdict=pass → return candidate unchanged
  verdict=rewrite → return clean rewrite (NOT suggestions+original)
  verdict=clarify → return clean clarification question
  Any exception → log warning, return candidate unchanged (fail-safe)
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_ENV_KEY = "QUALITY_LOOP_GATED"


def is_quality_gate_enabled() -> bool:
    return os.environ.get(_ENV_KEY, "").strip().lower() in ("1", "true", "yes")


def apply_quality_gate_if_enabled(
    candidate: str,
    already_streamed: bool = False,
) -> str:
    """
    Apply quality gate to a candidate final response.

    This is the single integration point called from run_agent.py.
    Safe to call unconditionally — returns candidate unchanged unless
    QUALITY_LOOP_GATED=true AND not already_streamed AND verdict!=pass.
    """
    if not is_quality_gate_enabled():
        return candidate

    # Streaming safety: content already delivered to user — only log
    if already_streamed:
        try:
            from .evaluator import CandidateAnswerEvaluator
            result = CandidateAnswerEvaluator().evaluate(candidate)
            logger.info(
                "quality_gate[streamed]: verdict=%s score=%.2f reason=%s",
                result.verdict, result.score, result.reason,
            )
        except Exception as exc:
            logger.warning("quality_gate[streamed] evaluation failed: %s", exc)
        return candidate

    try:
        from .evaluator import CandidateAnswerEvaluator
        evaluator = CandidateAnswerEvaluator()
        result = evaluator.evaluate(candidate)

        logger.info(
            "quality_gate: verdict=%s score=%.2f reason=%s",
            result.verdict, result.score, result.reason,
        )

        if result.verdict == "pass":
            return candidate

        if result.verdict == "rewrite":
            rewritten = result.rewrite_target
            if rewritten and rewritten.strip():
                logger.info(
                    "quality_gate: rewrote response (%d → %d chars)",
                    len(candidate), len(rewritten),
                )
                return rewritten
            # rewrite_target empty — fallback to original
            logger.warning("quality_gate: rewrite_target empty, using original")
            return candidate

        if result.verdict == "clarify":
            clarification = result.rewrite_target
            if clarification and clarification.strip():
                logger.info("quality_gate: returning clarification question")
                return clarification
            return candidate

        return candidate

    except Exception as exc:
        logger.warning("quality_gate: exception during evaluation, using original: %s", exc)
        return candidate
