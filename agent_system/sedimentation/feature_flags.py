"""Sedimentation governance feature flags — ALL OFF by default (shadow mode).

Import and check these flags before any governance capability is exercised
in production paths. Tests may monkeypatch individual flags or reload the module.

Runtime override: call set_flag(name, value) to change a flag without env var
(e.g., driven by load_gstack_config()); survives until module is reloaded.
"""
from __future__ import annotations

import os

_TRUTHY = ("1", "true", "yes")


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


# gstack output → SedimentationEvent pipeline
# When OFF: gstack_bridge.route() is a no-op
GSTACK_SEDIMENTATION_ENABLED: bool = _env_bool("GSTACK_SEDIMENTATION_ENABLED")

# session_capture auto-trigger on every agent turn
# When OFF: capture_turn() must be called explicitly
SESSION_CAPTURE_AUTO_ENABLED: bool = _env_bool("SESSION_CAPTURE_AUTO_ENABLED")

# usage_hint injection on knowledge_query results and memory context blocks
# When OFF: knowledge_query returns content without hint prefix
USAGE_HINT_INJECTION_ENABLED: bool = _env_bool("USAGE_HINT_INJECTION_ENABLED")


_KNOWN_FLAGS = {"GSTACK_SEDIMENTATION_ENABLED", "SESSION_CAPTURE_AUTO_ENABLED", "USAGE_HINT_INJECTION_ENABLED"}


def set_flag(name: str, value: bool) -> None:
    """Override a feature flag at runtime (e.g., driven by load_gstack_config()).

    Modifies the module-level variable. Callers that already imported the flag
    by name (e.g., `from feature_flags import GSTACK_SEDIMENTATION_ENABLED`) will
    not see the change — they should import the module and check the attribute.
    """
    import sys
    if name not in _KNOWN_FLAGS:
        return
    mod = sys.modules[__name__]
    setattr(mod, name, bool(value))
