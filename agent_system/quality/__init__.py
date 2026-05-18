"""
agent_system.quality — Quality gate subsystem.

Chain: candidate final_response → CandidateAnswerEvaluator → EvalResult → gate decision

QUALITY_LOOP_GATED=false (default) → zero overhead noop
QUALITY_LOOP_GATED=true → evaluate and optionally rewrite

Streaming safety: already_streamed=True → only log, never replace.
Rewrite exception fallback: original response returned, warning logged.
"""
from .models import UnderstandingState, BoundaryMemory, UserQualityFunction, EvalResult
from .evaluator import CandidateAnswerEvaluator
from .gate import apply_quality_gate_if_enabled, is_quality_gate_enabled

__all__ = [
    "UnderstandingState",
    "BoundaryMemory",
    "UserQualityFunction",
    "EvalResult",
    "CandidateAnswerEvaluator",
    "apply_quality_gate_if_enabled",
    "is_quality_gate_enabled",
]
