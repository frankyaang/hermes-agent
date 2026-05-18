"""
Dry-run executor — simulate phase evaluation with no real side effects.
Does not call gstack CLI, does not touch Gateway, does not modify config.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from .state_machine import evaluate
from .specs import RiskLevel, ControlDecision


@dataclass
class DryRunRecord:
    phase_id: str
    risk_level: RiskLevel
    decision: dict[str, Any]
    timestamp_ms: int
    notes: str = ""


def run(
    phase_id: str,
    risk_level: RiskLevel = "low",
    notes: str = "",
) -> DryRunRecord:
    """
    Simulate evaluate() and return a DryRunRecord.
    No real gstack CLI is invoked. No Gateway calls. No config changes.
    """
    decision: ControlDecision = evaluate(phase_id, risk_level)
    return DryRunRecord(
        phase_id=phase_id,
        risk_level=risk_level,
        decision={
            "mode": decision.mode,
            "blocking": decision.blocking,
            "advisory_message": decision.advisory_message,
        },
        timestamp_ms=int(time.time() * 1000),
        notes=notes,
    )


def to_json(record: DryRunRecord) -> str:
    return json.dumps(asdict(record), indent=2)
