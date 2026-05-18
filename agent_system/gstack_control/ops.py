"""
GStack Control operations entrypoints.

All functions return sanitized dicts (no tokens/secrets).
CLI usage: python -m agent_system.gstack_control.ops <command>
"""
from __future__ import annotations

import json
import sys
from typing import Any


def status() -> dict[str, Any]:
    """Return current gstack_control status (enabled, mode, adapter, kill_switch, phases)."""
    from .feature_flags import (
        is_enabled, get_mode, is_blocking_allowed,
        is_controlled_enabled, is_kill_switch_active,
        get_allowlist_phases, get_budget_limit_tokens, get_max_runtime_seconds,
    )
    from .phase_registry import list_phases, list_known_commands
    from .adapter import detect_gstack

    phases_info = [
        {"id": p.id, "label": p.label, "risk_level": p.risk_level,
         "gstack_command": p.gstack_command, "production_ready": p.production_ready}
        for p in list_phases()
    ]
    return {
        "enabled": is_enabled(),
        "mode": get_mode(),
        "allow_blocking": is_blocking_allowed(),
        "controlled": is_controlled_enabled(),
        "kill_switch": is_kill_switch_active(),
        "budget_limit_tokens": get_budget_limit_tokens(),
        "max_runtime_seconds": get_max_runtime_seconds(),
        "allowlist_phases": get_allowlist_phases(),
        "adapter_available": detect_gstack(),
        "known_commands": list_known_commands(),
        "phases": phases_info,
    }


def smoke() -> dict[str, Any]:
    """Run adapter detection and dry-run to verify CLI availability."""
    from .adapter import detect_gstack, run_gstack_dry_run
    from .phase_registry import list_phases

    available = detect_gstack()
    results = []
    for phase in list_phases():
        result = run_gstack_dry_run(phase.id)
        results.append({
            "phase_id": phase.id,
            "gstack_command": phase.gstack_command,
            "available": result.available,
            "blocked_reason": result.blocked_reason,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
        })
    return {
        "adapter_available": available,
        "blocked": not available,
        "blocked_reason": "" if available else "gstack CLI not found at PATH",
        "phase_smoke": results,
    }


def report() -> dict[str, Any]:
    """Aggregate status, smoke, evidence, and readiness matrix."""
    return {
        "status": status(),
        "smoke": smoke(),
        "evidence": _load_evidence(),
    }


def metrics(limit: int = 20) -> dict[str, Any]:
    """Return last N sanitized metric entries from HERMES_HOME/gstack_control/metrics/."""
    from hermes_constants import get_hermes_home  # type: ignore[import]
    from .metrics_redaction import redact_string

    metrics_dir = get_hermes_home() / "gstack_control" / "metrics"
    if not metrics_dir.exists():
        return {"entries": [], "count": 0, "metrics_dir": str(metrics_dir)}

    files = sorted(metrics_dir.glob("*.json"), reverse=True)[:limit]
    entries = []
    for f in files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            # Redact any string values
            sanitized = {
                k: redact_string(v) if isinstance(v, str) else v
                for k, v in raw.items()
            }
            entries.append(sanitized)
        except Exception:  # noqa: BLE001
            pass
    return {"entries": entries, "count": len(entries), "metrics_dir": str(metrics_dir)}


def rollback_report() -> dict[str, Any]:
    """Generate rollback evidence and steps."""
    from .rollback import generate_rollback_evidence
    return generate_rollback_evidence()


def _load_evidence() -> dict[str, Any]:
    try:
        from .evidence_report import generate_acceptance_report
        return generate_acceptance_report()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _main() -> None:
    commands = {
        "status": status,
        "smoke": smoke,
        "report": report,
        "metrics": metrics,
        "rollback-report": rollback_report,
    }
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    fn = commands.get(cmd)
    if fn is None:
        print(f"Unknown command: {cmd}. Available: {list(commands)}", file=sys.stderr)
        sys.exit(1)
    result = fn()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    _main()
