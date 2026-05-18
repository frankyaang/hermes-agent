"""
Python dataclass representations of protocol.yaml entries.
KNOWN_PHASES is NOT defined here — import from phase_registry instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RiskLevel = Literal["low", "medium", "high"]
ControlMode = Literal["disabled", "shadow", "advisory", "controlled", "quarantined"]


@dataclass(frozen=True)
class PhaseSpec:
    id: str
    label: str
    description: str
    gstack_command: str
    risk_level: RiskLevel
    allowed_modes: list[str]
    blocking_allowed: bool
    production_ready: bool
    real_gstack: bool


@dataclass(frozen=True)
class ControlDecision:
    phase_id: str
    risk_level: RiskLevel
    mode: ControlMode
    # blocking is never True by default — field exists for audit trail only
    blocking: bool = False
    advisory_message: str = ""
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.blocking:
            raise ValueError(
                "ControlDecision.blocking=True is prohibited. "
                "blocking requires allow_blocking=True and explicit human approval."
            )
