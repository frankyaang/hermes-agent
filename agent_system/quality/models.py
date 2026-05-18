"""
Data models for the Quality gate subsystem.

UnderstandingState   — captures the evaluator's reading of the candidate response
BoundaryMemory       — tracks evaluation history for the session (in-memory only)
UserQualityFunction  — quality thresholds / preferences (configurable)
EvalResult           — output of CandidateAnswerEvaluator.evaluate()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class EvalResult:
    verdict: Literal["pass", "rewrite", "clarify"]
    score: float        # 0.0 – 1.0 (higher = better)
    reason: str
    rewrite_target: str = ""  # clean rewrite text (verdict=rewrite) or clarification (verdict=clarify)


@dataclass
class UnderstandingState:
    """Evaluator's interpretation of the candidate response."""
    is_vague: bool = False
    is_incomplete: bool = False
    is_contradictory: bool = False
    is_evasive: bool = False
    has_actionable_content: bool = True
    length_ok: bool = True
    score: float = 1.0


@dataclass
class UserQualityFunction:
    """
    Quality preferences / thresholds.

    pass_threshold: responses scoring above this are passed unchanged.
    rewrite_threshold: responses scoring below this trigger a rewrite.
    Between pass_threshold and rewrite_threshold: clarify path.
    """
    pass_threshold: float = 0.5
    rewrite_threshold: float = 0.3
    min_length_chars: int = 10
    max_length_chars: int = 50_000


@dataclass
class BoundaryMemory:
    """In-memory log of quality evaluations for this session."""
    evaluations: list[dict] = field(default_factory=list)

    def record(self, candidate: str, result: EvalResult) -> None:
        self.evaluations.append({
            "candidate_length": len(candidate),
            "verdict": result.verdict,
            "score": result.score,
            "reason": result.reason,
        })
