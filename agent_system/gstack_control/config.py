"""
GStack Control config loader.

Reads the optional `agent_system.gstack_control` block from the Hermes
user config (via hermes_cli.config.load_config). Returns safe defaults
when the block is absent or the config cannot be loaded.

CONTRACT:
- Never modifies ~/.hermes/config.yaml
- Config missing → safe defaults (enabled=False, mode=disabled)
- Any exception → safe defaults (fail-closed)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GstackConfig:
    enabled: bool = False
    mode: str = "disabled"
    allow_blocking: bool = False
    controlled: bool = False
    kill_switch: bool = True
    budget_limit_tokens: int = 4000
    max_runtime_seconds: int = 30
    allowlist_phases: list[str] = field(default_factory=list)
    use_real_gstack: bool = False


_SAFE_DEFAULTS = GstackConfig()


def load_gstack_config() -> GstackConfig:
    """
    Load gstack_control config from Hermes user config.
    Falls back to safe defaults on any error (fail-closed).
    """
    try:
        from hermes_cli.config import load_config  # type: ignore[import]
        raw: dict[str, Any] = load_config()
        block: dict[str, Any] = (
            raw.get("agent_system", {}).get("gstack_control", {})
        )
        if not block:
            return _SAFE_DEFAULTS

        allowlist = block.get("allowlist_phases", [])
        cfg = GstackConfig(
            enabled=bool(block.get("enabled", False)),
            mode=str(block.get("mode", "disabled")),
            allow_blocking=bool(block.get("allow_blocking", False)),
            controlled=bool(block.get("controlled", False)),
            kill_switch=bool(block.get("kill_switch", True)),
            budget_limit_tokens=int(block.get("budget_limit_tokens", 4000)),
            max_runtime_seconds=int(block.get("max_runtime_seconds", 30)),
            allowlist_phases=list(allowlist) if isinstance(allowlist, list) else [],
            use_real_gstack=bool(block.get("use_real_gstack", False)),
        )
        # Propagate sedimentation_enabled to feature_flags (runtime override)
        if block.get("sedimentation_enabled"):
            try:
                from agent_system.sedimentation.feature_flags import set_flag
                set_flag("GSTACK_SEDIMENTATION_ENABLED", True)
            except Exception:
                pass
        return cfg
    except Exception:  # noqa: BLE001
        return _SAFE_DEFAULTS
