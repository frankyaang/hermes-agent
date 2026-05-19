from __future__ import annotations

import json
from pathlib import Path

from agent_system.operational_evidence import summarize_operational_evidence


def _append_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_operational_evidence_not_ready_without_real_events(tmp_path: Path):
    summary = summarize_operational_evidence(tmp_path)
    assert summary["status"] == "not_ready"
    assert summary["event_count"] == 0
    assert summary["checks"]["min_50_real_events"] is False
    assert summary["gateway_smoke_routes_missing"]


def test_operational_evidence_ready_when_all_gates_present(tmp_path: Path):
    events = []
    for idx in range(50):
        events.append(
            {
                "id": f"evt-{idx}",
                "source_type": "session",
                "source_uri": f"hermes://session/{idx}",
                "risk_flags": [],
                "recommended_destination": "personal_memory",
            }
        )
    events[0].update({"source_type": "user_correction", "risk_flags": ["user_correction"]})
    events[1].update({"source_type": "write_failure", "risk_flags": ["tool_failure", "permission_unclear"]})
    events[2].update({"recommended_destination": "project_process"})
    events[3].update({"source_uri": "hermes://gstack/gstack.review/gstack review --advisory"})
    _append_jsonl(tmp_path / "memory_events" / "events.jsonl", events)
    _append_jsonl(tmp_path / "staging" / "staging.jsonl", [{"staging_id": "s1"}])
    _append_jsonl(tmp_path / "project_process" / "records.jsonl", [{"record_id": "p1"}])

    gateway_path = tmp_path / "agent_system" / "evidence" / "gateway_smoke.json"
    gateway_path.parent.mkdir(parents=True, exist_ok=True)
    gateway_path.write_text(
        json.dumps(
            {
                "routes": [
                    {"route": "artifact_status_flow", "status": "ok"},
                    {"route": "artifact_delivery_flow", "status": "ok"},
                    {"route": "doc_publish_flow", "status": "ok"},
                    {"route": "insight_flow", "status": "ok"},
                    {"route": "dashboard_flow", "status": "ok"},
                    {"route": "html_flow", "status": "ok"},
                    {"route": "dashboard_from_artifact_flow", "status": "ok"},
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_operational_evidence(tmp_path)
    assert summary["status"] == "ready"
    assert summary["event_count"] == 50
    assert summary["checks"]["gateway_smoke_routes_complete"] is True
