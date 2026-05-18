"""
Replay — re-evaluate a stored DryRunRecord against the current state machine.
Useful for verifying that a past decision would still hold today.
"""
from __future__ import annotations

import json
from typing import Any

from .dry_run import DryRunRecord, run
from .specs import RiskLevel


def replay_record(record: DryRunRecord) -> DryRunRecord:
    """Re-run dry_run.run() with the same inputs as an existing record."""
    return run(
        phase_id=record.phase_id,
        risk_level=record.risk_level,
        notes=f"replayed from timestamp_ms={record.timestamp_ms}",
    )


def replay_json(record_json: str) -> DryRunRecord:
    """Parse a JSON dry-run record and replay it."""
    data: dict[str, Any] = json.loads(record_json)
    record = DryRunRecord(
        phase_id=data["phase_id"],
        risk_level=data["risk_level"],
        decision=data["decision"],
        timestamp_ms=data["timestamp_ms"],
        notes=data.get("notes", ""),
    )
    return replay_record(record)
