from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from agent_system.output_selector import extract_report_path, select_output_files


# ---------------------------------------------------------------------------
# Scenario A: user deliverable (analysis) takes priority over execution log
# (status_report) even when log file has a newer mtime.
# ---------------------------------------------------------------------------


def _make_skill(root: Path, name: str, skill_type: str, report_content: str) -> Path:
    skill_dir = root / name
    (skill_dir / "output").mkdir(parents=True)
    skill_json = {"name": name, "type": skill_type}
    (skill_dir / "skill.json").write_text(json.dumps(skill_json), encoding="utf-8")
    report = skill_dir / "output" / "report.md"
    report.write_text(report_content, encoding="utf-8")
    return skill_dir


def test_select_prefers_deliverable_over_log(tmp_path: Path) -> None:
    analysis_root = _make_skill(tmp_path, "voc_insight", "analysis", "# 用户洞察报告")
    briefing_root = _make_skill(tmp_path, "briefing", "status_report", "# 执行简报")

    # Make briefing file appear newer to simulate the old mtime-first bug.
    briefing_report = briefing_root / "output" / "report.md"
    future = time.time() + 60
    import os
    os.utime(briefing_report, (future, future))

    skill_output_dirs = {
        "voc_insight": analysis_root / "output",
        "briefing": briefing_root / "output",
    }
    skill_roots = {
        "voc_insight": analysis_root,
        "briefing": briefing_root,
    }

    deliverable, logs = select_output_files(skill_output_dirs, skill_roots)

    assert deliverable, "Should have at least one deliverable file"
    assert logs, "Should have at least one log file"
    assert deliverable[0].read_text(encoding="utf-8") == "# 用户洞察报告"
    assert all("执行简报" not in f.read_text(encoding="utf-8") for f in deliverable)


# ---------------------------------------------------------------------------
# Scenario B: extract_report_path handles cloud-doc-failure summary correctly.
# ---------------------------------------------------------------------------


def test_extract_report_path_from_cloud_doc_failure_summary() -> None:
    summary = (
        "云文档创建失败（无 create_doc 工具），"
        "主报告已保存至 /tmp/test/report.md"
    )
    result = extract_report_path(summary)
    assert result == "/tmp/test/report.md"


def test_extract_report_path_returns_none_when_no_path() -> None:
    assert extract_report_path("执行完成，无文件输出") is None
    assert extract_report_path("") is None
    assert extract_report_path(None) is None  # type: ignore[arg-type]


def test_extract_report_path_picks_first_path() -> None:
    summary = "生成了 /a/first.md 和 /b/second.md"
    assert extract_report_path(summary) == "/a/first.md"


# ---------------------------------------------------------------------------
# Scenario C: when only execution-log skills have output, return them as logs
# (caller adds the fallback label).
# ---------------------------------------------------------------------------


def test_select_returns_logs_when_no_deliverable(tmp_path: Path) -> None:
    briefing_root = _make_skill(tmp_path, "briefing", "status_report", "# 执行简报")

    skill_output_dirs = {"briefing": briefing_root / "output"}
    skill_roots = {"briefing": briefing_root}

    deliverable, logs = select_output_files(skill_output_dirs, skill_roots)

    assert deliverable == [], "No deliverable expected when only log skills exist"
    assert logs, "Should surface the execution log file"
    assert logs[0].read_text(encoding="utf-8") == "# 执行简报"


def test_select_returns_empty_when_no_output_dirs(tmp_path: Path) -> None:
    deliverable, logs = select_output_files({}, {})
    assert deliverable == []
    assert logs == []


def test_select_treats_unknown_type_as_deliverable(tmp_path: Path) -> None:
    skill_dir = tmp_path / "mystery_skill"
    (skill_dir / "output").mkdir(parents=True)
    (skill_dir / "skill.json").write_text(json.dumps({"name": "mystery", "type": "unknown_future_type"}))
    (skill_dir / "output" / "result.md").write_text("mystery output")

    deliverable, logs = select_output_files(
        {"mystery_skill": skill_dir / "output"},
        {"mystery_skill": skill_dir},
    )
    assert deliverable, "Unknown type should default to deliverable"
    assert logs == []
