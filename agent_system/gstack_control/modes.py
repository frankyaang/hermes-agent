"""
Five runtime mode implementations for gstack_control.

All functions return ModeResult and never raise.
Failures → quarantined ModeResult (fail-closed).
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModeResult:
    mode: str
    phase_id: str
    success: bool
    advisory_note: str = ""
    blocked_reason: str = ""
    evidence: dict = field(default_factory=dict)
    dry_run_only: bool = True


def run_disabled(phase_id: str, context: dict | None = None) -> ModeResult:
    """Immediate return, zero side effects."""
    return ModeResult(mode="disabled", phase_id=phase_id, success=True)


def run_shadow(phase_id: str, context: dict | None = None) -> ModeResult:
    """
    Shadow mode: call adapter, write metrics, do NOT change model output.
    Returns success=True even if adapter is blocked (observation still counts).
    """
    try:
        from .adapter import run_gstack_shadow
        from .metrics_writer import write_metric

        ctx = context or {}
        result = run_gstack_shadow(phase_id, ctx)
        write_metric("shadow", {
            "phase_id": phase_id,
            "available": result.available,
            "blocked_reason": result.blocked_reason,
            "duration_ms": result.duration_ms,
        })
        return ModeResult(
            mode="shadow",
            phase_id=phase_id,
            success=True,
            blocked_reason=result.blocked_reason,
            evidence={"adapter_result": {
                "available": result.available,
                "exit_code": result.exit_code,
                "blocked_reason": result.blocked_reason,
                "duration_ms": result.duration_ms,
            }},
        )
    except Exception:  # noqa: BLE001
        return run_quarantined(phase_id, traceback.format_exc(), context)


def run_advisory(phase_id: str, context: dict | None = None) -> ModeResult:
    """
    Advisory mode: return suggestion text annotated with [gstack advisory].
    Never blocks; advisory note is informational only.
    """
    try:
        from .adapter import run_gstack_advisory
        from .metrics_writer import write_metric
        from .phase_registry import get_phase

        ctx = context or {}
        result = run_gstack_advisory(phase_id, ctx)
        phase_spec = get_phase(phase_id)
        label = phase_spec.label if phase_spec else phase_id

        if result.available and not result.blocked_reason:
            note = f"[gstack advisory] Phase '{label}': review recommended before proceeding."
        else:
            note = (
                f"[gstack advisory] Phase '{label}': "
                f"advisory unavailable ({result.blocked_reason or 'CLI not found'})."
            )

        write_metric("advisory", {
            "phase_id": phase_id,
            "available": result.available,
            "blocked_reason": result.blocked_reason,
            "duration_ms": result.duration_ms,
        })
        return ModeResult(
            mode="advisory",
            phase_id=phase_id,
            success=True,
            advisory_note=note,
            blocked_reason=result.blocked_reason,
        )
    except Exception:  # noqa: BLE001
        return run_quarantined(phase_id, traceback.format_exc(), context)


def run_controlled(
    phase_id: str,
    context: dict | None = None,
) -> ModeResult:
    """
    Controlled mode: allowlist + kill_switch + budget guard + dry_run_only (MVP).
    Returns blocked ModeResult if any guard fails.
    """
    try:
        from .feature_flags import (
            is_controlled_enabled,
            is_kill_switch_active,
            get_allowlist_phases,
        )
        from .adapter import run_gstack_controlled_execution
        from .metrics_writer import write_metric

        if not is_controlled_enabled():
            return ModeResult(
                mode="controlled",
                phase_id=phase_id,
                success=False,
                blocked_reason="controlled mode not enabled in feature_flags",
            )
        if is_kill_switch_active():
            return ModeResult(
                mode="controlled",
                phase_id=phase_id,
                success=False,
                blocked_reason="kill_switch is active — controlled execution prevented",
            )
        if phase_id not in get_allowlist_phases():
            return ModeResult(
                mode="controlled",
                phase_id=phase_id,
                success=False,
                blocked_reason=f"phase '{phase_id}' not in allowlist_phases",
            )

        ctx = context or {}
        result = run_gstack_controlled_execution(phase_id, ctx, dry_run_only=True)
        write_metric("controlled", {
            "phase_id": phase_id,
            "available": result.available,
            "blocked_reason": result.blocked_reason,
            "duration_ms": result.duration_ms,
            "dry_run_only": True,
        })
        return ModeResult(
            mode="controlled",
            phase_id=phase_id,
            success=not bool(result.blocked_reason),
            blocked_reason=result.blocked_reason,
            dry_run_only=True,
            evidence={"adapter_result": {
                "available": result.available,
                "exit_code": result.exit_code,
                "blocked_reason": result.blocked_reason,
                "duration_ms": result.duration_ms,
            }},
        )
    except Exception:  # noqa: BLE001
        return run_quarantined(phase_id, traceback.format_exc(), context)


def run_quarantined(
    phase_id: str,
    error: Any = "",
    context: dict | None = None,
) -> ModeResult:
    """
    Quarantined: failure isolation. Record evidence. Hermes original chain continues.
    Requires manual human reset to exit quarantined state.
    """
    error_str = str(error) if not isinstance(error, str) else error
    try:
        from .metrics_writer import write_metric
        from .metrics_redaction import redact_string
        write_metric("quarantined", {
            "phase_id": phase_id,
            "error": redact_string(error_str[:500]),
        })
    except Exception:  # noqa: BLE001
        pass

    return ModeResult(
        mode="quarantined",
        phase_id=phase_id,
        success=False,
        blocked_reason="quarantined — manual human reset required",
        evidence={"error_summary": error_str[:200]},
    )
