"""
Quality Gate × run_conversation 一致性集成测试（P0-6）

验证真实 AIAgent.run_conversation 接入质量闭环（不用 _simulate_correction_hook）：
  1. 纠偏消息后 _session_boundary_memory 非空（_classify_and_log_correction 真实更新）
  2. quality gate 检测到混题 → _do_quality_rewrite 被调用，final_response == rewrite 结果
  3. rewrite 后 final_response == messages[-1]["content"]（history sync 正确）
  4. QUALITY_LOOP_GATED=false → _do_quality_rewrite 不被调用
  5. _do_quality_rewrite 抛 RuntimeError → fallback，不中断主流程
  6. gate pass（干净答案）→ final_response 原样返回，messages 一致
  7. SQLite session 一致性：rewrite 后 DB messages.content == final_response
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import run_agent
from run_agent import AIAgent


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_tool_defs(*names):
    return [
        {
            "type": "function",
            "function": {
                "name": n,
                "description": n,
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for n in names
    ]


def _mock_response(content="OK", finish_reason="stop"):
    msg = SimpleNamespace(
        content=content, tool_calls=None, reasoning=None,
        reasoning_content=None, reasoning_details=None,
    )
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    resp = SimpleNamespace(choices=[choice], model="test/model")
    resp.usage = None
    return resp


@pytest.fixture()
def quality_agent(monkeypatch):
    """AIAgent with skip_memory + UNDERSTANDING_LOOP_ENABLED + QUALITY_LOOP_GATED."""
    monkeypatch.setenv("UNDERSTANDING_LOOP_ENABLED", "true")
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")
    with (
        patch("run_agent.get_tool_definitions", return_value=_make_tool_defs("web_search")),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        a = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
    a.client = MagicMock()
    a.client.chat.completions.create.return_value = _mock_response("OK")
    return a


# ──────────────────────────────────────────────────────────────────────────────
# 1. 纠偏消息后 _session_boundary_memory 非空
# ──────────────────────────────────────────────────────────────────────────────

def test_run_conversation_correction_updates_boundary_memory(quality_agent):
    """
    UNDERSTANDING_LOOP_ENABLED=true 时，run_conversation 末尾的
    _classify_and_log_correction 处理 separation_correction 并写入 _session_boundary_memory。
    """
    quality_agent.client.chat.completions.create.return_value = _mock_response(
        "好的，我会分开回答两个问题"
    )
    result = quality_agent.run_conversation("这两个问题要分别思考，不要混在一起")
    assert isinstance(result, dict)
    assert result.get("final_response") is not None
    assert len(quality_agent._session_boundary_memory) >= 1, (
        "_classify_and_log_correction 应将 separation_correction 写入 _session_boundary_memory"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2. quality gate 检测混题 → _do_quality_rewrite 被调用，final_response == rewrite 结果
# ──────────────────────────────────────────────────────────────────────────────

def test_run_conversation_quality_gate_fires_on_mixed_answer(quality_agent):
    """
    split_frame=True + 响应含混题关键词 → gate fail → _do_quality_rewrite 被调用
    → final_response == rewrite 结果，不是原始 API 返回。
    """
    quality_agent._session_understanding_state.split_frame = True
    quality_agent.client.chat.completions.create.return_value = _mock_response(
        "综合来看两个问题，它们都需要关注效率问题。"
    )

    with patch.object(quality_agent, "_do_quality_rewrite", return_value="CLEAN_REWRITE") as mock_rewrite:
        result = quality_agent.run_conversation("请分析这两个问题")

    mock_rewrite.assert_called_once()
    assert result["final_response"] == "CLEAN_REWRITE", (
        f"rewrite 后 final_response 应为 'CLEAN_REWRITE'，实际: {result['final_response']!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3. rewrite 后 final_response 与 messages[-1]["content"] 一致
# ──────────────────────────────────────────────────────────────────────────────

def test_run_conversation_final_response_matches_messages(quality_agent):
    """
    quality gate rewrite 后，history sync 必须将 messages[-1]["content"] 同步为
    final_response，不能残留原始未改写内容。
    """
    quality_agent._session_understanding_state.split_frame = True
    quality_agent.client.chat.completions.create.return_value = _mock_response(
        "综合来看两个问题的解法是相同的。"
    )

    with patch.object(quality_agent, "_do_quality_rewrite", return_value="SYNCED_CLEAN_ANSWER"):
        result = quality_agent.run_conversation("分析两个问题")

    final = result["final_response"]
    last_content = result["messages"][-1].get("content")
    assert final == "SYNCED_CLEAN_ANSWER"
    assert last_content == final, (
        f"messages[-1]['content'] ({last_content!r}) 应与 final_response ({final!r}) 一致"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 4. QUALITY_LOOP_GATED=false → _do_quality_rewrite 不被调用
# ──────────────────────────────────────────────────────────────────────────────

def test_run_conversation_gated_false_no_rewrite(monkeypatch):
    """
    QUALITY_LOOP_GATED=false 时，即使响应含混题关键词，_do_quality_rewrite 也不被调用，
    final_response == 原始 API 返回。
    """
    monkeypatch.setenv("UNDERSTANDING_LOOP_ENABLED", "true")
    monkeypatch.delenv("QUALITY_LOOP_GATED", raising=False)

    with (
        patch("run_agent.get_tool_definitions", return_value=_make_tool_defs("web_search")),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        agent = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
    agent.client = MagicMock()
    agent._session_understanding_state.split_frame = True
    MIXED_ANSWER = "综合来看两个问题，答案如下。"
    agent.client.chat.completions.create.return_value = _mock_response(MIXED_ANSWER)

    with patch.object(agent, "_do_quality_rewrite") as mock_rewrite:
        result = agent.run_conversation("请分析两个问题")

    mock_rewrite.assert_not_called()
    assert result["final_response"] == MIXED_ANSWER


# ──────────────────────────────────────────────────────────────────────────────
# 5. _do_quality_rewrite 抛 RuntimeError → fallback，不阻断主流程
# ──────────────────────────────────────────────────────────────────────────────

def test_run_conversation_rewrite_exception_fallback(quality_agent):
    """
    _do_quality_rewrite 抛 RuntimeError（例如非 Anthropic provider）时，
    apply_quality_gate fallback 到原始答案，run_conversation 不被阻断。
    """
    quality_agent._session_understanding_state.split_frame = True
    ORIGINAL = "综合来看这是原始回答，含混题内容。"
    quality_agent.client.chat.completions.create.return_value = _mock_response(ORIGINAL)

    with patch.object(
        quality_agent, "_do_quality_rewrite",
        side_effect=RuntimeError("provider not supported"),
    ):
        result = quality_agent.run_conversation("请分析两个问题")

    assert result.get("final_response") == ORIGINAL, (
        f"rewrite 异常时应 fallback 到原始答案，实际: {result.get('final_response')!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 6. gate pass（干净答案）→ final_response 原样返回，与 messages[-1] 一致
# ──────────────────────────────────────────────────────────────────────────────

def test_run_conversation_gate_pass_response_unchanged(quality_agent):
    """
    干净答案（无混题关键词）→ gate pass → _do_quality_rewrite 不调用，
    final_response == 原始答案，messages[-1]["content"] 同样一致。
    """
    quality_agent._session_understanding_state.split_frame = True
    CLEAN = "这是第一个问题的独立分析结果。"
    quality_agent.client.chat.completions.create.return_value = _mock_response(CLEAN)

    with patch.object(quality_agent, "_do_quality_rewrite") as mock_rewrite:
        result = quality_agent.run_conversation("请回答第一个问题")

    mock_rewrite.assert_not_called()
    assert result["final_response"] == CLEAN
    assert result["messages"][-1].get("content") == CLEAN


# ──────────────────────────────────────────────────────────────────────────────
# 7. SQLite session 一致性（Harness B：真实 session_db）
# ──────────────────────────────────────────────────────────────────────────────

def test_run_conversation_sqlite_session_consistent_after_rewrite(tmp_path, monkeypatch):
    """
    使用真实 HermesState（tmp SQLite）作为 session_db。
    quality gate rewrite 发生后，SQLite messages 表中最后一条 assistant 消息的 content
    与 result["final_response"] 一致，不是 rewrite 前的原始内容。
    """
    from hermes_state import SessionDB

    monkeypatch.setenv("UNDERSTANDING_LOOP_ENABLED", "true")
    monkeypatch.setenv("QUALITY_LOOP_GATED", "true")

    db = SessionDB(db_path=tmp_path / "hermes.db")

    with (
        patch("run_agent.get_tool_definitions", return_value=_make_tool_defs("web_search")),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        agent = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            session_db=db,
        )
    agent.client = MagicMock()
    agent._session_understanding_state.split_frame = True
    ORIGINAL = "综合来看两个问题的答案是相同的。"
    REWRITE = "SQLITE_CONSISTENT_REWRITE"
    agent.client.chat.completions.create.return_value = _mock_response(ORIGINAL)

    with patch.object(agent, "_do_quality_rewrite", return_value=REWRITE):
        result = agent.run_conversation("分析两个问题")

    assert result["final_response"] == REWRITE

    # 从 SQLite 读取最后一条 assistant 消息
    conn = sqlite3.connect(str(tmp_path / "hermes.db"))
    rows = conn.execute(
        "SELECT content FROM messages WHERE role = 'assistant' ORDER BY id DESC LIMIT 1"
    ).fetchall()
    conn.close()

    assert rows, "SQLite messages 表应有 assistant 消息"
    db_content = rows[0][0]
    assert db_content == REWRITE, (
        f"SQLite messages.content ({db_content!r}) 应与 final_response ({REWRITE!r}) 一致"
    )
