"""Unit tests for artifact_resolver leaf resolution (resolver.py).

Coverage targets:
- Absolute path in message
- Tilde (~) path expansion
- Relative (./...) path resolution
- Markdown link path
- Prior results flat key hit
- Prior results deeply nested key hit
- reply_context inline path
- Title keyword search in project output dirs
- Multiple candidates → best (most recent) returned with candidates list
- Nothing found → needs_input with descriptive reason
- Internal backtick message still blocked from delegate
- No "Delegation depth limit reached" in output
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_system.skills.artifact_resolver.resolver import resolve_artifact


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_html(p: Path, content: str = "<html>report</html>") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── path extraction from message ─────────────────────────────────────────────

def test_absolute_path_in_message(tmp_path: Path):
    report = _make_html(tmp_path / "report.html")
    result = resolve_artifact(message=f"请找 {report}")
    assert result["status"] == "completed"
    assert result["path"] == str(report)
    assert result["source"] == "message"


def test_tilde_path_expanded(tmp_path: Path, monkeypatch):
    """~/report.html must expand to home and resolve correctly."""
    monkeypatch.setenv("HOME", str(tmp_path))
    report = _make_html(tmp_path / "tilde_report.html")
    result = resolve_artifact(message="请找 ~/tilde_report.html")
    assert result["status"] == "completed"
    assert result["path"] == str(report)


def test_relative_path_resolved(tmp_path: Path, monkeypatch):
    """./report.html must resolve against cwd."""
    monkeypatch.chdir(tmp_path)
    report = _make_html(tmp_path / "relative_report.html")
    result = resolve_artifact(message="请找 ./relative_report.html")
    assert result["status"] == "completed"
    assert result["path"] == str(report)


def test_markdown_link_path(tmp_path: Path):
    """[text](path) Markdown link must be extracted."""
    report = _make_html(tmp_path / "md_report.html")
    result = resolve_artifact(message=f"报告链接：[查看报告]({report})")
    assert result["status"] == "completed"
    assert result["path"] == str(report)


def test_quoted_path_with_spaces(tmp_path: Path):
    """Quoted paths like "/path/my report.html" must be handled."""
    report = _make_html(tmp_path / "my report.html")
    result = resolve_artifact(message=f'请找 "{report}"')
    assert result["status"] == "completed"
    assert result["path"] == str(report)


# ── prior_results scanning ────────────────────────────────────────────────────

def test_prior_results_flat_key(tmp_path: Path):
    report = _make_html(tmp_path / "flat.html")
    result = resolve_artifact(
        message="找上一步产物",
        prior_results={
            "voc_insight": {
                "status": "completed",
                "output": {"artifact_path": str(report), "result_summary": "Insight report"},
            }
        },
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)
    assert result["source"].startswith("prior_result")


def test_prior_results_nested_key(tmp_path: Path):
    """Deeply nested path key must be found via recursive scan."""
    report = _make_html(tmp_path / "nested.html")
    result = resolve_artifact(
        message="找上一步产物",
        prior_results={
            "html_render": {
                "status": "completed",
                "output": {
                    "nested": {
                        "deep": {"main_report_path": str(report)}
                    }
                },
            }
        },
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)


def test_prior_results_main_report_path(tmp_path: Path):
    report = _make_html(tmp_path / "main.html")
    result = resolve_artifact(
        message="请定位产物",
        prior_results={
            "ops_dashboard": {
                "output": {"main_report_path": str(report)}
            }
        },
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)


# ── reply_context path ────────────────────────────────────────────────────────

def test_reply_context_path(tmp_path: Path):
    report = _make_html(tmp_path / "ctx_report.html")
    result = resolve_artifact(
        message="请定位上一轮的产物",
        reply_context=f"上一轮产物保存在 {report}",
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)
    assert result["source"] == "reply_context"


# ── directory scan (project_root) ─────────────────────────────────────────────

def test_title_keyword_match_in_output_dir(tmp_path: Path):
    """Keyword from message should match a file in skills/*/output/."""
    report = _make_html(tmp_path / "skills" / "ops_dashboard" / "output" / "monthly_report.html")
    result = resolve_artifact(
        message="请找 monthly report",
        project_root=tmp_path,
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)


def test_scan_project_temp_dir(tmp_path: Path):
    report = _make_html(tmp_path / "temp" / "dashboard.html")
    result = resolve_artifact(
        message="找 dashboard",
        project_root=tmp_path,
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)


def test_scan_returns_most_recent_when_multiple(tmp_path: Path):
    """When multiple keyword-matching candidates exist, most recently modified is chosen."""
    old = _make_html(tmp_path / "skills" / "ops_dashboard" / "output" / "monthly_summary.html")
    time.sleep(0.05)
    new = _make_html(tmp_path / "skills" / "ops_dashboard" / "output" / "monthly_dashboard.html")

    result = resolve_artifact(
        message="找 monthly",  # "monthly" is a non-stopword keyword
        project_root=tmp_path,
    )
    assert result["status"] == "completed"
    assert result["path"] == str(new)
    assert "candidates" in result
    assert len(result["candidates"]) >= 2


# ── needs_input ───────────────────────────────────────────────────────────────

def test_needs_input_when_nothing_found():
    result = resolve_artifact(message="请帮我找报告")
    assert result["status"] == "needs_input"
    reason = result["reason"]
    assert "artifact_resolver" in reason
    assert any(kw in reason for kw in ("path", "title", "link", "reference"))


def test_needs_input_has_no_failed_status():
    result = resolve_artifact(message="")
    assert result["status"] != "failed"
    assert result["status"] in ("needs_input", "blocked", "completed")


# ── candidates list ───────────────────────────────────────────────────────────

def test_completed_result_includes_candidates(tmp_path: Path):
    report = _make_html(tmp_path / "report.html")
    result = resolve_artifact(message=f"找 {report}")
    assert result["status"] == "completed"
    assert "candidates" in result
    assert any(c["path"] == str(report) for c in result["candidates"])


# ── regression: recursion guard still works ──────────────────────────────────

def test_backtick_internal_msg_no_delegation(tmp_path: Path):
    """Verify the cli_bridge guard prevents delegate_task for backtick messages."""
    import json as _json
    from agent_system.cli_bridge import maybe_run_agent_system_from_message

    root = tmp_path / "agent_system"
    (root / "skills" / "artifact_resolver" / "pipeline").mkdir(parents=True)
    (root / "skills" / "artifact_resolver" / "skill.json").write_text(
        _json.dumps({"name": "artifact_resolver", "display_name": "产物定位",
                     "description": "d", "type": "analysis",
                     "pipeline": "artifact_resolver_pipeline",
                     "private_memory": True, "root": "skills/artifact_resolver"}),
        encoding="utf-8",
    )
    (root / "skills" / "artifact_resolver" / "pipeline" / "artifact_resolver_pipeline.json").write_text(
        _json.dumps({"name": "artifact_resolver_pipeline", "version": 1, "steps": []}),
        encoding="utf-8",
    )
    (root / "scheduler" / "main_scheduler").mkdir(parents=True)
    (root / "scheduler" / "main_scheduler" / "routes.json").write_text(
        _json.dumps({"pipelines": []}), encoding="utf-8"
    )

    INTERNAL_MSG_BACKTICK = (
        "[Hermes Agent System] 以 system 身份调用 Skill `artifact_resolver`，"
        "完成节点 `artifact_resolver`。"
    )

    class FakeAgent:
        model = "test"; provider = "test"; _delegate_depth = 3

    with patch("agent_system.cli_bridge._make_delegate_skill_executor") as mock_exec:
        result = maybe_run_agent_system_from_message(
            INTERNAL_MSG_BACKTICK,
            parent_agent=FakeAgent(),
            root_dir=root,
        )
        mock_exec.assert_not_called()

    assert result is not None
    assert "Delegation depth limit reached" not in _json.dumps(result)
    assert result.get("agent_system_result", {}).get("agent_system_internal_skill_call") is True


# ── gating: dir scan must not fire on internal-only messages ─────────────────

def test_no_context_internal_msg_returns_needs_input(tmp_path: Path):
    """Pure internal message with no reply_context/prior_results → needs_input.

    Even if output dirs contain files, they must NOT be returned as completed
    when the only context is the system-generated internal skill call message.
    """
    # Put a file in the output dir that might accidentally match
    _make_html(tmp_path / "skills" / "artifact_resolver" / "output" / "artifact_output.html")
    _make_html(tmp_path / "skills" / "ops_dashboard" / "output" / "latest.html")

    internal_msg = (
        "[Hermes Agent System] 以 system 身份调用 Skill `artifact_resolver`，"
        "完成节点 `artifact_resolver`。"
    )
    result = resolve_artifact(
        message=internal_msg,
        reply_context="",
        prior_results=None,
        project_root=tmp_path,
    )
    assert result["status"] == "needs_input", (
        f"Expected needs_input but got {result['status']!r} (path={result.get('path')!r})"
    )


def test_dir_scan_requires_keyword_match(tmp_path: Path):
    """Output dir has files but message has no matching keyword → needs_input."""
    _make_html(tmp_path / "skills" / "ops_dashboard" / "output" / "briefing_report.html")

    result = resolve_artifact(
        message="请找报告",  # all stopwords; no user keyword
        project_root=tmp_path,
    )
    assert result["status"] == "needs_input"


def test_dir_scan_keyword_match_returns_completed(tmp_path: Path):
    """Specific keyword in message → matches file in output dir → completed."""
    report = _make_html(tmp_path / "skills" / "ops_dashboard" / "output" / "q2_briefing.html")

    result = resolve_artifact(
        message="找 q2 briefing",
        project_root=tmp_path,
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)


# ── feishu link detection ─────────────────────────────────────────────────────

def test_feishu_docx_link_returns_needs_input():
    result = resolve_artifact(
        message="请找这个飞书文档：https://example.feishu.cn/docx/AbCdEfGh123"
    )
    assert result["status"] == "needs_input"
    reason = result["reason"]
    assert "Feishu" in reason or "feishu" in reason.lower()
    assert "local artifact" in reason or "mapping" in reason


def test_feishu_wiki_link_returns_needs_input():
    result = resolve_artifact(
        message="文档链接 https://company.feishu.cn/wiki/XyZ789abc"
    )
    assert result["status"] == "needs_input"
    assert "feishu" in result["reason"].lower()


# ── task_id / session_id ──────────────────────────────────────────────────────

def test_task_id_no_match_returns_needs_input(tmp_path: Path):
    """task_id extracted but no file contains it → needs_input."""
    # Put some files in output dir that don't contain the task_id
    _make_html(tmp_path / "skills" / "ops_dashboard" / "output" / "other_report.html")

    result = resolve_artifact(
        message="请找 task_id=task-abc123 的产物",
        project_root=tmp_path,
    )
    assert result["status"] == "needs_input"
    reason = result["reason"]
    assert "task" in reason.lower() or "artifact_resolver" in reason


def test_task_id_file_match_returns_completed(tmp_path: Path):
    """File whose name contains the task_id → completed."""
    report = _make_html(
        tmp_path / "skills" / "ops_dashboard" / "output" / "task-abc123_report.html"
    )
    result = resolve_artifact(
        message="请找 task_id=task-abc123 的报告",
        project_root=tmp_path,
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)


# ── regression: prior_results and reply_context still bypass gate ─────────────

def test_prior_results_still_bypasses_gate(tmp_path: Path):
    """prior_results with valid path → completed without needing dir scan."""
    report = _make_html(tmp_path / "insight.html")
    result = resolve_artifact(
        message="",   # no user keywords at all
        prior_results={"voc_insight": {"output": {"artifact_path": str(report)}}},
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)


def test_reply_context_path_still_bypasses_gate(tmp_path: Path):
    """reply_context with inline path → completed without dir scan."""
    report = _make_html(tmp_path / "ctx.html")
    result = resolve_artifact(
        message="",
        reply_context=f"上一轮产物在 {report}",
    )
    assert result["status"] == "completed"
    assert result["path"] == str(report)
