"""Tests for internal skill call routing guard in cli_bridge.

These tests verify that the message:
  "[Hermes Agent System] 以 system 身份调用 Skill artifact_resolver，完成节点 artifact_resolver。"
(and the backtick variant produced by cli_bridge line 821-822)
does NOT re-trigger planning, artifact_delivery_flow routing, or delegation,
preventing the recursive depth limit error (depth=3, max_spawn_depth=3).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_system.cli_bridge import _parse_internal_skill_call, maybe_run_agent_system_from_message


INTERNAL_MSG = (
    "[Hermes Agent System] 以 system 身份调用 Skill artifact_resolver，完成节点 artifact_resolver。"
)
# Real format produced by cli_bridge.py line 821-822
INTERNAL_MSG_BACKTICK = (
    "[Hermes Agent System] 以 system 身份调用 Skill `artifact_resolver`，完成节点 `artifact_resolver`。"
)

NORMAL_ARTIFACT_MSG = "帮我找刚才生成的报告"


class FakeParentAgent:
    model = "test-model"
    provider = "test-provider"
    base_url = "http://example.test/v1"
    _delegate_depth = 3  # at cap — simulates the real recursion scenario


def _create_project(tmp_path: Path, *, empty_pipeline: bool = True) -> Path:
    """Minimal project with artifact_resolver skill and routes.json."""
    root = tmp_path / "agent_system"
    skill_dir = root / "skills" / "artifact_resolver"
    pipeline_dir = skill_dir / "pipeline"
    pipeline_dir.mkdir(parents=True)

    (skill_dir / "skill.json").write_text(
        json.dumps({
            "name": "artifact_resolver",
            "display_name": "产物定位",
            "description": "定位已有文件、已有输出或历史产物，返回路径和摘要",
            "type": "analysis",
            "pipeline": "artifact_resolver_pipeline",
            "private_memory": True,
            "root": "skills/artifact_resolver",
        }),
        encoding="utf-8",
    )

    pipeline_content = (
        {"name": "artifact_resolver_pipeline", "version": 1, "steps": [], "status": "empty_example_pipeline"}
        if empty_pipeline
        else {"name": "artifact_resolver_pipeline", "version": 1, "steps": [{"id": "s1", "skill": "artifact_resolver"}]}
    )
    (pipeline_dir / "artifact_resolver_pipeline.json").write_text(
        json.dumps(pipeline_content), encoding="utf-8"
    )

    scheduler_dir = root / "scheduler" / "main_scheduler"
    scheduler_dir.mkdir(parents=True)
    (scheduler_dir / "routes.json").write_text(
        json.dumps({
            "pipelines": [
                {
                    "pipeline_id": "artifact_delivery_flow",
                    "pipeline_name": "产物交付",
                    "step": 1,
                    "node": "artifact_resolver",
                    "display_name": "产物定位",
                    "constraints": {},
                    "supervision": {},
                    "user_gate": False,
                }
            ]
        }),
        encoding="utf-8",
    )
    return root


# ── Unit: regex parser ────────────────────────────────────────────────────────

def test_parse_internal_skill_call_matches_no_backticks():
    result = _parse_internal_skill_call(INTERNAL_MSG)
    assert result is not None
    assert result["skill_id"] == "artifact_resolver"
    assert result["node_id"] == "artifact_resolver"


def test_parse_internal_skill_call_strips_backticks():
    """Real cli_bridge output uses backticks; parsed IDs must be clean."""
    result = _parse_internal_skill_call(INTERNAL_MSG_BACKTICK)
    assert result is not None
    assert result["skill_id"] == "artifact_resolver", f"got {result['skill_id']!r}"
    assert result["node_id"] == "artifact_resolver", f"got {result['node_id']!r}"
    assert "`" not in result["skill_id"]
    assert "`" not in result["node_id"]


def test_parse_internal_skill_call_no_match_on_normal_message():
    assert _parse_internal_skill_call(NORMAL_ARTIFACT_MSG) is None
    assert _parse_internal_skill_call("普通对话内容") is None
    assert _parse_internal_skill_call("") is None


# ── Unit: artifact resolver leaf ─────────────────────────────────────────────

def test_artifact_resolver_finds_existing_file(tmp_path: Path):
    from agent_system.skills.artifact_resolver.resolver import resolve_artifact

    report = tmp_path / "monthly_report.html"
    report.write_text("<html>Report content</html>", encoding="utf-8")

    result = resolve_artifact(message=f"请帮我找这个产物：{report}")
    assert result["status"] == "completed"
    assert result["path"] == str(report)
    assert "monthly_report.html" in result["summary"]
    assert "source" in result


def test_artifact_resolver_finds_path_in_reply_context(tmp_path: Path):
    from agent_system.skills.artifact_resolver.resolver import resolve_artifact

    report = tmp_path / "dashboard.html"
    report.write_text("<html>Dashboard</html>", encoding="utf-8")

    result = resolve_artifact(
        message="请定位上一步生成的产物",
        reply_context=f"上一轮产物保存在 {report}",
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)


def test_artifact_resolver_finds_path_in_prior_results(tmp_path: Path):
    from agent_system.skills.artifact_resolver.resolver import resolve_artifact

    report = tmp_path / "insight.html"
    report.write_text("<html>Insight</html>", encoding="utf-8")

    result = resolve_artifact(
        message="请找上一步的产物",
        prior_results={
            "voc_insight": {
                "status": "completed",
                "output": {"artifact_path": str(report), "result_summary": "Insight report"},
            }
        },
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)
    assert result["source"].startswith("prior_result:")


def test_artifact_resolver_needs_input_without_path():
    from agent_system.skills.artifact_resolver.resolver import resolve_artifact

    result = resolve_artifact(message="请帮我找报告")
    assert result["status"] == "needs_input"
    reason = result["reason"]
    assert "artifact_resolver" in reason
    assert any(kw in reason for kw in ("path", "title", "link", "reference"))


# ── T1: internal message does NOT route to artifact_delivery_flow ─────────────

def test_internal_msg_does_not_route_to_artifact_delivery(tmp_path: Path):
    root = _create_project(tmp_path)
    result = maybe_run_agent_system_from_message(
        INTERNAL_MSG,
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is not None
    agent_result = result.get("agent_system_result", {})
    assert agent_result.get("agent_system_internal_skill_call") is True
    assert "artifact_delivery" not in str(agent_result.get("pipeline_id", ""))
    assert result.get("agent_system_status") in ("unsupported", "blocked", "needs_input", "completed")


def test_backtick_internal_msg_does_not_route_to_artifact_delivery(tmp_path: Path):
    """Real cli_bridge output (backtick variant) must also be blocked."""
    root = _create_project(tmp_path)
    result = maybe_run_agent_system_from_message(
        INTERNAL_MSG_BACKTICK,
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is not None
    agent_result = result.get("agent_system_result", {})
    assert agent_result.get("agent_system_internal_skill_call") is True
    assert "artifact_delivery" not in str(agent_result.get("pipeline_id", ""))


# ── T2: internal artifact_resolver does NOT re-delegate ──────────────────────

def test_internal_artifact_resolver_does_not_redelegate(tmp_path: Path):
    root = _create_project(tmp_path)

    with patch("agent_system.cli_bridge._make_delegate_skill_executor") as mock_exec:
        maybe_run_agent_system_from_message(
            INTERNAL_MSG,
            parent_agent=FakeParentAgent(),
            root_dir=root,
        )
        mock_exec.assert_not_called()


def test_backtick_internal_msg_does_not_redelegate(tmp_path: Path):
    root = _create_project(tmp_path)

    with patch("agent_system.cli_bridge._make_delegate_skill_executor") as mock_exec:
        maybe_run_agent_system_from_message(
            INTERNAL_MSG_BACKTICK,
            parent_agent=FakeParentAgent(),
            root_dir=root,
        )
        mock_exec.assert_not_called()


# ── T3: no "Delegation depth limit reached" error ────────────────────────────

def test_no_delegation_depth_limit_reached(tmp_path: Path):
    root = _create_project(tmp_path)
    parent = FakeParentAgent()
    parent._delegate_depth = 3

    result = maybe_run_agent_system_from_message(
        INTERNAL_MSG,
        parent_agent=parent,
        root_dir=root,
    )

    assert result is not None
    assert "Delegation depth limit reached" not in json.dumps(result)


def test_backtick_no_delegation_depth_limit_reached(tmp_path: Path):
    root = _create_project(tmp_path)
    parent = FakeParentAgent()
    parent._delegate_depth = 3

    result = maybe_run_agent_system_from_message(
        INTERNAL_MSG_BACKTICK,
        parent_agent=parent,
        root_dir=root,
    )

    assert result is not None
    assert "Delegation depth limit reached" not in json.dumps(result)


# ── T4: empty pipeline → needs_input with readable reason ────────────────────

def test_empty_pipeline_returns_needs_input_not_failed(tmp_path: Path):
    root = _create_project(tmp_path, empty_pipeline=True)
    result = maybe_run_agent_system_from_message(
        INTERNAL_MSG,
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is not None
    assert result.get("agent_system_status") in ("needs_input", "blocked")
    reason = result.get("agent_system_result", {}).get("reason", "")
    assert "artifact_resolver" in reason
    assert any(kw in reason for kw in ("path", "title", "link", "reference", "pipeline", "implementation"))


# ── T5: explicit user request for artifacts still goes through normal planning ─

def test_normal_artifact_request_not_blocked_as_internal(tmp_path: Path):
    root = _create_project(tmp_path)

    with patch("agent_system.cli_bridge.HermesAgentSystemRuntime") as mock_rt_cls:
        mock_rt = MagicMock()
        mock_rt.run_dynamic_pipeline.return_value = {"status": "success", "output": "ok"}
        mock_rt_cls.return_value = mock_rt

        result = maybe_run_agent_system_from_message(
            NORMAL_ARTIFACT_MSG,
            parent_agent=FakeParentAgent(),
            root_dir=root,
        )

    if result is not None:
        assert not result.get("agent_system_result", {}).get("agent_system_internal_skill_call")
