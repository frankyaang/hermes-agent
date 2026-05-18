"""
risk_level → ControlMode state machine.

Transitions (hardcoded, not configurable at runtime):
  low    → disabled   (no-op)
  medium → shadow     (record only, no intervention)
  high   → advisory   (return suggestion, never block)

blocking is NEVER returned by default. It requires:
  1. allow_blocking=True in feature_flags
  2. Explicit human approval (out of scope for MVP)
"""
from __future__ import annotations

from .feature_flags import is_enabled, get_mode, is_blocking_allowed
from .specs import RiskLevel, ControlMode, ControlDecision
from .phase_registry import KNOWN_PHASES

_RISK_TO_MODE: dict[RiskLevel, ControlMode] = {
    "low": "disabled",
    "medium": "shadow",
    "high": "advisory",
}


def evaluate(phase_id: str, risk_level: RiskLevel | None = None) -> ControlDecision:
    """
    Evaluate a phase and return the appropriate ControlDecision.

    When feature flag is disabled (default), always returns mode=disabled.
    blocking is never returned by this function.
    """
    if not is_enabled():
        return ControlDecision(
            phase_id=phase_id,
            risk_level=risk_level or "low",
            mode="disabled",
            blocking=False,
        )

    phase_spec = KNOWN_PHASES.get(phase_id)
    effective_risk: RiskLevel = risk_level or (
        phase_spec.risk_level if phase_spec else "low"
    )

    resolved_mode: ControlMode = _RISK_TO_MODE.get(effective_risk, "disabled")

    # Honour the configured mode ceiling from feature_flags
    configured_mode = get_mode()
    if configured_mode == "disabled":
        resolved_mode = "disabled"
    elif configured_mode == "shadow" and resolved_mode == "advisory":
        resolved_mode = "shadow"

    advisory_message = ""
    if resolved_mode == "advisory" and phase_spec:
        advisory_message = (
            f"[gstack advisory] Phase '{phase_spec.label}' "
            f"(risk={effective_risk}): review recommended before proceeding."
        )

    return ControlDecision(
        phase_id=phase_id,
        risk_level=effective_risk,
        mode=resolved_mode,
        blocking=False,  # never True in MVP
        advisory_message=advisory_message,
    )
