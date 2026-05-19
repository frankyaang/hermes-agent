#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.status_report import acceptance_report_path, build_status_report


VALIDATION_COMMANDS = [
    "python3 scripts/check_agent_system_readiness.py",
    "python3 scripts/smoke_agent_system_business_routes.py",
    "python3 scripts/smoke_agent_system_sedimentation.py --hermes-home /tmp/hermes_sedimentation_smoke_final",
    "python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes",
    "python3 scripts/snapshot_agent_system_production_config.py",
    "python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes",
    "python3 scripts/write_agent_system_acceptance_report.py --hermes-home /Users/frank/.hermes",
    "scripts/run_tests.sh tests/agent_system/ -q",
    "git diff --check",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Agent-System acceptance report")
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--min-events", type=int, default=50)
    args = parser.parse_args()

    hermes_home = Path(args.hermes_home).expanduser()
    repo_root = Path(args.repo_root).expanduser()
    initial_status = build_status_report(
        hermes_home=hermes_home,
        repo_root=repo_root,
        min_events=args.min_events,
    )
    path = acceptance_report_path(hermes_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _build_acceptance_report(initial_status),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    final_status = build_status_report(
        hermes_home=hermes_home,
        repo_root=repo_root,
        min_events=args.min_events,
    )
    report = _build_acceptance_report(final_status)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "path": str(path),
                "overall_status": report["overall_status"],
                "upgrade_allowed": report["upgrade_allowed"],
                "primary_blocker_status": report["primary_blocker_status"],
                "missing_evidence": report["missing_evidence"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _build_acceptance_report(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git": status.get("git", {}),
        "overall_status": status.get("overall_status", ""),
        "primary_blocker_status": status.get("primary_blocker_status", ""),
        "upgrade_allowed": bool(status.get("upgrade_allowed", False)),
        "readiness": status.get("readiness", {}),
        "operational_evidence": status.get("operational_evidence", {}),
        "gateway_smoke": status.get("gateway_smoke", {}),
        "gstack": status.get("gstack", {}),
        "production_config_snapshot": status.get("production_config_snapshot", {}),
        "evidence_gate": status.get("evidence_gate", {}),
        "missing_evidence": status.get("missing_evidence", []),
        "next_required_actions": status.get("next_required_actions", []),
        "validation_commands": VALIDATION_COMMANDS,
        "operator_note": (
            "This report records the current gate decision only. It does not run real "
            "Gateway/Feishu smoke, install gstack, migrate secrets, or promote production state."
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
