"""
CandidateAnswerEvaluator — heuristic-first quality evaluator.

Design principle: no LLM call needed for the heuristic pass.
Only genuinely low-quality responses (<0.3) get a rewrite.
Rewrite is a clean new answer, not "suggestions + original".

Scoring heuristics:
- Empty or whitespace-only → 0.0 (rewrite)
- Very short (<15 chars) → 0.1 (rewrite)
- Contains only hedge phrases with no substance → 0.2 (rewrite)
- Ambiguous (no clear statement or question) → 0.25 (clarify)
- Otherwise → score based on length + actionable phrases (0.5–1.0)
"""
from __future__ import annotations

import re

from .models import EvalResult, UnderstandingState, UserQualityFunction

_HEDGE_PATTERNS = [
    re.compile(r"^i\s+(don[''`]t|do not)\s+know\.?\s*$", re.I),
    re.compile(r"^(maybe|perhaps)\s+(try|you could|it might).*\.$", re.I),
    re.compile(r"^(um+|uh+|err+)\.?\s*(\.\.\.)?$", re.I),
    re.compile(r"(could work or not|not sure what you want)", re.I),
]

_VAGUE_SIGNALS = [
    "i'm not sure",
    "i don't know",
    "maybe try",
    "it could work",
    "not sure what you want",
    "some things",
    "um...",
    "uh...",
]

_ACTIONABLE_SIGNALS = [
    "because",
    "therefore",
    "you should",
    "you can",
    "the reason",
    "the solution",
    "to fix",
    "the answer",
    "specifically",
    "in order to",
]


class CandidateAnswerEvaluator:
    """Heuristic quality evaluator for candidate final responses."""

    def __init__(self, quality_fn: UserQualityFunction | None = None) -> None:
        self._qfn = quality_fn or UserQualityFunction()

    def evaluate(self, candidate: str) -> EvalResult:
        """
        Evaluate a candidate response and return EvalResult.

        verdict=pass    → return as-is
        verdict=rewrite → rewrite_target contains clean replacement
        verdict=clarify → rewrite_target contains clean clarification question
        """
        state = self._analyze(candidate)
        score = state.score

        if score >= self._qfn.pass_threshold:
            return EvalResult(
                verdict="pass",
                score=score,
                reason="response meets quality threshold",
            )

        if score >= self._qfn.rewrite_threshold:
            clarification = self._make_clarification(candidate)
            return EvalResult(
                verdict="clarify",
                score=score,
                reason="response is ambiguous — clarification needed",
                rewrite_target=clarification,
            )

        rewrite = self._make_rewrite(candidate, state)
        return EvalResult(
            verdict="rewrite",
            score=score,
            reason="response below quality threshold",
            rewrite_target=rewrite,
        )

    def _analyze(self, candidate: str) -> UnderstandingState:
        state = UnderstandingState()
        stripped = candidate.strip()

        if not stripped:
            state.score = 0.0
            state.is_incomplete = True
            state.has_actionable_content = False
            state.length_ok = False
            return state

        if len(stripped) < self._qfn.min_length_chars:
            state.score = 0.1
            state.is_incomplete = True
            state.length_ok = False
            return state

        # Check for pure hedge (no substance)
        for pat in _HEDGE_PATTERNS:
            if pat.search(stripped):
                state.is_vague = True
                state.is_evasive = True
                state.has_actionable_content = False
                state.score = 0.2
                return state

        # Count vague signals
        lower = stripped.lower()
        vague_count = sum(1 for s in _VAGUE_SIGNALS if s in lower)
        actionable_count = sum(1 for s in _ACTIONABLE_SIGNALS if s in lower)

        if vague_count >= 2 and actionable_count == 0:
            state.is_vague = True
            state.score = 0.25
            return state

        # Length-based score (longer = more likely complete)
        length_score = min(1.0, len(stripped) / 200)
        actionable_bonus = min(0.3, actionable_count * 0.1)
        vague_penalty = min(0.3, vague_count * 0.1)

        state.score = max(0.0, min(1.0, 0.5 + length_score * 0.3 + actionable_bonus - vague_penalty))
        state.has_actionable_content = actionable_count > 0
        return state

    def _make_rewrite(self, candidate: str, state: UnderstandingState) -> str:
        """
        Produce a clean rewrite — NOT 'suggestions + original'.

        For MVP: generate a meta-response acknowledging the gap.
        In production this would call an LLM with strict instructions.
        """
        if not candidate.strip():
            return "I need more context to give you a complete answer. Could you clarify what you're looking for?"

        if state.is_incomplete or not state.length_ok:
            return "I don't have enough information to answer that fully right now. Please provide more details so I can help you accurately."

        # Strip vague hedges and produce clean fallback
        return "I want to make sure I give you a useful answer. Could you tell me more specifically what you need, so I can respond accurately?"

    def _make_clarification(self, candidate: str) -> str:
        """Produce a clean clarification question."""
        return "Could you clarify what you mean? I want to make sure my answer addresses your actual question."
