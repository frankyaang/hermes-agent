"""
Metrics writer — persists redacted metrics under $HERMES_HOME/gstack_control/metrics/.
All data passes through metrics_redaction before any write.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from .metrics_redaction import redact_dict


def _metrics_dir() -> Path:
    # All paths go through get_hermes_home() — never a hardcoded home subpath.
    p = get_hermes_home() / "gstack_control" / "metrics"
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_metric(name: str, data: dict[str, Any]) -> Path:
    """Write a redacted metric JSON file. Returns the written path."""
    clean = redact_dict(data)
    ts = int(time.time() * 1000)
    filename = f"{name}_{ts}.json"
    path = _metrics_dir() / filename
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return path


def write_dry_run_metric(record_dict: dict[str, Any]) -> Path:
    return write_metric("dry_run", record_dict)
