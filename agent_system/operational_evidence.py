from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_GATEWAY_SMOKE_ROUTES = (
    "artifact_status_flow",
    "artifact_delivery_flow",
    "doc_publish_flow",
    "insight_flow",
    "dashboard_flow",
    "html_flow",
    "dashboard_from_artifact_flow",
)


def summarize_operational_evidence(
    hermes_home: Path,
    *,
    min_events: int = 50,
) -> dict[str, Any]:
    """Summarize real-runtime evidence for production enablement gates."""
    hermes_home = Path(hermes_home).expanduser()
    events = _read_jsonl(hermes_home / "memory_events" / "events.jsonl")
    staging = _read_jsonl(hermes_home / "staging" / "staging.jsonl")
    project_process = _read_jsonl(hermes_home / "project_process" / "records.jsonl")
    gateway_smoke = _read_gateway_smoke(hermes_home)

    source_counts = Counter(str(e.get("source_type") or "unknown") for e in events)
    risk_counts = Counter(
        str(flag)
        for e in events
        for flag in (e.get("risk_flags") or [])
    )
    source_uris = [str(e.get("source_uri") or "") for e in events]

    gateway_routes = {
        str(item.get("route") or item.get("pipeline_id") or "")
        for item in gateway_smoke.get("routes", [])
        if str(item.get("status") or "").lower() in {"ok", "passed", "completed", "success"}
    }
    missing_gateway_routes = [
        route for route in REQUIRED_GATEWAY_SMOKE_ROUTES if route not in gateway_routes
    ]

    checks = {
        "min_50_real_events": len(events) >= min_events,
        "covers_user_correction": risk_counts.get("user_correction", 0) > 0
        or source_counts.get("user_correction", 0) > 0,
        "covers_tool_failure": risk_counts.get("tool_failure", 0) > 0
        or source_counts.get("write_failure", 0) > 0,
        "covers_permission_unclear": risk_counts.get("permission_unclear", 0) > 0,
        "covers_project_process": bool(project_process)
        or any(str(e.get("recommended_destination") or "") == "project_process" for e in events),
        "covers_gstack_external_evidence": any("hermes://gstack/" in uri for uri in source_uris),
        "staging_has_entries": bool(staging),
        "gateway_smoke_routes_complete": not missing_gateway_routes,
    }

    return {
        "hermes_home": str(hermes_home),
        "status": "ready" if all(checks.values()) else "not_ready",
        "event_count": len(events),
        "staging_count": len(staging),
        "project_process_count": len(project_process),
        "source_type_counts": dict(source_counts),
        "risk_flag_counts": dict(risk_counts),
        "gateway_smoke_path": str(_gateway_smoke_path(hermes_home)),
        "gateway_smoke_exists": _gateway_smoke_path(hermes_home).exists(),
        "gateway_smoke_routes_seen": sorted(gateway_routes),
        "gateway_smoke_routes_missing": missing_gateway_routes,
        "checks": checks,
        "secret_redaction": "no event raw content printed",
    }


def _gateway_smoke_path(hermes_home: Path) -> Path:
    return hermes_home / "agent_system" / "evidence" / "gateway_smoke.json"


def _read_gateway_smoke(hermes_home: Path) -> dict[str, Any]:
    path = _gateway_smoke_path(hermes_home)
    if not path.exists():
        return {"routes": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"routes": []}
    if isinstance(payload, list):
        return {"routes": payload}
    if isinstance(payload, dict):
        routes = payload.get("routes")
        if isinstance(routes, list):
            return payload
        if isinstance(payload.get("feishu_gateway_smoke"), list):
            return {"routes": payload["feishu_gateway_smoke"]}
    return {"routes": []}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
    except Exception:
        return records
    return records
