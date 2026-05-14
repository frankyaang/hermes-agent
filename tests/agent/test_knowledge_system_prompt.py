"""Tests for knowledge-capture guidance in the assembled system prompt."""

from run_agent import AIAgent


def _agent(enabled_toolsets):
    return AIAgent(
        model="gpt-5.5",
        api_key="test-key",
        base_url="https://example.test/v1",
        provider="openai-codex",
        enabled_toolsets=enabled_toolsets,
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
    )


def test_knowledge_guidance_is_injected_when_write_tool_is_available():
    agent = _agent(["knowledge"])

    prompt = agent._build_system_prompt()

    assert "Business knowledge capture" in prompt
    assert "Do not wait for the user to explicitly say" in prompt
    assert "knowledge_write" in prompt
    assert "source_uri" in prompt
    assert "pending-capture list" in prompt


def test_knowledge_guidance_is_not_injected_without_write_tool():
    agent = _agent([])

    prompt = agent._build_system_prompt()

    assert "Business knowledge capture" not in prompt
    assert "knowledge_write" not in prompt
