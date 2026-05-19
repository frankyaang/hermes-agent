"""project_process_store runtime evidence tests."""
from __future__ import annotations

from agent.project_process_store import list_records, write_record


def test_write_record_adds_runtime_evidence(tmp_path):
    record_id = write_record(
        event_id="evt-project-1",
        subject="PBI 二期下一步动作",
        project_hint="PBI_phase2",
        source_uri="hermes://session/project",
        actor_user_id="feishu:ou_pm",
        hermes_home=tmp_path,
    )

    records = list_records(hermes_home=tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["record_id"] == record_id
    assert record["status"] == "recorded"
    assert record["producer_runtime_path"] == "agent.project_process_store.write_record"
    assert record["source_capability"] == "project_process_store"
    assert record["usage_hint"] == "project_material_usable"
    assert record["sanitized_summary"]
