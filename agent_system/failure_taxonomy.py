from __future__ import annotations

from typing import Final


TRIGGER_MISS: Final = "trigger_miss"
ROUTE_MISCLASSIFIED: Final = "route_misclassified"
CREDENTIAL_MISSING: Final = "credential_missing"
PROVIDER_RATE_LIMITED: Final = "provider_rate_limited"
PROVIDER_NOT_FOUND: Final = "provider_not_found"
ARTIFACT_UNRESOLVED: Final = "artifact_unresolved"
HUMAN_GATE_TIMEOUT: Final = "human_gate_timeout"
HUMAN_GATE_REJECTED: Final = "human_gate_rejected"
DELEGATE_CONTRACT_VIOLATION: Final = "delegate_contract_violation"
MEMORY_ACL_DENIED: Final = "memory_acl_denied"
GATEWAY_DELIVERY_FAILED: Final = "gateway_delivery_failed"
COST_BUDGET_EXCEEDED: Final = "cost_budget_exceeded"
GSTACK_CLI_MISSING: Final = "gstack_cli_missing"
EXTERNAL_DEPENDENCY_UNAVAILABLE: Final = "external_dependency_unavailable"
CONFIG_SNAPSHOT_MISSING: Final = "config_snapshot_missing"
GATEWAY_SMOKE_MISSING: Final = "gateway_smoke_missing"
INSUFFICIENT_MEMORY_EVENTS: Final = "insufficient_memory_events"
GSTACK_EXTERNAL_EVIDENCE_MISSING: Final = "gstack_external_evidence_missing"
ACCEPTANCE_REPORT_MISSING: Final = "acceptance_report_missing"
CONFIG_SECRET_DETECTED: Final = "config_secret_detected"


FAILURE_CODES: Final[set[str]] = {
    TRIGGER_MISS,
    ROUTE_MISCLASSIFIED,
    CREDENTIAL_MISSING,
    PROVIDER_RATE_LIMITED,
    PROVIDER_NOT_FOUND,
    ARTIFACT_UNRESOLVED,
    HUMAN_GATE_TIMEOUT,
    HUMAN_GATE_REJECTED,
    DELEGATE_CONTRACT_VIOLATION,
    MEMORY_ACL_DENIED,
    GATEWAY_DELIVERY_FAILED,
    COST_BUDGET_EXCEEDED,
    GSTACK_CLI_MISSING,
    EXTERNAL_DEPENDENCY_UNAVAILABLE,
    CONFIG_SNAPSHOT_MISSING,
    GATEWAY_SMOKE_MISSING,
    INSUFFICIENT_MEMORY_EVENTS,
    GSTACK_EXTERNAL_EVIDENCE_MISSING,
    ACCEPTANCE_REPORT_MISSING,
    CONFIG_SECRET_DETECTED,
}


def normalize_failure_code(value: str | None, *, default: str = EXTERNAL_DEPENDENCY_UNAVAILABLE) -> str:
    code = (value or "").strip()
    if not code:
        return ""
    return code if code in FAILURE_CODES else default


def require_failure_code(value: str | None) -> str:
    code = normalize_failure_code(value)
    if not code:
        raise ValueError("failure_code is required for failed/blocked evidence")
    return code
