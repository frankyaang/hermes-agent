"""
Evidence report — generates Go/No-Go acceptance report for the MVP skeleton.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from .feature_flags import GSTACK_FEATURE_FLAGS
from .phase_registry import list_phases


def _check_no_literal_gstack_path() -> bool:
    """Return True if no hardcoded gstack home path exists in gstack_control source."""
    src = Path(__file__).parent
    # Search pattern split to avoid self-match; exclude __pycache__ bytecode
    _pattern = "~/" + ".gstack"
    result = subprocess.run(
        ["grep", "-r", "--include=*.py", "--include=*.yaml", "--include=*.json",
         _pattern, str(src)],
        capture_output=True,
        text=True,
    )
    return result.returncode != 0  # grep exits 1 when no match found


def generate_acceptance_report() -> dict[str, Any]:
    """Generate a structured Go/No-Go acceptance report."""
    phases = [{"id": p.id, "production_ready": p.production_ready} for p in list_phases()]
    no_literal_path = _check_no_literal_gstack_path()

    report: dict[str, Any] = {
        "report_type": "gstack_control_acceptance",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "verdict": "GO" if no_literal_path else "NO-GO",
        "checks": {
            "feature_flags_all_off": all(
                not v if isinstance(v, bool) else v in ("disabled", False)
                for k, v in GSTACK_FEATURE_FLAGS.items()
                if k not in ("mode",)
            ),
            "mode_is_disabled": GSTACK_FEATURE_FLAGS.get("mode") == "disabled",
            "allow_blocking_false": not GSTACK_FEATURE_FLAGS.get("allow_blocking"),
            "use_real_gstack_false": not GSTACK_FEATURE_FLAGS.get("use_real_gstack"),
            "browser_daemon_false": not GSTACK_FEATURE_FLAGS.get("browser_daemon"),
            "gbrain_false": not GSTACK_FEATURE_FLAGS.get("gbrain"),
            "no_literal_gstack_path": no_literal_path,
            "phases_not_production_ready": all(not p["production_ready"] for p in phases),
        },
        "phases": phases,
        "hermes_home": str(get_hermes_home()),
    }
    return report


def save_acceptance_report() -> Path:
    report = generate_acceptance_report()
    out_dir = get_hermes_home() / "gstack_control" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"acceptance_{ts}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
