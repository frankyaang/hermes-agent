from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_system.evidence_gate import evaluate_evidence_gate
from agent_system.failure_taxonomy import CONFIG_SECRET_DETECTED, GATEWAY_SMOKE_MISSING
from agent_system.operational_evidence import REQUIRED_GATEWAY_SMOKE_ROUTES
from agent_system.production_config_snapshot import (
    build_production_config_snapshot,
    write_production_config_snapshot,
)
from agent_system.run_evidence import (
    append_run_evidence,
    list_run_evidence,
    make_gateway_smoke_record,
    make_run_evidence_record,
    record_gateway_smoke,
)
from agent_system.status_report import build_status_report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ready_summary() -> dict:
    return {
        "ready_routes": list(REQUIRED_GATEWAY_SMOKE_ROUTES),
        "non_ready_routes": ["report_revision_flow"],
        "unknown_routes": [],
    }


def _ready_operational_summary() -> dict:
    return {
        "status": "ready",
        "event_count": 50,
        "gateway_smoke_routes_seen": list(REQUIRED_GATEWAY_SMOKE_ROUTES),
        "checks": {
            "min_50_real_events": True,
            "covers_gstack_external_evidence": True,
        },
    }


def _gateway_smoke_payload() -> dict:
    return {
        "routes": [
            {"route": route, "status": "ok"}
            for route in REQUIRED_GATEWAY_SMOKE_ROUTES
        ]
    }


def test_evidence_gate_blocks_without_gateway_smoke() -> None:
    result = evaluate_evidence_gate(
        readiness_summary=_ready_summary(),
        operational_summary={
            "status": "not_ready",
            "event_count": 0,
            "checks": {
                "min_50_real_events": False,
                "covers_gstack_external_evidence": False,
            },
        },
        gateway_smoke={"routes": []},
        gstack_status={"adapter_available": False},
        config_snapshot=None,
        acceptance_report=None,
    )

    assert result["overall_status"] == "local_ready_not_operationally_verified"
    assert result["primary_blocker_status"] == "gateway_smoke_incomplete"
    assert result["upgrade_allowed"] is False
    assert any(item["failure_code"] == GATEWAY_SMOKE_MISSING for item in result["missing_evidence"])


def test_evidence_gate_blocks_config_secret_even_when_other_gates_pass() -> None:
    result = evaluate_evidence_gate(
        readiness_summary=_ready_summary(),
        operational_summary=_ready_operational_summary(),
        gateway_smoke=_gateway_smoke_payload(),
        gstack_status={"adapter_available": True},
        config_snapshot={
            "secret_hygiene": {
                "config_secret_detected": True,
                "detected_paths": ["providers.example.api_key"],
            }
        },
        acceptance_report={"created_at": "2026-05-19T00:00:00Z"},
    )

    assert result["overall_status"] == "local_ready_not_operationally_verified"
    assert result["upgrade_allowed"] is False
    assert any(item["failure_code"] == CONFIG_SECRET_DETECTED for item in result["missing_evidence"])


def test_evidence_gate_allows_production_only_when_all_evidence_exists() -> None:
    result = evaluate_evidence_gate(
        readiness_summary=_ready_summary(),
        operational_summary=_ready_operational_summary(),
        gateway_smoke=_gateway_smoke_payload(),
        gstack_status={"adapter_available": True},
        config_snapshot={"secret_hygiene": {"config_secret_detected": False}},
        acceptance_report={"created_at": "2026-05-19T00:00:00Z"},
    )

    assert result["overall_status"] == "production_ready"
    assert result["primary_blocker_status"] == "production_ready"
    assert result["upgrade_allowed"] is True
    assert result["missing_evidence"] == []


def test_run_evidence_validates_route_status_failure_code_and_redacts(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make_run_evidence_record(route="unknown_flow", platform="feishu", status="ok")

    with pytest.raises(ValueError):
        make_run_evidence_record(route="insight_flow", platform="feishu", status="failed")

    record = make_run_evidence_record(
        route="insight_flow",
        platform="feishu",
        status="ok",
        model_routing={"planning": "Bearer secret-value", "execution": "gpt-5.5"},
        human_gate={"required": True, "decision": "approved", "actor": "operator"},
    )
    path = append_run_evidence(tmp_path, record)

    assert path.exists()
    loaded = list_run_evidence(tmp_path)
    assert loaded[0]["model_routing"]["planning"] == "[REDACTED]"
    assert "secret-value" not in json.dumps(loaded, ensure_ascii=False)


def test_gateway_smoke_record_validates_and_upserts(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make_gateway_smoke_record(route="report_revision_flow", status="ok")

    first = make_gateway_smoke_record(route="insight_flow", status="ok", run_id="run-1")
    second = make_gateway_smoke_record(route="insight_flow", status="blocked", failure_code="human_gate_timeout", run_id="run-2")
    record_gateway_smoke(tmp_path, first)
    path = record_gateway_smoke(tmp_path, second)
    payload = json.loads(path.read_text(encoding="utf-8"))

    routes = [item for item in payload["routes"] if item["route"] == "insight_flow"]
    assert len(routes) == 1
    assert routes[0]["status"] == "blocked"
    assert routes[0]["failure_code"] == "human_gate_timeout"


def test_production_config_snapshot_redacts_and_marks_plaintext_secret(tmp_path: Path) -> None:
    hermes_home = tmp_path / "home"
    hermes_home.mkdir()
    config_path = hermes_home / "config.yaml"
    config_path.write_text(
        """
providers:
  example:
    base_url: https://example.test/v1
    api_key: sk-test-secret-value
agent:
  reasoning_effort: xhigh
voice:
  record_key: r
""",
        encoding="utf-8",
    )

    snapshot = build_production_config_snapshot(
        hermes_home=hermes_home,
        repo_root=tmp_path,
        config_path=config_path,
    )
    text = json.dumps(snapshot, ensure_ascii=False)

    assert snapshot["secret_hygiene"]["config_secret_detected"] is True
    assert "providers.example.api_key" in snapshot["secret_hygiene"]["detected_paths"]
    assert "voice.record_key" not in snapshot["secret_hygiene"]["detected_paths"]
    assert "sk-test-secret-value" not in text
    assert snapshot["providers"]["example"]["has_api_key"] is True


def test_status_report_keeps_current_state_not_upgradeable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hermes_home = tmp_path / "home"
    hermes_home.mkdir()
    write_production_config_snapshot(hermes_home=hermes_home, repo_root=_repo_root())
    monkeypatch.setattr(
        "agent_system.status_report.summarize_gstack_status",
        lambda: {
            "enabled": False,
            "mode": "disabled",
            "adapter_available": False,
            "blocked": True,
            "blocked_reason": "missing cli",
        },
    )

    report = build_status_report(hermes_home=hermes_home, repo_root=_repo_root())

    assert report["overall_status"] == "local_ready_not_operationally_verified"
    assert report["upgrade_allowed"] is False
    assert report["readiness"]["ready_route_count"] == 7
    assert report["gateway_smoke"]["completed_count"] == 0
    assert report["production_config_snapshot"]["exists"] is True
