from __future__ import annotations

from typing import Any

from agent_system.failure_taxonomy import (
    ACCEPTANCE_REPORT_MISSING,
    CONFIG_SECRET_DETECTED,
    CONFIG_SNAPSHOT_MISSING,
    GATEWAY_SMOKE_MISSING,
    GSTACK_CLI_MISSING,
    GSTACK_EXTERNAL_EVIDENCE_MISSING,
    INSUFFICIENT_MEMORY_EVENTS,
    ROUTE_MISCLASSIFIED,
)
from agent_system.operational_evidence import REQUIRED_GATEWAY_SMOKE_ROUTES


GATE_DECLARED = "declared"
GATE_CONTRACT_TESTED = "contract_tested"
GATE_LOCAL_SMOKE_PASSED = "local_smoke_passed"
GATE_GATEWAY_SMOKE_PASSED = "gateway_smoke_passed"
GATE_OPERATIONALLY_VERIFIED = "operationally_verified"
GATE_PRODUCTION_READY = "production_ready"
GATE_BLOCKED = "blocked"

STATUS_LOCAL_READY = "local_ready_not_operationally_verified"
STATUS_GATEWAY_INCOMPLETE = "gateway_smoke_incomplete"
STATUS_SEDIMENTATION_INSUFFICIENT = "sedimentation_insufficient_events"
STATUS_GSTACK_SHADOW_ONLY = "gstack_shadow_only"
STATUS_EXTERNAL_BLOCKED = "external_dependency_blocked"
STATUS_PRODUCTION_READY = "production_ready"


