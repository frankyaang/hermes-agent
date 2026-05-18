"""
Rollback — documents and verifies the rollback procedure.
generate_rollback_evidence() produces a structured report
confirming the system state after rollback.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from .observability import log_rollback


def _gateway_diff_clean() -> bool:
    """Return True if gateway/* has no uncommitted changes."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "gateway/"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == ""


def generate_rollback_evidence(reason: str = "manual") -> dict[str, Any]:
    """
    Produce a rollback evidence report.
    Call this AFTER performing the rollback steps.
    """
    log_rollback(reason)

    gstack_control_exists = (
        Path(__file__).parent.exists()
    )
    gateway_clean = _gateway_diff_clean()
    hermes_home = get_hermes_home()
    metrics_dir = hermes_home / "gstack_control" / "metrics"
    metrics_exist = metrics_dir.exists()

    evidence: dict[str, Any] = {
        "report_type": "gstack_control_rollback_evidence",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "reason": reason,
        "checks": {
            "gstack_control_module_present": gstack_control_exists,
            "gateway_diff_clean": gateway_clean,
            "metrics_dir_exists": metrics_exist,
        },
        "instructions": [
            "1. Confirm feature_flags.enabled=False (or module deleted)",
            "2. Run: git diff gateway/  (must be empty)",
            "3. Confirm ~/.hermes/config.yaml is unchanged",
            "4. Run: rm -rf agent_system/gstack_control/",
            "5. Run: git checkout agent_system/readiness_manifest.json",
            f"6. Run: rm -rf {metrics_dir}",
            "7. Run: rm -rf agent_system/tests/agent_system/test_gstack_control_*.py",
            "8. Run: scripts/run_tests.sh  (must be 0 failures)",
        ],
        "hermes_home": str(hermes_home),
    }

    out_dir = hermes_home / "gstack_control" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"rollback_{ts}.json"
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return evidence
