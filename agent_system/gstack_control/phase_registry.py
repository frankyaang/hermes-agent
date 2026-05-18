"""
Phase registry — loads phase definitions from protocol.yaml (single source of truth).
specs.py must not maintain a second copy of KNOWN_PHASES.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .specs import PhaseSpec

_PROTOCOL_PATH = Path(__file__).parent / "protocol.yaml"

_KNOWN_COMMANDS: list[str] = []
KNOWN_PHASES: dict[str, PhaseSpec] = {}


def _load() -> None:
    global _KNOWN_COMMANDS, KNOWN_PHASES
    with _PROTOCOL_PATH.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    _KNOWN_COMMANDS = data.get("known_commands", [])

    phases: dict[str, PhaseSpec] = {}
    for p in data.get("phases", []):
        spec = PhaseSpec(
            id=p["id"],
            label=p["label"],
            description=p["description"],
            gstack_command=p.get("gstack_command", ""),
            risk_level=p["risk_level"],
            allowed_modes=p.get("allowed_modes", []),
            blocking_allowed=p.get("blocking_allowed", False),
            production_ready=p.get("production_ready", False),
            real_gstack=p.get("real_gstack", False),
        )
        phases[spec.id] = spec
    KNOWN_PHASES = phases


_load()


def get_phase(phase_id: str) -> PhaseSpec | None:
    return KNOWN_PHASES.get(phase_id)


def list_phases() -> list[PhaseSpec]:
    return list(KNOWN_PHASES.values())


def list_known_commands() -> list[str]:
    return list(_KNOWN_COMMANDS)


def is_registered(phase_id: str) -> bool:
    return phase_id in KNOWN_PHASES


def is_production_ready(phase_id: str) -> bool:
    spec = KNOWN_PHASES.get(phase_id)
    return spec.production_ready if spec is not None else False
