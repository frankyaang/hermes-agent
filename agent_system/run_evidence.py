from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_system.failure_taxonomy import normalize_failure_code, require_failure_code
from agent_system.operational_evidence import REQUIRED_GATEWAY_SMOKE_ROUTES


SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "bearer",
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "secret",
    "password",
}

VALID_STATUSES = {"ok", "failed", "blocked"}
VALID_RUN_EVIDENCE_ROUTES = set(REQUIRED_GATEWAY_SMOKE_ROUTES) | {"report_revision_flow"}


def evidence_dir(hermes_home: Path) -> Path:
    return Path(hermes_home).expanduser() / "agent_system" / "evidence"


def run_evidence_path(hermes_home: Path) -> Path:
    return evidence_dir(hermes_home) / "run_evidence.jsonl"


def gateway_smoke_path(hermes_home: Path) -> Path:
    return evidence_dir(hermes_home) / "gateway_smoke.json"


def make_run_evidence_record(
    *,
    platform: str,
    route: str,
    status: str,
    message_id: str = "",
    session_id: str = "",
    run_id: str = "",
    failure_code: str = "",
    artifact_path: str = "",
    audit_log: str = "",
    review_summary: str = "",
    model_routing: dict[str, Any] | None = None,
    memory_event_ids: list[str] | None = None,
    staging_ids: list[str] | None = None,
    human_gate: dict[str, Any] | None = None,
    created_at: str = "",
) -> dict[str, Any]:
    route = _normalize_route(route)
    status = _normalize_status(status)
    if status in {"failed", "blocked"}:
        failure_code = require_failure_code(failure_code)
    else:
        failure_code = normalize_failure_code(failure_code)
    record = {
        "id": str(uuid.uuid4()),
        "platform": platform or "unknown",
        "message_id": message_id,
        "session_id": session_id,
        "route": route,
        "run_id": run_id,
        "status": status,
        "failure_code": failure_code,
        "artifact_path": artifact_path,
        "audit_log": audit_log,
        "review_summary": review_summary,
        "model_routing": _default_model_routing(model_routing),
        "memory_event_ids": list(memory_event_ids or []),
        "staging_ids": list(staging_ids or []),
        "human_gate": _default_human_gate(human_gate),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    return redact(record)


def append_run_evidence(hermes_home: Path, record: dict[str, Any]) -> Path:
    path = run_evidence_path(hermes_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(redact(record), ensure_ascii=False, default=str) + "\n")
    return path


def list_run_evidence(hermes_home: Path) -> list[dict[str, Any]]:
    return _read_jsonl(run_evidence_path(hermes_home))


def make_gateway_smoke_record(
    *,
    route: str,
    status: str,
    platform: str = "feishu",
    run_id: str = "",
    failure_code: str = "",
    artifact_path: str = "",
    audit_log: str = "",
    review_summary: str = "",
    created_at: str = "",
) -> dict[str, Any]:
    route = _normalize_route(route)
    if route not in REQUIRED_GATEWAY_SMOKE_ROUTES:
        raise ValueError(f"unsupported gateway smoke route: {route}")
    status = _normalize_status(status)
    if status in {"failed", "blocked"}:
        failure_code = require_failure_code(failure_code)
    else:
        failure_code = normalize_failure_code(failure_code)
    return redact(
        {
            "route": route,
            "platform": platform or "feishu",
            "status": status,
            "run_id": run_id,
            "failure_code": failure_code,
            "artifact_path": artifact_path,
            "audit_log": audit_log,
            "review_summary": review_summary,
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        }
    )


def record_gateway_smoke(hermes_home: Path, record: dict[str, Any]) -> Path:
    path = gateway_smoke_path(hermes_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = load_gateway_smoke(hermes_home)
    routes = [
        item for item in payload.get("routes", [])
        if item.get("route") != record.get("route")
    ]
    routes.append(redact(record))
    payload = {
        "schema_version": "1.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "routes": sorted(routes, key=lambda item: str(item.get("route") or "")),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_gateway_smoke(hermes_home: Path) -> dict[str, Any]:
    path = gateway_smoke_path(hermes_home)
    if not path.exists():
        return {"schema_version": "1.0", "routes": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": "1.0", "routes": []}
    if isinstance(payload, list):
        return {"schema_version": "1.0", "routes": payload}
    if isinstance(payload, dict):
        routes = payload.get("routes")
        if isinstance(routes, list):
            return payload
    return {"schema_version": "1.0", "routes": []}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _normalize_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}, got {status!r}")
    return normalized


def _normalize_route(route: str) -> str:
    normalized = (route or "").strip()
    if normalized not in VALID_RUN_EVIDENCE_ROUTES:
        raise ValueError(f"route must be one of {sorted(VALID_RUN_EVIDENCE_ROUTES)}, got {route!r}")
    return normalized


def _default_model_routing(value: dict[str, Any] | None) -> dict[str, Any]:
    base = {"planning": "", "execution": "", "audit": "", "fallback": ""}
    if isinstance(value, dict):
        base.update({k: value.get(k, "") for k in base})
    return base


def _default_human_gate(value: dict[str, Any] | None) -> dict[str, Any]:
    base = {"required": False, "decision": "", "actor": "", "timestamp": ""}
    if isinstance(value, dict):
        base.update({k: value.get(k, base[k]) for k in base})
    return base


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    if lower.startswith("has_"):
        return False
    return any(part in lower for part in SENSITIVE_KEYS)


def _redact_string(value: str) -> str:
    lowered = value.lower()
    if any(marker in lowered for marker in ("authorization:", "bearer ", "sk-", "access_token", "refresh_token")):
        return "[REDACTED]"
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records
