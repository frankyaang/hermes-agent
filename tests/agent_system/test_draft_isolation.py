"""
Tests for draft artifact session isolation in 深度养马模式.

Verifies that write_drafts() writes to per-session directories under
agent_system/temp/builder_sessions/<state_identity>/ and never touches
shared paths like agent_system/scheduler/main_scheduler/routes.draft.json.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from agent_system.experts.builder_expert import draft_writer
from agent_system.experts.builder_expert.builder import handle_commit
from agent_system import builder_dispatcher


def _minimal_state(state_identity: str) -> dict:
    """Minimal builder state for write_drafts / handle_commit."""
    safe_id = state_identity.replace("-", "_")
    return {
        "state_identity": state_identity,
        "stage": "DRAFT",
        "intake": {
            "business_goal": "test goal",
            "scenario": "test scenario",
            "input_type": "text",
            "output_type": "summary",
            "pipeline_description": "test pipeline",
            "priority": "normal",
        },
        "architect_proposal": {
            "experts": [{"name": f"expert_{safe_id}", "action": "create"}],
            "skills": [{"name": f"skill_{safe_id}", "input": "text", "rationale": ""}],
            "routes": [
                {"pipeline_id": f"pipeline_{safe_id}", "steps": [], "schedule": None}
            ],
        },
        "drafts": {},
        "validation": {},
        "dry_run": {},
        "trial_run": {},
        "history": [],
    }


def _setup_prod_dirs(root: Path) -> None:
    """Create the production directories that handle_commit renames drafts into."""
    (root / "skills").mkdir(parents=True, exist_ok=True)
    (root / "experts").mkdir(parents=True, exist_ok=True)
    routes_prod = root / "scheduler" / "main_scheduler" / "routes.json"
    routes_prod.parent.mkdir(parents=True, exist_ok=True)
    routes_prod.write_text(
        json.dumps(
            {"scheduler": "main_scheduler", "version": 1, "pipelines": []},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_two_sessions_produce_different_session_draft_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_writer, "_agent_system_root", lambda: tmp_path)

    result_a = draft_writer.write_drafts(_minimal_state("session-a"))
    result_b = draft_writer.write_drafts(_minimal_state("session-b"))

    assert result_a["session_draft_root"] != result_b["session_draft_root"]
    assert "session" in result_a["session_draft_root"]
    assert "session" in result_b["session_draft_root"]


def test_two_sessions_have_different_routes_draft_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_writer, "_agent_system_root", lambda: tmp_path)

    result_a = draft_writer.write_drafts(_minimal_state("session-a"))
    result_b = draft_writer.write_drafts(_minimal_state("session-b"))

    assert result_a["routes_draft_path"] != result_b["routes_draft_path"]


def test_no_write_to_shared_routes_draft_json(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_writer, "_agent_system_root", lambda: tmp_path)

    draft_writer.write_drafts(_minimal_state("session-x"))

    shared = tmp_path / "scheduler" / "main_scheduler" / "routes.draft.json"
    assert not shared.exists(), "write_drafts must not touch the shared routes.draft.json"


def test_session_a_commit_reads_session_a_draft_only(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_writer, "_agent_system_root", lambda: tmp_path)

    state_a = _minimal_state("session-a")
    state_a["drafts"] = draft_writer.write_drafts(state_a)
    _setup_prod_dirs(tmp_path)

    # Shared _drafts/ path must NOT have been created by write_drafts
    assert not (tmp_path / "skills" / "_drafts").exists()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        output = handle_commit(state_a, "确认提交", parent_agent=None)

    skill_name = state_a["drafts"]["skill_name"]
    skill_prod = tmp_path / "skills" / skill_name
    assert skill_prod.exists(), f"skill not moved to prod; handle_commit output: {output}"


def test_exit_does_not_delete_session_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_writer, "_agent_system_root", lambda: tmp_path)

    state = _minimal_state("exit-test")
    result = draft_writer.write_drafts(state)
    session_root = Path(result["session_draft_root"])
    assert session_root.exists()

    # Simulate builder_dispatcher exit: only the mode state file is removed
    fake_state_file = tmp_path / "temp" / "skill_creation_exit-test.json"
    fake_state_file.parent.mkdir(parents=True, exist_ok=True)
    fake_state_file.write_text("{}", encoding="utf-8")

    builder_dispatcher._exit_mode(fake_state_file)

    assert not fake_state_file.exists(), "exit must remove the state file"
    assert session_root.exists(), "exit must NOT delete the session draft directory"


def test_session_b_draft_untouched_after_session_a_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_writer, "_agent_system_root", lambda: tmp_path)

    state_a = _minimal_state("session-a2")
    state_b = _minimal_state("session-b2")

    state_a["drafts"] = draft_writer.write_drafts(state_a)
    state_b["drafts"] = draft_writer.write_drafts(state_b)

    _setup_prod_dirs(tmp_path)

    skill_b_name = state_b["drafts"]["skill_name"]
    session_b_root = Path(state_b["drafts"]["session_draft_root"])
    skill_b_draft = session_b_root / "skills" / "_drafts" / skill_b_name
    assert skill_b_draft.exists()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        handle_commit(state_a, "确认提交", parent_agent=None)

    assert skill_b_draft.exists(), "session B draft must be untouched after session A commits"
