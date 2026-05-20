#!/usr/bin/env python3
"""Blocker Control Plane for Hermes Agent-System upgrade readiness.

Reads the live status report (via build_status_report) and emits per-blocker
details: category, owner, next_command, verification_command, rollback_note,
risk_level.

Usage:
    python3 scripts/agent_system_blockers.py --hermes-home /Users/frank/.hermes
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.status_report import build_status_report


# ---------------------------------------------------------------------------
# Blocker catalogue — static metadata keyed by failure_code
# ---------------------------------------------------------------------------

_BLOCKER_CATALOGUE: dict[str, dict] = {
    "gateway_smoke_missing": {
        "category": "external_runtime",
        "owner": "feishu_gateway",
        "risk_level": "critical",
        "next_command": (
            "# Run a real Feishu/Gateway message for each ready route, then record:\n"
            "python3 scripts/record_gateway_smoke_evidence.py \\\n"
            "  --hermes-home /Users/frank/.hermes \\\n"
            "  --route <route> --status ok --platform feishu \\\n"
            "  --run-id <run_id> --artifact-path <artifact_path> \\\n"
            "  --audit-log <audit_log_path> --review-summary <review_summary_path>"
        ),
        "verification_command": (
            "python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | "
            "python3 -c \"import sys,json; d=json.load(sys.stdin); "
            "print('gateway_smoke_complete:', d['operational_evidence']['checks']['gateway_smoke_routes_complete'])\""
        ),
        "rollback_note": (
            "Gateway smoke records are append-only in gateway_smoke.json. "
            "To invalidate a bad entry, record the same route with status=blocked and a failure_code. "
            "The evidence gate counts only status=ok entries as passing."
        ),
        "auto_executable": False,
        "requires_real_feishu": True,
    },
    "insufficient_memory_events": {
        "category": "external_runtime",
        "owner": "feishu_gateway",
        "risk_level": "high",
        "next_command": (
            "# Memory events accumulate from real tasks. Enable session capture in staging:\n"
            "# Set SESSION_CAPTURE_AUTO_ENABLED=true in staging environment.\n"
            "# Each real Feishu/Gateway task will emit MemoryEvents.\n"
            "# Check current count:\n"
            "python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes"
        ),
        "verification_command": (
            "python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes | "
            "python3 -c \"import sys,json; d=json.load(sys.stdin); "
            "print('event_count:', d['event_count'], '/ required: 50')\""
        ),
        "rollback_note": (
            "Memory events are append-only. "
            "If a bad event is written, it cannot be deleted without invalidating the JSONL log. "
            "Always write events via dispatch_event() through the dispatcher, not directly."
        ),
        "auto_executable": False,
        "requires_real_feishu": True,
    },
    "gstack_external_evidence_missing": {
        "category": "user_authorization",
        "owner": "user",
        "risk_level": "medium",
        "next_command": (
            "# Option A: Install gstack and produce real external evidence (requires user decision)\n"
            "# See docs/agent-system-gstack-decision-request.md\n\n"
            "# Option B: Keep gstack shadow-only (upgrade_allowed stays false for this blocker)\n"
            "# gstack remains advisory; this blocker persists until real gstack evidence appears."
        ),
        "verification_command": (
            "python3 scripts/check_agent_system_operational_evidence.py --hermes-home /Users/frank/.hermes | "
            "python3 -c \"import sys,json; d=json.load(sys.stdin); "
            "print('covers_gstack_external_evidence:', d['checks']['covers_gstack_external_evidence'])\""
        ),
        "rollback_note": (
            "gstack is currently shadow/advisory/fail-closed. "
            "Installing gstack does not change Hermes runtime behaviour unless "
            "GSTACK_SEDIMENTATION_ENABLED=true. "
            "Rollback: uninstall gstack or set kill_switch=true in gstack config."
        ),
        "auto_executable": False,
        "requires_real_feishu": False,
    },
    "config_secret_detected": {
        "category": "user_authorization",
        "owner": "user",
        "risk_level": "critical",
        "next_command": (
            "# Do NOT migrate automatically. Read docs first:\n"
            "# cat docs/agent-system-secret-migration-request.md\n\n"
            "# After migrating secrets to .env / credential store, regenerate snapshot:\n"
            "python3 scripts/snapshot_agent_system_production_config.py\n"
            "python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes"
        ),
        "verification_command": (
            "python3 scripts/snapshot_agent_system_production_config.py | "
            "python3 -c \"import sys,json; d=json.load(sys.stdin); "
            "print('config_secret_detected:', d.get('config_secret_detected'))\""
        ),
        "rollback_note": (
            "If migration causes auth failures, restore the original config from backup "
            "and set the keys back. "
            "The config snapshot is re-generated on demand and does not affect runtime directly."
        ),
        "auto_executable": False,
        "requires_real_feishu": False,
    },
    "gstack_cli_missing": {
        "category": "user_authorization",
        "owner": "user",
        "risk_level": "medium",
        "next_command": (
            "# Do NOT auto-install. Read the decision doc first:\n"
            "# cat docs/agent-system-gstack-decision-request.md\n\n"
            "# Then choose:\n"
            "# Option A: install gstack at agreed path, run smoke\n"
            "# Option B: keep disabled (gstack_cli_missing stays as blocker)"
        ),
        "verification_command": (
            "python3 -m agent_system.gstack_control.ops status | "
            "python3 -c \"import sys,json; d=json.load(sys.stdin); "
            "print('adapter_available:', d['adapter_available'])\""
        ),
        "rollback_note": (
            "gstack CLI absence is the current safe state (shadow/advisory/fail-closed). "
            "If installed and causing issues, remove from PATH or set kill_switch=true in gstack config."
        ),
        "auto_executable": False,
        "requires_real_feishu": False,
    },
    "human_gate_not_drilled": {
        "category": "user_authorization",
        "owner": "user",
        "risk_level": "high",
        "next_command": (
            "# Follow the drill scenarios in:\n"
            "# cat docs/agent-system-human-gate-drill-plan.md\n\n"
            "# For each scenario, record evidence:\n"
            "python3 scripts/record_run_evidence.py \\\n"
            "  --hermes-home /Users/frank/.hermes \\\n"
            "  --platform feishu --route <route> --status <ok|blocked> \\\n"
            "  --run-id <run_id> --human-gate-json '{\"decision\":\"approved\",\"drilled\":true}'"
        ),
        "verification_command": (
            "python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes | "
            "python3 -c \"import sys,json; d=json.load(sys.stdin); "
            "print('run_evidence_count:', d['run_evidence']['count'])\""
        ),
        "rollback_note": (
            "Run evidence is append-only. Drill records are labelled by human_gate.drilled=true. "
            "They count toward operational evidence but are clearly marked as drill, not production."
        ),
        "auto_executable": False,
        "requires_real_feishu": True,
    },
    "upgrade_preflight_missing": {
        "category": "auto",
        "owner": "claudecode",
        "risk_level": "low",
        "next_command": (
            "python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes"
        ),
        "verification_command": (
            "python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes; "
            "echo \"exit_code: $?\""
        ),
        "rollback_note": (
            "Preflight is read-only — it does not change any state. "
            "Running it multiple times is safe."
        ),
        "auto_executable": True,
        "requires_real_feishu": False,
    },
}


def _build_blocker_entry(
    failure_code: str,
    reason: str,
    detail: str,
    catalogue: dict,
) -> dict:
    return {
        "blocker_code": failure_code,
        "reason": reason,
        "current_evidence": detail,
        "category": catalogue.get("category", "unknown"),
        "owner": catalogue.get("owner", "unknown"),
        "risk_level": catalogue.get("risk_level", "unknown"),
        "auto_executable": catalogue.get("auto_executable", False),
        "requires_real_feishu": catalogue.get("requires_real_feishu", False),
        "next_command": catalogue.get("next_command", ""),
        "verification_command": catalogue.get("verification_command", ""),
        "rollback_note": catalogue.get("rollback_note", ""),
    }


def build_blockers(hermes_home: Path, repo_root: Path) -> dict:
    report = build_status_report(hermes_home=hermes_home, repo_root=repo_root)

    upgrade_allowed: bool = bool(report.get("upgrade_allowed"))
    overall_status: str = report.get("overall_status", "unknown")
    primary_blocker_status: str = report.get("primary_blocker_status", "")

    raw_missing: list[dict] = list(report.get("missing_evidence") or [])

    # Inject human_gate_not_drilled if run_evidence count == 0
    run_evidence_count: int = int((report.get("run_evidence") or {}).get("count", 0))
    has_human_gate_code = any(
        m.get("failure_code") == "human_gate_not_drilled" for m in raw_missing
    )
    if not has_human_gate_code and run_evidence_count == 0:
        raw_missing.append(
            {
                "failure_code": "human_gate_not_drilled",
                "reason": "No run evidence recorded; human gate drill not yet performed",
                "detail": f"run_evidence.count={run_evidence_count}",
            }
        )

    # Always include upgrade_preflight_missing as an auto-executable reminder
    # if upgrade is not allowed
    if not upgrade_allowed:
        raw_missing.append(
            {
                "failure_code": "upgrade_preflight_missing",
                "reason": "preflight_agent_system_upgrade.py must pass before any upgrade attempt",
                "detail": "upgrade_allowed=false; preflight enforces non-0 exit",
            }
        )

    blockers = []
    seen_codes: set[str] = set()
    for item in raw_missing:
        code = item.get("failure_code", "")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        cat_entry = _BLOCKER_CATALOGUE.get(code, {})
        blockers.append(
            _build_blocker_entry(
                failure_code=code,
                reason=item.get("reason", ""),
                detail=item.get("detail", ""),
                catalogue=cat_entry,
            )
        )

    # Sort: critical first, then high, medium, low
    _order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 9}
    blockers.sort(key=lambda b: _order.get(b.get("risk_level", "unknown"), 9))

    # Summarise by category
    by_category: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    for b in blockers:
        cat = b.get("category", "unknown")
        owner = b.get("owner", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1
        by_owner[owner] = by_owner.get(owner, 0) + 1

    return {
        "upgrade_allowed": upgrade_allowed,
        "overall_status": overall_status,
        "primary_blocker_status": primary_blocker_status,
        "blocker_count": len(blockers),
        "by_category": by_category,
        "by_owner": by_owner,
        "blockers": blockers,
        "legend": {
            "auto": "Claude Code can execute without user authorization",
            "user_authorization": "Requires explicit user decision or action",
            "external_runtime": "Requires real Feishu/Gateway environment",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes Agent-System Blocker Control Plane"
    )
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--repo-root", default=str(ROOT))
    args = parser.parse_args()

    hermes_home = Path(args.hermes_home).expanduser()
    repo_root = Path(args.repo_root).expanduser()

    result = build_blockers(hermes_home=hermes_home, repo_root=repo_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result["upgrade_allowed"]:
        print(
            "\n当前不能升级 Hermes，因为 upgrade_allowed=false。"
            f"\n残余 blocker 数量: {result['blocker_count']}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
