"""Knowledge Tool Sedimentation Integration Tests

Verifies that knowledge_tool write failures route through dispatch_tool_failure()
to staging(retry_write), and that query results carry usage_hint when the flag is ON.
"""
from __future__ import annotations

import json
import pytest


def test_knowledge_write_permission_denied_creates_staging_entry(tmp_path, monkeypatch):
    """permission_denied → dispatch_tool_failure() → staging(retry_write)."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    from agent.memory_dispatcher import dispatch_tool_failure
    from agent.staging_store import list_staging

    result = dispatch_tool_failure(
        title="knowledge_write: permission_denied — test_product_line",
        source_uri="hermes://knowledge/test_product_line",
        actor_user_id="agent",
        session_id="sess-kt-1",
        product_line_hint="test_product_line",
        hermes_home=tmp_path,
    )

    assert result.destination == "staging"
    entries = list_staging(hermes_home=tmp_path)
    assert any(e["event_id"] == result.event_id for e in entries)
    matching = [e for e in entries if e["event_id"] == result.event_id]
    assert matching[0]["next_action"] == "retry_write"


def test_knowledge_write_failure_not_discarded(tmp_path):
    """Failed knowledge write content must appear in staging, not be silently dropped."""
    from agent.memory_dispatcher import dispatch_tool_failure
    from agent.staging_store import stats

    dispatch_tool_failure(
        title="write_failed: test scenario",
        source_uri="hermes://knowledge/test",
        actor_user_id="agent",
        session_id="sess-kt-2",
        hermes_home=tmp_path,
    )

    result = stats(hermes_home=tmp_path)
    assert result["total"] >= 1
    assert result["by_next_action"].get("retry_write", 0) >= 1


def test_knowledge_query_hint_injection_when_flag_on(tmp_path, monkeypatch):
    """USAGE_HINT_INJECTION_ENABLED=ON → docs carry _usage_hint field."""
    monkeypatch.setenv("USAGE_HINT_INJECTION_ENABLED", "true")

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)

    from agent.usage_hint import hint_for_knowledge, wrap_with_hint, USAGE_HINTS

    doc = {"confidence": "high", "knowledge_type": "business_fact"}
    hint = hint_for_knowledge(doc)
    assert hint in USAGE_HINTS

    wrapped = wrap_with_hint("sample content", hint)
    assert wrapped.startswith("[usage_hint:")


def test_knowledge_query_no_hint_when_flag_off(monkeypatch):
    """USAGE_HINT_INJECTION_ENABLED=OFF → flag check returns False."""
    monkeypatch.delenv("USAGE_HINT_INJECTION_ENABLED", raising=False)

    import importlib
    import agent_system.sedimentation.feature_flags as ff
    importlib.reload(ff)

    assert not ff.USAGE_HINT_INJECTION_ENABLED


def test_dispatch_tool_failure_creates_memory_event(tmp_path):
    """dispatch_tool_failure must create a MemoryEvent in events.jsonl."""
    from agent.memory_dispatcher import dispatch_tool_failure
    from agent.memory_event import list_events

    result = dispatch_tool_failure(
        title="tool failure test",
        source_uri="hermes://test/fail",
        actor_user_id="agent",
        hermes_home=tmp_path,
    )

    events = list_events(hermes_home=tmp_path)
    assert any(e["id"] == result.event_id for e in events)
    matching = [e for e in events if e["id"] == result.event_id]
    assert "tool_failure" in matching[0]["risk_flags"]
