"""
Per-phase performance budgets (latency + token limits).
Used by roi_controller for redacted ROI calculations.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseBudget:
    phase_id: str
    max_latency_ms: int
    max_input_tokens: int
    max_output_tokens: int


PHASE_BUDGETS: dict[str, PhaseBudget] = {
    "gstack.plan_eng_review": PhaseBudget(
        phase_id="gstack.plan_eng_review",
        max_latency_ms=30_000,
        max_input_tokens=8_000,
        max_output_tokens=2_000,
    ),
    "gstack.review": PhaseBudget(
        phase_id="gstack.review",
        max_latency_ms=30_000,
        max_input_tokens=8_000,
        max_output_tokens=2_000,
    ),
    "gstack.qa": PhaseBudget(
        phase_id="gstack.qa",
        max_latency_ms=60_000,
        max_input_tokens=12_000,
        max_output_tokens=4_000,
    ),
}


def get_budget(phase_id: str) -> PhaseBudget | None:
    return PHASE_BUDGETS.get(phase_id)


def within_budget(
    phase_id: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
) -> bool:
    budget = get_budget(phase_id)
    if budget is None:
        return False
    return (
        latency_ms <= budget.max_latency_ms
        and input_tokens <= budget.max_input_tokens
        and output_tokens <= budget.max_output_tokens
    )
