"""
Read-only suggestion mapping: gstack phase → Hermes route hint.
This module never writes to or modifies the Hermes router.
It returns suggestions only; the actual routing decision
remains entirely with Hermes runtime.
"""
from __future__ import annotations

from .phase_registry import get_phase

# Advisory-only hints. These do NOT override Hermes routing.
_PHASE_TO_ROUTE_HINT: dict[str, str] = {
    "gstack.plan_eng_review": "insight_flow",
    "gstack.review": "insight_flow",
    "gstack.qa": "artifact_status_flow",
}


def get_route_hint(phase_id: str) -> str | None:
    """
    Return a non-binding route hint for a given phase.
    Returns None if the phase is unknown or not registered.
    The caller must treat this as advisory only.
    """
    if get_phase(phase_id) is None:
        return None
    return _PHASE_TO_ROUTE_HINT.get(phase_id)