def evaluate_evidence_gate(
    readiness_summary: dict[str, Any],
    operational_summary: dict[str, Any],
    gateway_smoke: dict[str, Any] | None = None,
    gstack_status: dict[str, Any] | None = None,
    config_snapshot: dict[str, Any] | None = None,
    acceptance_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gateway_smoke = gateway_smoke or {}
    gstack_status = gstack_status or {}
    route_ids = list(readiness_summary.get("ready_routes") or [])
    non_ready_routes = list(readiness_summary.get("non_ready_routes") or [])
    gateway_ok_routes = _gateway_ok_routes(gateway_smoke, operational_summary)
    route_gates = {
        route: (
            GATE_GATEWAY_SMOKE_PASSED
            if route in gateway_ok_routes
            else GATE_LOCAL_SMOKE_PASSED
        )
        for route in route_ids
    }
    for route in readiness_summary.get("non_ready_routes") or []:
        route_gates[route] = GATE_BLOCKED
    for route in readiness_summary.get("unknown_routes") or []:
        route_gates[route] = GATE_BLOCKED

    missing_evidence: list[dict[str, str]] = []
    expected_ready_routes = set(REQUIRED_GATEWAY_SMOKE_ROUTES)
    declared_ready_routes = set(route_ids)
    if declared_ready_routes != expected_ready_routes or "report_revision_flow" not in non_ready_routes:
        missing_evidence.append(
            {
                "failure_code": ROUTE_MISCLASSIFIED,
                "reason": "readiness baseline changed from 7 ready routes plus report_revision_flow non_ready",
                "detail": (
                    f"ready={','.join(sorted(declared_ready_routes))}; "
                    f"non_ready={','.join(sorted(non_ready_routes))}"
                ),
            }
        )

    missing_gateway = [
        route for route in REQUIRED_GATEWAY_SMOKE_ROUTES if route not in gateway_ok_routes
    ]
    if missing_gateway:
        missing_evidence.append(
            {
                "failure_code": GATEWAY_SMOKE_MISSING,
                "reason": "Gateway/Feishu smoke evidence missing for ready routes",
                "detail": ",".join(missing_gateway),
            }
        )

    checks = operational_summary.get("checks") or {}
    if not checks.get("min_50_real_events", False):
        missing_evidence.append(
            {
                "failure_code": INSUFFICIENT_MEMORY_EVENTS,
                "reason": "memory_events below required real-event threshold",
                "detail": f"{operational_summary.get('event_count', 0)}/50",
            }
        )
    if not checks.get("covers_gstack_external_evidence", False):
        missing_evidence.append(
            {
                "failure_code": GSTACK_EXTERNAL_EVIDENCE_MISSING,
                "reason": "no real gstack external evidence event observed",
                "detail": "missing hermes://gstack/ memory event",
            }
        )

    if not config_snapshot:
        missing_evidence.append(
            {
                "failure_code": CONFIG_SNAPSHOT_MISSING,
                "reason": "production config snapshot missing",
                "detail": "run scripts/snapshot_agent_system_production_config.py",
            }
        )
    elif (config_snapshot.get("secret_hygiene") or {}).get("config_secret_detected"):
        missing_evidence.append(
            {
                "failure_code": CONFIG_SECRET_DETECTED,
                "reason": "redacted production config snapshot detected plaintext secret material",
                "detail": ",".join((config_snapshot.get("secret_hygiene") or {}).get("detected_paths") or []),
            }
        )

    if not acceptance_report:
        missing_evidence.append(
            {
                "failure_code": ACCEPTANCE_REPORT_MISSING,
                "reason": "latest acceptance report missing",
                "detail": "run scripts/write_agent_system_acceptance_report.py",
            }
        )

    if not gstack_status.get("adapter_available", False):
        missing_evidence.append(
            {
                "failure_code": GSTACK_CLI_MISSING,
                "reason": "gstack CLI unavailable; Hermes remains shadow/advisory/fail-closed",
                "detail": str(gstack_status.get("blocked_reason") or "adapter unavailable"),
            }
        )

    system_gates = {
        "readiness": (
            GATE_LOCAL_SMOKE_PASSED
            if declared_ready_routes == expected_ready_routes
            and "report_revision_flow" in non_ready_routes
            else GATE_BLOCKED
        ),
        "gateway_smoke": GATE_GATEWAY_SMOKE_PASSED if not missing_gateway else GATE_LOCAL_SMOKE_PASSED,
        "sedimentation": (
            GATE_OPERATIONALLY_VERIFIED
            if operational_summary.get("status") == "ready"
            else GATE_LOCAL_SMOKE_PASSED
        ),
        "gstack": GATE_GATEWAY_SMOKE_PASSED if gstack_status.get("adapter_available") else GATE_BLOCKED,
        "config_snapshot": (
            GATE_BLOCKED
            if not config_snapshot or (config_snapshot.get("secret_hygiene") or {}).get("config_secret_detected")
            else GATE_DECLARED
        ),
        "acceptance_report": GATE_DECLARED if acceptance_report else GATE_BLOCKED,
    }
    overall_status = _overall_status(
        missing_gateway=missing_gateway,
        operational_summary=operational_summary,
        gstack_status=gstack_status,
        missing_evidence=missing_evidence,
    )
    upgrade_allowed = overall_status == STATUS_PRODUCTION_READY
    return {
        "overall_status": overall_status,
        "primary_blocker_status": _primary_blocker_status(
            missing_gateway=missing_gateway,
            operational_summary=operational_summary,
            gstack_status=gstack_status,
            missing_evidence=missing_evidence,
        ),
        "upgrade_allowed": upgrade_allowed,
        "route_gates": route_gates,
        "system_gates": system_gates,
        "missing_evidence": missing_evidence,
        "next_required_actions": _next_actions(missing_evidence),
    }


def _gateway_ok_routes(gateway_smoke: dict[str, Any], operational_summary: dict[str, Any]) -> set[str]:
    routes = {
        str(item.get("route") or item.get("pipeline_id") or "")
        for item in gateway_smoke.get("routes", [])
        if str(item.get("status") or "").lower() in {"ok", "passed", "completed", "success"}
    }
    routes.update(operational_summary.get("gateway_smoke_routes_seen") or [])
    return {route for route in routes if route}


def _overall_status(
    *,
    missing_gateway: list[str],
    operational_summary: dict[str, Any],
    gstack_status: dict[str, Any],
    missing_evidence: list[dict[str, str]],
) -> str:
    if missing_evidence:
        return STATUS_LOCAL_READY
    return STATUS_PRODUCTION_READY


def _primary_blocker_status(
    *,
    missing_gateway: list[str],
    operational_summary: dict[str, Any],
    gstack_status: dict[str, Any],
    missing_evidence: list[dict[str, str]],
) -> str:
    if missing_gateway:
        return STATUS_GATEWAY_INCOMPLETE
    if operational_summary.get("status") != "ready":
        return STATUS_SEDIMENTATION_INSUFFICIENT
    if not gstack_status.get("adapter_available", False):
        return STATUS_GSTACK_SHADOW_ONLY
    if missing_evidence:
        return STATUS_EXTERNAL_BLOCKED
    return STATUS_PRODUCTION_READY


def _next_actions(missing_evidence: list[dict[str, str]]) -> list[str]:
    actions = []
    for item in missing_evidence:
        code = item.get("failure_code")
        if code == GATEWAY_SMOKE_MISSING:
            actions.append("Run and record real Gateway/Feishu smoke for all 7 ready routes.")
        elif code == INSUFFICIENT_MEMORY_EVENTS:
            actions.append("Collect at least 50 real memory events with required coverage.")
        elif code == GSTACK_EXTERNAL_EVIDENCE_MISSING:
            actions.append("Record real gstack external expert evidence or keep gstack shadow-only.")
        elif code == CONFIG_SNAPSHOT_MISSING:
            actions.append("Generate redacted production config snapshot.")
        elif code == ACCEPTANCE_REPORT_MISSING:
            actions.append("Generate latest acceptance report after status check.")
        elif code == GSTACK_CLI_MISSING:
            actions.append("Decide whether to install/absorb gstack; do not auto-install.")
        elif code == CONFIG_SECRET_DETECTED:
            actions.append("Move plaintext config secrets into .env or provider auth store, then regenerate snapshot.")
    return list(dict.fromkeys(actions))
