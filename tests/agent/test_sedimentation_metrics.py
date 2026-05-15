"""Tests for sedimentation_metrics — atomic counter observability."""
from __future__ import annotations
from agent.sedimentation_metrics import SedimentationMetrics, METRIC_NAMES


def test_increment_and_snapshot():
    m = SedimentationMetrics()
    m.increment("candidate_detected")
    m.increment("knowledge_write_success")
    m.increment("knowledge_write_success")
    snap = m.snapshot()
    assert snap["candidate_detected"] == 1
    assert snap["knowledge_write_success"] == 2
    assert snap["pending_created"] == 0


def test_all_metric_names_in_snapshot():
    m = SedimentationMetrics()
    snap = m.snapshot()
    for name in METRIC_NAMES:
        assert name in snap


def test_increment_unknown_name_raises():
    m = SedimentationMetrics()
    try:
        m.increment("does_not_exist")
        assert False, "should have raised"
    except KeyError:
        pass


def test_reset_clears_counts():
    m = SedimentationMetrics()
    m.increment("pending_created")
    m.reset()
    assert m.snapshot()["pending_created"] == 0


def test_required_metric_names():
    for name in [
        "candidate_detected", "routed_to_memory", "routed_to_skill",
        "routed_to_knowledge", "pending_created",
        "knowledge_write_success", "knowledge_write_failed",
        "no_action_with_reason", "replay_success", "replay_failed", "blocked",
    ]:
        assert name in METRIC_NAMES
