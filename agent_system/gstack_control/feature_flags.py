"""
GStack Control feature flags — all defaults OFF.
This module has no imports from other gstack_control modules
so it can be safely imported to check flags before any other
gstack_control code is loaded.
"""
from __future__ import annotations

GSTACK_FEATURE_FLAGS: dict[str, object] = {
    # Master switch — when False, all gstack_control code is a no-op.
    "enabled": False,
    # Operating mode. disabled | shadow | advisory | controlled | quarantined
    # blocking is never a default; it requires allow_blocking=True AND explicit human upgrade.
    "mode": "disabled",
    # Safety valve: blocking responses are unconditionally prohibited unless True.
    "allow_blocking": False,
    # Enable controlled mode (allowlist + kill_switch + budget + dry_run).
    # Requires explicit human approval in production; MVP: dry_run_only.
    "controlled": False,
    # Emergency stop: when True, controlled mode is prevented from executing.
    "kill_switch": True,
    # Token budget limit for controlled mode (per-phase execution).
    "budget_limit_tokens": 4000,
    # Max runtime for controlled mode execution (seconds).
    "max_runtime_seconds": 30,
    # Phases explicitly allowlisted for controlled execution. Empty = none allowed.
    "allowlist_phases": [],
    # Do not call the real gstack CLI.
    "use_real_gstack": False,
    # Do not start the browser daemon.
    "browser_daemon": False,
    # Do not connect GBrain.
    "gbrain": False,
    # Do not enable telemetry.
    "telemetry": False,
    # Do not enable proactive mode.
    "proactive_mode": False,
    # Do not enable continuous checkpoint.
    "continuous_checkpoint": False,
}


def get_flag(name: str, default: object = None) -> object:
    """Return the current value of a feature flag."""
    return GSTACK_FEATURE_FLAGS.get(name, default)


def is_enabled() -> bool:
    """Return True only if the master switch is on."""
    return bool(GSTACK_FEATURE_FLAGS.get("enabled", False))


def get_mode() -> str:
    """Return the current operating mode string."""
    return str(GSTACK_FEATURE_FLAGS.get("mode", "disabled"))


def is_blocking_allowed() -> bool:
    """Return True only if blocking has been explicitly enabled."""
    return bool(GSTACK_FEATURE_FLAGS.get("allow_blocking", False))


def is_controlled_enabled() -> bool:
    """Return True only if controlled mode has been explicitly enabled."""
    return bool(GSTACK_FEATURE_FLAGS.get("controlled", False))


def is_kill_switch_active() -> bool:
    """Return True if kill_switch is active (prevents controlled execution)."""
    return bool(GSTACK_FEATURE_FLAGS.get("kill_switch", True))


def get_budget_limit_tokens() -> int:
    return int(GSTACK_FEATURE_FLAGS.get("budget_limit_tokens", 4000))  # type: ignore[arg-type]


def get_max_runtime_seconds() -> int:
    return int(GSTACK_FEATURE_FLAGS.get("max_runtime_seconds", 30))  # type: ignore[arg-type]


def get_allowlist_phases() -> list[str]:
    val = GSTACK_FEATURE_FLAGS.get("allowlist_phases", [])
    return list(val) if isinstance(val, list) else []
