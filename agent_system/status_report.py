from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_system.capability_readiness import load_readiness_manifest
from agent_system.evidence_gate import evaluate_evidence_gate
from agent_system.operational_evidence import REQUIRED_GATEWAY_SMOKE_ROUTES, summarize_operational_evidence
from agent_system.production_config_snapshot import (
    config_snapshot_path,
    load_production_config_snapshot,
)
from agent_system.run_evidence import (
    gateway_smoke_path,
    list_run_evidence,
    load_gateway_smoke,
)


ACCEPTANCE_REPORT_FILENAME = "latest_acceptance_report.json"


def acceptance_report_path(hermes_home: Path) -> Path:
    return Path(hermes_home).expanduser() / "agent_system" / "evidence" / ACCEPTANCE_REPORT_FILENAME


def load_acceptance_report(hermes_home: Path) -> dict[str, Any] | None:
    path = acceptance_report_path(hermes_home)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def build_status_report(
    *,
    hermes_home: Path,
    repo_root: Path,
    min_events: int = 50,
) -> dict[str, Any]:
    hermes_home = Path(hermes_home).expanduser()
    repo_root = Path(repo_root)
    readiness_summary = summarize_readiness(repo_root)
    operational_summary = summarize_operational_evidence(hermes_home, min_events=min_events)
    gateway_smoke = load_gateway_smoke(hermes_home)
    run_evidence = list_run_evidence(hermes_home)
    gstack_status = summarize_gstack_status()
    config_snapshot = load_production_config_snapshot(hermes_home)
    acceptance_report = load_acceptance_report(hermes_home)
    gate = evaluate_evidence_gate(
        readiness_summary=readiness_summary,
        operational_summary=operational_summary,
        gateway_smoke=gateway_smoke,
        gstack_status=gstack_status,
        config_snapshot=config_snapshot,
        acceptance_report=acceptance_report,
    )
    gateway_completed = {
        str(item.get("route") or item.get("pipeline_id") or "")
        for item in gateway_smoke.get("routes", [])
        if str(item.get("status") or "").lower() in {"ok", "passed", "completed", "success"}
    }
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hermes_home": str(hermes_home),
        "git": _git_info(repo_root),
        "overall_status": gate["overall_status"],
        "primary_blocker_status": gate.get("primary_blocker_status", ""),
        "upgrade_allowed": bool(gate["upgrade_allowed"]),
        "readiness": readiness_summary,
        "operational_evidence": {
            "status": operational_summary.get("status"),
            "event_count": operational_summary.get("event_count", 0),
            "memory_event_required_count": min_events,
            "staging_count": operational_summary.get("staging_count", 0),
            "project_process_count": operational_summary.get("project_process_count", 0),
            "checks": operational_summary.get("checks", {}),
            "gateway_smoke_routes_missing": operational_summary.get("gateway_smoke_routes_missing", []),
        },
        "gateway_smoke": {
            "path": str(gateway_smoke_path(hermes_home)),
            "exists": gateway_smoke_path(hermes_home).exists(),
            "completed_count": len(gateway_completed),
            "required_count": len(REQUIRED_GATEWAY_SMOKE_ROUTES),
            "completed_routes": sorted(gateway_completed),
            "missing_routes": [r for r in REQUIRED_GATEWAY_SMOKE_ROUTES if r not in gateway_completed],
        },
        "run_evidence": {
            "path": str(hermes_home / "agent_system" / "evidence" / "run_evidence.jsonl"),
            "count": len(run_evidence),
        },
        "gstack": gstack_status,
        "production_config_snapshot": {
            "path": str(config_snapshot_path(hermes_home)),
            "exists": config_snapshot is not None,
            "secret_hygiene": (config_snapshot or {}).get("secret_hygiene", {}),
        },
        "acceptance_report": {
            "path": str(acceptance_report_path(hermes_home)),
            "exists": acceptance_report is not None,
        },
        "evidence_gate": gate,
        "missing_evidence": gate["missing_evidence"],
        "next_required_actions": gate["next_required_actions"],
    }


def summarize_readiness(repo_root: Path) -> dict[str, Any]:
    manifest = load_readiness_manifest(repo_root)
    routes = manifest.get("routes", [])
    skills = manifest.get("skills", [])
    ready_routes = [str(r.get("pipeline_id")) for r in routes if r.get("readiness_state") == "ready"]
    non_ready_routes = [str(r.get("pipeline_id")) for r in routes if r.get("readiness_state") == "non_ready"]
    unknown_routes = [str(r.get("pipeline_id")) for r in routes if r.get("readiness_state") == "unknown"]
    return {
        "ready_routes": ready_routes,
        "non_ready_routes": non_ready_routes,
        "unknown_routes": unknown_routes,
        "ready_route_count": len(ready_routes),
        "non_ready_route_count": len(non_ready_routes),
        "unknown_route_count": len(unknown_routes),
        "ready_skill_count": sum(1 for s in skills if s.get("readiness_state") == "ready"),
        "non_ready_skill_count": sum(1 for s in skills if s.get("readiness_state") == "non_ready"),
        "unknown_skill_count": sum(1 for s in skills if s.get("readiness_state") == "unknown"),
    }


def summarize_gstack_status() -> dict[str, Any]:
    try:
        from agent_system.gstack_control.ops import smoke, status

        status_payload = status()
        smoke_payload = smoke()
    except Exception as exc:
        return {
            "enabled": False,
            "mode": "error",
            "adapter_available": False,
            "blocked": True,
            "blocked_reason": f"gstack status unavailable: {exc}",
        }
    return {
        "enabled": bool(status_payload.get("enabled")),
        "mode": status_payload.get("mode", "disabled"),
        "allow_blocking": bool(status_payload.get("allow_blocking")),
        "controlled": bool(status_payload.get("controlled")),
        "kill_switch": bool(status_payload.get("kill_switch")),
        "adapter_available": bool(status_payload.get("adapter_available")),
        "blocked": bool(smoke_payload.get("blocked")),
        "blocked_reason": smoke_payload.get("blocked_reason", ""),
        "known_commands": status_payload.get("known_commands", []),
    }


def _git_info(repo_root: Path) -> dict[str, str]:
    return {
        "branch": _git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": _git(repo_root, ["rev-parse", "HEAD"]),
    }


def _git(repo_root: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""
