"""Staging + Pending Ops Tests

Covers approve/reject/archive/update_next_action/stats operations on
StagingStore, plus stats/migrate_to_staging on PendingCapture.

HERMES_HOME is isolated per test via tmp_path.
"""
from __future__ import annotations

import pytest
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────────

def _seed_staging(tmp_path, next_action="retry_write", count=1) -> list[str]:
    from agent.staging_store import write_staging
    ids = []
    for i in range(count):
        sid = write_staging(
            event_id=f"evt-{i}",
            reason=f"test reason {i}",
            next_action=next_action,
            source_uri=f"hermes://test/{i}",
            hermes_home=tmp_path,
        )
        ids.append(sid)
    return ids


def _seed_pending(tmp_path, n=1) -> list[str]:
    from agent.pending_capture import write_pending_capture
    ids = []
    for i in range(n):
        cid = write_pending_capture(
            title=f"pending {i}",
            summary=f"summary {i}",
            candidate_type="knowledge",
            scope_id="test_scope",
            source_uri=f"hermes://test/pending/{i}",
            confidence="medium",
            missing_fields=[],
            failure_reason="permission_denied",
            session_id="sess-test",
            user_id="user_test",
            hermes_home=tmp_path,
        )
        ids.append(cid)
    return ids


# ── approve ─────────────────────────────────────────────────────────────────

def test_approve_marks_staging_approved(tmp_path):
    from agent.staging_store import approve, read_staging
    sid = _seed_staging(tmp_path)[0]

    result = approve(sid, hermes_home=tmp_path)

    assert result is True
    entry = read_staging(sid, hermes_home=tmp_path)
    assert entry is not None
    assert entry["next_action"] == "approved"


def test_approve_not_found_returns_false(tmp_path):
    from agent.staging_store import approve
    result = approve("nonexistent-id", hermes_home=tmp_path)
    assert result is False


def test_approve_idempotent(tmp_path):
    from agent.staging_store import approve, read_staging
    sid = _seed_staging(tmp_path)[0]
    approve(sid, hermes_home=tmp_path)
    result2 = approve(sid, hermes_home=tmp_path)
    assert result2 is True
    entry = read_staging(sid, hermes_home=tmp_path)
    assert entry["next_action"] == "approved"


# ── reject ──────────────────────────────────────────────────────────────────

def test_reject_marks_staging_rejected(tmp_path):
    from agent.staging_store import reject, read_staging
    sid = _seed_staging(tmp_path)[0]

    result = reject(sid, reason="out of scope", hermes_home=tmp_path)

    assert result is True
    entry = read_staging(sid, hermes_home=tmp_path)
    assert entry["next_action"] == "rejected"


def test_reject_stores_reason(tmp_path):
    from agent.staging_store import reject, read_staging
    sid = _seed_staging(tmp_path)[0]
    reject(sid, reason="irrelevant content", hermes_home=tmp_path)
    entry = read_staging(sid, hermes_home=tmp_path)
    assert "irrelevant content" in entry.get("rejection_reason", "")


def test_reject_not_found_returns_false(tmp_path):
    from agent.staging_store import reject
    assert reject("no-such-id", hermes_home=tmp_path) is False


# ── archive ──────────────────────────────────────────────────────────────────

def test_archive_sets_archive_as_reference(tmp_path):
    from agent.staging_store import archive, read_staging
    sid = _seed_staging(tmp_path, next_action="needs_user_confirmation")[0]

    result = archive(sid, hermes_home=tmp_path)

    assert result is True
    entry = read_staging(sid, hermes_home=tmp_path)
    assert entry["next_action"] == "archive_as_reference"


# ── update_next_action ────────────────────────────────────────────────────────

def test_update_next_action_valid(tmp_path):
    from agent.staging_store import update_next_action, read_staging
    sid = _seed_staging(tmp_path, next_action="wait_for_source")[0]

    result = update_next_action(sid, "needs_user_confirmation", hermes_home=tmp_path)

    assert result is True
    entry = read_staging(sid, hermes_home=tmp_path)
    assert entry["next_action"] == "needs_user_confirmation"


