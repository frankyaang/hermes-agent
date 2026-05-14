"""Auto-recovery for write_file mid-tool stalls.

Covers the contract between ``run_agent.py`` (which emits
``[[HERMES_DELIVERY_RECOVERY:write_file_stalled]]``) and
``gateway/run.py`` (which detects the marker and re-runs the agent
once).  Validates:

* The recovery helper strips the internal marker before the user sees
  the response.
* Detection triggers exactly one re-run of ``_run_agent``.
* If the retry response still contains the marker, the loop guard
  short-circuits and does not recurse.
* Failed runs are not re-attempted.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.delivery_manager import RECOVERY_MARKER_WRITE_FILE_STALL
from gateway.run import GatewayRunner


def _runner_with_mock_run_agent(retry_result):
    """Build a minimal GatewayRunner stub with _run_agent mocked.

    Only sets the attributes that ``_maybe_recover_write_file_stall``
    touches — everything else is left as MagicMocks so test failures
    point at the recovery path itself, not setup noise.
    """
    runner = object.__new__(GatewayRunner)
    runner._run_agent = AsyncMock(return_value=retry_result)
    return runner


def _make_event():
    return SimpleNamespace(message_id="m1", channel_prompt=None)


def _make_source():
    return SimpleNamespace(platform="feishu", chat_id="c1", user_id="u1")


@pytest.mark.asyncio
async def test_strip_marker_removes_recovery_token():
    text = f"完整正文\n{RECOVERY_MARKER_WRITE_FILE_STALL}"
    assert "HERMES_DELIVERY_RECOVERY" not in GatewayRunner._strip_delivery_recovery_marker(text)


@pytest.mark.asyncio
async def test_strip_marker_handles_empty():
    assert GatewayRunner._strip_delivery_recovery_marker("") == ""
    assert GatewayRunner._strip_delivery_recovery_marker(None) is None


@pytest.mark.asyncio
async def test_no_marker_is_passthrough():
    """When the marker is absent, the helper must NOT call _run_agent."""
    runner = _runner_with_mock_run_agent(retry_result={"final_response": "x"})

    result, response = await runner._maybe_recover_write_file_stall(
        agent_result={"final_response": "all good", "messages": []},
        response="all good",
        source=_make_source(),
        event=_make_event(),
        context_prompt="",
        session_id="s1",
        session_key="k1",
        run_generation=1,
    )

    assert response == "all good"
    assert result["final_response"] == "all good"
    runner._run_agent.assert_not_called()


@pytest.mark.asyncio
async def test_marker_triggers_one_shot_recovery():
    """Marker present → exactly one _run_agent retry, retry's response wins."""
    partial = f"已经写了一半\n{RECOVERY_MARKER_WRITE_FILE_STALL}"
    retry_response = "这是恢复后的完整报告正文。"
    retry_result = {"final_response": retry_response, "messages": []}
    runner = _runner_with_mock_run_agent(retry_result=retry_result)

    result, response = await runner._maybe_recover_write_file_stall(
        agent_result={
            "final_response": partial,
            "messages": [
                {"role": "user", "content": "请生成报告"},
                {"role": "assistant", "content": partial},
            ],
        },
        response=partial,
        source=_make_source(),
        event=_make_event(),
        context_prompt="ctx",
        session_id="s1",
        session_key="k1",
        run_generation=1,
    )

    # Exactly one retry, never more.
    assert runner._run_agent.await_count == 1
    # User-facing response is the retry, marker stripped.
    assert response == retry_response
    assert "HERMES_DELIVERY_RECOVERY" not in response
    # The history passed to _run_agent must also have the marker stripped.
    kwargs = runner._run_agent.await_args.kwargs
    for m in kwargs["history"]:
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            assert "HERMES_DELIVERY_RECOVERY" not in m["content"]
    # The recovery instruction must forbid further write_file usage.
    assert "write_file" in kwargs["message"]


@pytest.mark.asyncio
async def test_marker_in_retry_response_does_not_recurse():
    """If the retry itself emits the marker, the loop guard short-circuits
    instead of recursing.  The user sees a clean partial + a failure note."""
    partial = f"原始一半\n{RECOVERY_MARKER_WRITE_FILE_STALL}"
    # Retry also stalls: response carries the marker again.
    retry_partial = f"恢复也一半\n{RECOVERY_MARKER_WRITE_FILE_STALL}"
    retry_result = {"final_response": retry_partial, "messages": []}
    runner = _runner_with_mock_run_agent(retry_result=retry_result)

    result, response = await runner._maybe_recover_write_file_stall(
        agent_result={"final_response": partial, "messages": []},
        response=partial,
        source=_make_source(),
        event=_make_event(),
        context_prompt="",
        session_id="s1",
        session_key="k1",
        run_generation=1,
    )

    # The helper takes the retry response (also markered) and strips,
    # but does NOT call _run_agent again — that's the loop guard.
    assert runner._run_agent.await_count == 1
    assert "HERMES_DELIVERY_RECOVERY" not in response


@pytest.mark.asyncio
async def test_failed_agent_result_not_retried():
    """Failed runs already have a user-visible error.  Recovery must not
    pile on extra runs."""
    partial = f"部分\n{RECOVERY_MARKER_WRITE_FILE_STALL}"
    runner = _runner_with_mock_run_agent(retry_result={"final_response": "x"})

    result, response = await runner._maybe_recover_write_file_stall(
        agent_result={
            "final_response": partial,
            "messages": [],
            "failed": True,
        },
        response=partial,
        source=_make_source(),
        event=_make_event(),
        context_prompt="",
        session_id="s1",
        session_key="k1",
        run_generation=1,
    )

    runner._run_agent.assert_not_called()
    assert "HERMES_DELIVERY_RECOVERY" not in response


@pytest.mark.asyncio
async def test_retry_exception_falls_back_to_partial():
    """When the retry _run_agent raises, surface the original partial
    (marker stripped) plus a brief failure note."""
    partial = f"部分内容\n{RECOVERY_MARKER_WRITE_FILE_STALL}"
    runner = object.__new__(GatewayRunner)
    runner._run_agent = AsyncMock(side_effect=RuntimeError("network down"))

    _, response = await runner._maybe_recover_write_file_stall(
        agent_result={"final_response": partial, "messages": []},
        response=partial,
        source=_make_source(),
        event=_make_event(),
        context_prompt="",
        session_id="s1",
        session_key="k1",
        run_generation=1,
    )

    assert "HERMES_DELIVERY_RECOVERY" not in response
    assert "部分内容" in response
    assert "自动恢复" in response
