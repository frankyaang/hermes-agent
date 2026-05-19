"""ExperienceCard 主路径行为注入测试。"""
from __future__ import annotations

from agent.memory_event import list_events
from agent.working_memory import WorkingMemory
from run_agent import AIAgent


def _bare_agent(tmp_path):
    agent = object.__new__(AIAgent)
    agent.session_id = "sess-experience-card"
    agent._user_id = "feishu:ou_test"
    agent.platform = "cli"
    agent._working_memory = WorkingMemory(
        session_id=agent.session_id,
        user_id=agent._user_id,
    )
    return agent


def test_experience_card_capture_injects_working_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _bare_agent(tmp_path)

    agent._capture_session_memory(
        original_user_message="David 提到跨产品线优先级需要重新判断",
        interrupted=False,
    )

    entries = agent._working_memory.get_visible_memories()
    assert len(entries) == 1
    assert entries[0].memory_type == "experience"
    assert "usage_hint: action_rule_for_next_task" in entries[0].content
    assert entries[0].metadata["source"] == "experience_card"

    events = list_events(hermes_home=tmp_path)
    assert len(events) == 1
    assert events[0]["status"] == "captured"
    assert events[0]["source_capability"] == "memory_event"


def test_experience_card_capture_without_working_memory_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    agent = _bare_agent(tmp_path)
    agent._working_memory = None

    agent._capture_session_memory(
        original_user_message="David 提到一个需要确认的判断",
        interrupted=False,
    )

    events = list_events(hermes_home=tmp_path)
    assert len(events) == 1
