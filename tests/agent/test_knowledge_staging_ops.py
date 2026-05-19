"""Tests for knowledge_staging_ops tool (_staging_ops function).

Covers all 6 actions: list, stats, approve, reject, archive, migrate_pending,
plus the invalid action guard.
"""
from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# Helper: call _staging_ops via direct import (no registry overhead)
# ---------------------------------------------------------------------------

def _call(action, staging_id="", reason="", limit=20, tmp_path=None):
    import sys
    # Force hermes_home via env if tmp_path provided
    if tmp_path is not None:
        import os
        os.environ["HERMES_HOME"] = str(tmp_path)
    from tools.knowledge_tool import _staging_ops
    return json.loads(_staging_ops(action=action, staging_id=staging_id,
                                   reason=reason, limit=limit, task_id=""))


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture()
def populated(home):
    """Write two staging entries and return their staging_ids."""
    from agent.staging_store import write_staging
    id1 = write_staging(
        event_id="evt-ops-1",
        source_uri="hermes://test/1",
        reason="test entry 1",
        next_action="retry_write",
        hermes_home=home,
    )
    id2 = write_staging(
        event_id="evt-ops-2",
        source_uri="hermes://test/2",
        reason="test entry 2",
        next_action="needs_user_confirmation",
        hermes_home=home,
    )
    return id1, id2, home


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_returns_all_entries(populated):
    id1, id2, home = populated
    result = _call("list", tmp_path=home)
    assert result["total"] == 2
    assert result["showing"] == 2
    ids = [e["staging_id"] for e in result["entries"]]
    assert id1 in ids
    assert id2 in ids


def test_list_truncates_event_id(populated):
    _, _, home = populated
    result = _call("list", tmp_path=home)
    for entry in result["entries"]:
        assert entry["event_id"].endswith("...")


def test_list_limit_respected(populated):
    _, _, home = populated
    result = _call("list", limit=1, tmp_path=home)
    assert result["total"] == 2
    assert result["showing"] == 1


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def test_stats_returns_staging_and_pending(home):
    from agent.staging_store import write_staging
    write_staging(
        event_id="evt-stats-1",
        source_uri="hermes://test/s",
        reason="stats test",
        next_action="retry_write",
        hermes_home=home,
    )
    result = _call("stats", tmp_path=home)
    assert "staging" in result
    assert "pending" in result
    assert result["staging"]["total"] == 1
    assert result["staging"]["by_next_action"]["retry_write"] == 1


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------

def test_approve_succeeds(populated):
    id1, _, home = populated
    result = _call("approve", staging_id=id1, tmp_path=home)
    assert result["success"] is True
    assert result["staging_id"] == id1
    assert result["action"] == "approved"


def test_approve_missing_staging_id(home):
    result = _call("approve", tmp_path=home)
    assert "error" in result
    assert result["error"] == "missing_staging_id"


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------

def test_reject_with_reason(populated):
    _, id2, home = populated
    result = _call("reject", staging_id=id2, reason="not relevant", tmp_path=home)
    assert result["success"] is True
    assert result["action"] == "rejected"


def test_reject_missing_staging_id(home):
    result = _call("reject", tmp_path=home)
    assert result["error"] == "missing_staging_id"


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------

def test_archive_succeeds(populated):
    id1, _, home = populated
    result = _call("archive", staging_id=id1, tmp_path=home)
    assert result["success"] is True
    assert result["action"] == "archived"


def test_archive_missing_staging_id(home):
    result = _call("archive", tmp_path=home)
    assert result["error"] == "missing_staging_id"


# ---------------------------------------------------------------------------
# migrate_pending
# ---------------------------------------------------------------------------

def test_migrate_pending_moves_records_to_staging(home):
    from agent.pending_capture import write_pending_capture
    write_pending_capture(
        title="pending item 1",
        summary="summary 1",
        candidate_type="business_fact",
        scope_id="test_pl",
        source_uri="hermes://pending/1",
        confidence="medium",
        missing_fields=[],
        failure_reason="permission_denied",
        session_id="sess-mp-1",
        user_id="agent",
        hermes_home=home,
    )
    write_pending_capture(
        title="pending item 2",
        summary="summary 2",
        candidate_type="business_fact",
        scope_id="test_pl",
        source_uri="hermes://pending/2",
        confidence="medium",
        missing_fields=[],
        failure_reason="permission_denied",
        session_id="sess-mp-1",
        user_id="agent",
        hermes_home=home,
    )
    result = _call("migrate_pending", tmp_path=home)
    assert result["total"] == 2
    assert result["migrated"] == 2

    from agent.staging_store import stats
    s = stats(hermes_home=home)
    assert s["total"] == 2


def test_migrate_pending_idempotent(home):
    from agent.pending_capture import write_pending_capture
    write_pending_capture(
        title="idempotent item",
        summary="summary idem",
        candidate_type="business_fact",
        scope_id="test_pl",
        source_uri="hermes://pending/idem",
        confidence="medium",
        missing_fields=[],
        failure_reason="permission_denied",
        session_id="sess-idem",
        user_id="agent",
        hermes_home=home,
    )
    result1 = _call("migrate_pending", tmp_path=home)
    result2 = _call("migrate_pending", tmp_path=home)
    assert result1["migrated"] == 1
    assert result2["migrated"] == 1

    from agent.staging_store import stats
    s = stats(hermes_home=home)
    assert s["total"] == 1


def test_migrate_pending_empty(home):
    result = _call("migrate_pending", tmp_path=home)
    assert result["total"] == 0
    assert result["migrated"] == 0


# ---------------------------------------------------------------------------
# invalid action
# ---------------------------------------------------------------------------

def test_invalid_action_returns_error(home):
    result = _call("nonexistent", tmp_path=home)
    assert result["error"] == "invalid_action"
