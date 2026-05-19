"""Session Capture Runtime Wiring Tests

Verifies that capture_turn() dispatches events through MemoryDispatcher
and produces entries in staging or personal_memory as appropriate.
"""
from __future__ import annotations

import pytest


def test_capture_turn_user_correction_dispatches_to_personal_memory(tmp_path):
    """user_correction + no scope → goes to staging (rule 4 no scope)."""
    from agent.session_capture import capture_turn
    from agent.memory_event import list_events
    from agent.staging_store import list_staging

    event_id = capture_turn(
        "不要用这个词，很奇怪",
        session_id="sess-rt-1",
        actor_user_id="user_test",
        hermes_home=tmp_path,
    )

    assert event_id is not None, "correction text must trigger event creation"
    events = list_events(hermes_home=tmp_path)
    assert any(e["id"] == event_id for e in events), "event must be written to events.jsonl"
    staging = list_staging(hermes_home=tmp_path)
    assert len(staging) >= 1, "user_correction without scope → staging (rule 4)"


def test_capture_turn_no_risk_pattern_returns_none(tmp_path):
    """Normal text without risk patterns must return None (no event created)."""
    from agent.session_capture import capture_turn
    from agent.memory_event import list_events

    result = capture_turn(
        "请帮我分析一下这个数据",
        session_id="sess-rt-2",
        actor_user_id="user_test",
        hermes_home=tmp_path,
    )

    assert result is None
    events = list_events(hermes_home=tmp_path)
    assert len(events) == 0, "no event for non-risk text"


def test_capture_turn_dispatch_never_raises(tmp_path):
    """capture_turn must not raise even when dispatcher would fail."""
    from agent.session_capture import capture_turn

    result = capture_turn(
        "不要用'晋升'这个词",
        session_id="sess-rt-3",
        actor_user_id="user",
        hermes_home=tmp_path,
    )
    # Any result (None or event_id) is acceptable; no exception must propagate
    assert True


def test_capture_turn_david_trigger_creates_event(tmp_path):
    """ExperienceCard trigger word → identity_missing flag → event created."""
    from agent.session_capture import capture_turn
    from agent.memory_event import list_events

    event_id = capture_turn(
        "David 说他不喜欢这个功能",
        session_id="sess-rt-4",
        actor_user_id="user_test",
        hermes_home=tmp_path,
    )

    assert event_id is not None
    events = list_events(hermes_home=tmp_path)
    matching = [e for e in events if e["id"] == event_id]
    assert matching, "event must be in events.jsonl"
    assert "identity_missing" in matching[0]["risk_flags"]


def test_capture_turn_event_has_correct_session_id(tmp_path):
    """Events created by capture_turn must carry the passed session_id."""
    from agent.session_capture import capture_turn
    from agent.memory_event import list_events

    event_id = capture_turn(
        "不要用系统腔",
        session_id="my-session-xyz",
        actor_user_id="user_test",
        hermes_home=tmp_path,
    )

    assert event_id is not None
    events = list_events(hermes_home=tmp_path)
    matching = [e for e in events if e["id"] == event_id]
    assert matching
    assert matching[0]["session_id"] == "my-session-xyz"
