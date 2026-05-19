"""cognitive_governance_smoke script tests."""
from __future__ import annotations

import json

from scripts.cognitive_governance_smoke import artifact_report, backfill_legacy_status


def test_backfill_legacy_status_adds_evidence_fields(tmp_path):
    path = tmp_path / "memory_events" / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "id": "evt-legacy",
            "subject": "legacy subject",
            "source_uri": "hermes://legacy",
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    changed = backfill_legacy_status(tmp_path)
    assert "memory_events" in changed
    assert path.with_name(path.name + ".bak_20260519_phase9").exists()

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["status"] == "captured"
    assert record["producer_runtime_path"] == "agent.memory_event.write_event"
    assert record["sanitized_summary"]


def test_artifact_report_counts_statuses(tmp_path):
    path = tmp_path / "staging" / "staging.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"status": "staged", "sanitized_summary": "ok"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report = artifact_report(tmp_path)
    assert report["staging"]["line_count"] == 1
    assert report["staging"]["status_counts"] == {"staged": 1}