def test_update_next_action_invalid_rejected(tmp_path):
    from agent.staging_store import update_next_action, read_staging
    sid = _seed_staging(tmp_path, next_action="wait_for_source")[0]

    result = update_next_action(sid, "invalid_state", hermes_home=tmp_path)

    assert result is False
    entry = read_staging(sid, hermes_home=tmp_path)
    assert entry["next_action"] == "wait_for_source", "Invalid transition must not modify state"


# ── stats ────────────────────────────────────────────────────────────────────

def test_stats_empty(tmp_path):
    from agent.staging_store import stats
    result = stats(hermes_home=tmp_path)
    assert isinstance(result, dict)
    assert result.get("total") == 0


def test_stats_counts_by_next_action(tmp_path):
    from agent.staging_store import stats
    _seed_staging(tmp_path, next_action="retry_write", count=3)
    _seed_staging(tmp_path, next_action="needs_user_confirmation", count=2)

    result = stats(hermes_home=tmp_path)

    assert result["total"] == 5
    assert result["by_next_action"]["retry_write"] == 3
    assert result["by_next_action"]["needs_user_confirmation"] == 2


def test_stats_reflects_state_changes(tmp_path):
    from agent.staging_store import approve, stats
    sids = _seed_staging(tmp_path, next_action="retry_write", count=2)
    approve(sids[0], hermes_home=tmp_path)

    result = stats(hermes_home=tmp_path)

    assert result["by_next_action"].get("approved", 0) == 1
    assert result["by_next_action"].get("retry_write", 0) == 1


# ── audit log ────────────────────────────────────────────────────────────────

def test_ops_write_audit_log(tmp_path):
    from agent.staging_store import approve, reject
    sids = _seed_staging(tmp_path, count=2)
    approve(sids[0], hermes_home=tmp_path)
    reject(sids[1], reason="test", hermes_home=tmp_path)

    audit_path = tmp_path / "staging" / "staging_audit.jsonl"
    assert audit_path.exists(), "audit log must be written"
    lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
    assert len(lines) >= 2, "each op must write an audit entry"


# ── pending stats ─────────────────────────────────────────────────────────────

def test_pending_stats_empty(tmp_path):
    from agent.pending_capture import stats as pending_stats
    result = pending_stats(hermes_home=tmp_path)
    assert isinstance(result, dict)
    assert result.get("total") == 0


def test_pending_stats_counts_by_status(tmp_path):
    from agent.pending_capture import stats as pending_stats, mark_terminal
    cids = _seed_pending(tmp_path, n=3)
    mark_terminal(cids[0], "knowledge_saved", hermes_home=tmp_path)
    mark_terminal(cids[1], "blocked", hermes_home=tmp_path)

    result = pending_stats(hermes_home=tmp_path)

    assert result["total"] == 3
    assert result["by_status"]["written"] >= 1
    assert result["by_status"]["blocked"] >= 1
    assert result["by_status"]["pending"] >= 1


# ── pending migrate_to_staging ────────────────────────────────────────────────

def test_migrate_pending_to_staging(tmp_path):
    from agent.pending_capture import migrate_to_staging
    from agent.staging_store import read_staging
    cids = _seed_pending(tmp_path)

    staging_id = migrate_to_staging(cids[0], hermes_home=tmp_path)

    assert staging_id, "migrate must return a non-empty staging_id"
    entry = read_staging(staging_id, hermes_home=tmp_path)
    assert entry is not None
    assert entry["next_action"] == "retry_write"


def test_migrate_pending_idempotent(tmp_path):
    from agent.pending_capture import migrate_to_staging, read_pending
    from agent.staging_store import list_staging
    cids = _seed_pending(tmp_path)

    sid1 = migrate_to_staging(cids[0], hermes_home=tmp_path)
    sid2 = migrate_to_staging(cids[0], hermes_home=tmp_path)

    assert sid1 == sid2, "idempotent: same staging_id on repeat call"
    staging_entries = list_staging(hermes_home=tmp_path)
    assert len(staging_entries) == 1, "no duplicate staging entries"


def test_migrate_nonexistent_pending_returns_empty(tmp_path):
    from agent.pending_capture import migrate_to_staging
    result = migrate_to_staging("no-such-id", hermes_home=tmp_path)
    assert result == ""
