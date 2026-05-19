"""Sedimentation governance feature flags — ALL OFF by default (shadow mode).

Import and check these flags before any governance capability is exercised
in production paths. Tests may monkeypatch individual flags.
"""
from __future__ import annotations

import os

# gstack output → SedimentationEvent pipeline
# When OFF: gstack_bridge.route() is a no-op
GSTACK_SEDIMENTATION_ENABLED: bool = (
    os.environ.get("GSTACK_SEDIMENTATION_ENABLED", "").strip().lower() in ("1", "true", "yes")
)

# session_capture auto-trigger on every agent turn
# When OFF: capture_turn() must be called explicitly
SESSION_CAPTURE_AUTO_ENABLED: bool = (
    os.environ.get("SESSION_CAPTURE_AUTO_ENABLED", "").strip().lower() in ("1", "true", "yes")
)

# usage_hint injection on knowledge_query results
# When OFF: knowledge_query returns content without hint prefix
USAGE_HINT_INJECTION_ENABLED: bool = (
    os.environ.get("USAGE_HINT_INJECTION_ENABLED", "").strip().lower() in ("1", "true", "yes")
)
