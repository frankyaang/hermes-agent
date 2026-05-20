#!/usr/bin/env python3
"""Upgrade Preflight Hard Gate for Hermes Agent-System.

Reads the live status report. If upgrade_allowed=false, exits with code 1.
No secrets are printed.

Usage:
    python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes

Exit codes:
    0 — upgrade_allowed=true (all gates passed)
    1 — upgrade_allowed=false (blockers remain)
    2 — internal error (report could not be built)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.status_report import build_status_report


_REDACTED_FIELDS = {
    "api_key", "access_token", "refresh_token", "id_token",
    "authorization", "bearer", "password", "secret", "token",
}


def _safe_report(report: dict) -> dict:
    """Return a copy of report with no secret values printed."""
    return {
        "overall_status": report.get("overall_status", "unknown"),
        "primary_blocker_status": report.get("primary_blocker_status", ""),
        "upgrade_allowed": bool(report.get("upgrade_allowed")),
        "missing_evidence": list(report.get("missing_evidence") or []),
        "next_required_actions": list(report.get("next_required_actions") or []),
        "system_gates": (report.get("upgrade_preflight") or {}).get("system_gates", {}),
        "gateway_smoke_completed": (report.get("gateway_smoke") or {}).get("completed_count", 0),
        "gateway_smoke_required": (report.get("gateway_smoke") or {}).get("required_count", 7),
        "run_evidence_count": (report.get("run_evidence") or {}).get("count", 0),
        "memory_event_count": (report.get("operational_evidence") or {}).get("event_count", 0),
        "gstack_adapter_available": (report.get("gstack") or {}).get("adapter_available", False),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes Agent-System upgrade preflight hard gate"
    )
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output machine-readable JSON only",
    )
    args = parser.parse_args()

    hermes_home = Path(args.hermes_home).expanduser()
    repo_root = Path(args.repo_root).expanduser()

    try:
        report = build_status_report(hermes_home=hermes_home, repo_root=repo_root)
    except Exception as exc:
        output = {
            "upgrade_allowed": False,
            "overall_status": "error",
            "error": str(exc),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 2

    safe = _safe_report(report)
    upgrade_allowed: bool = safe["upgrade_allowed"]

    if args.json_output:
        print(json.dumps(safe, ensure_ascii=False, indent=2))
    else:
        _print_preflight(safe)

    if not upgrade_allowed:
        return 1
    return 0


def _print_preflight(safe: dict) -> None:
    print("=== Hermes Agent-System Upgrade Preflight ===\n")
    print(f"  overall_status        : {safe['overall_status']}")
    print(f"  primary_blocker_status: {safe['primary_blocker_status']}")
    print(f"  upgrade_allowed       : {safe['upgrade_allowed']}")
    print(f"  gateway_smoke         : {safe['gateway_smoke_completed']}/{safe['gateway_smoke_required']} routes")
    print(f"  run_evidence          : {safe['run_evidence_count']} records")
    print(f"  memory_events         : {safe['memory_event_count']} (required: 50)")
    print(f"  gstack_adapter        : {'available' if safe['gstack_adapter_available'] else 'not available'}")

    missing = safe.get("missing_evidence") or []
    if missing:
        print("\n  Missing evidence (blockers):")
        for item in missing:
            code = item.get("failure_code", "unknown")
            reason = item.get("reason", "")
            detail = item.get("detail", "")
            print(f"    - [{code}] {reason}")
            if detail:
                print(f"        detail: {detail}")

    actions = safe.get("next_required_actions") or []
    if actions:
        print("\n  Next required actions:")
        for action in actions:
            print(f"    * {action}")

    print()
    if safe["upgrade_allowed"]:
        print("PREFLIGHT PASSED — upgrade_allowed=true")
    else:
        print("PREFLIGHT FAILED — upgrade_allowed=false")
        print("\n当前不能升级 Hermes，因为 upgrade_allowed=false。")


if __name__ == "__main__":
    raise SystemExit(main())
