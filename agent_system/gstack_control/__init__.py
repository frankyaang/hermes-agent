"""
agent_system.gstack_control — GStack SDLC phase control protocol skeleton.

Public API (all no-ops when feature_flags.enabled=False):
  evaluate(phase_id, risk_level) -> ControlDecision
  dry_run(phase_id, risk_level)  -> DryRunRecord

Import is intentionally lazy: when enabled=False, importing this package
has zero side effects on Hermes runtime, Gateway, or prompt cache.
"""
from __future__ import annotations

from .feature_flags import is_enabled, get_flag, get_mode, is_blocking_allowed
from .specs import ControlDecision, PhaseSpec
from .phase_registry import KNOWN_PHASES


def evaluate(phase_id: str, risk_level: str = "low") -> "ControlDecision":
    if not is_enabled():
        return ControlDecision(
            phase_id=phase_id,
            risk_level=risk_level,  # type: ignore[arg-type]
            mode="disabled",
            blocking=False,
        )
    from .state_machine import evaluate as _evaluate
    return _evaluate(phase_id, risk_level)  # type: ignore[arg-type]


def dry_run(phase_id: str, risk_level: str = "low") -> "object":
    from .dry_run import run
    return run(phase_id, risk_level)  # type: ignore[arg-type]


__all__ = [
    "evaluate",
    "dry_run",
    "is_enabled",
    "get_flag",
    "get_mode",
    "is_blocking_allowed",
    "ControlDecision",
    "PhaseSpec",
    "KNOWN_PHASES",
]
