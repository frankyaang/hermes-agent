"""Select user-facing artifact from pipeline results."""
from __future__ import annotations

import json
import re
from pathlib import Path

_USER_DELIVERABLE_TYPES = {"analysis", "report_generation", "ui_render", "analysis_assist"}
_EXECUTION_LOG_TYPES = {"status_report", "audit"}
_PATH_RE = re.compile(r"(/[^\s]+\.(?:md|txt|html))")


def extract_report_path(summary: str) -> str | None:
    """Extract the first absolute file path from a child agent summary string."""
    m = _PATH_RE.search(summary or "")
    return m.group(1) if m else None


def _skill_type(skill_root: Path) -> str:
    try:
        return json.loads((skill_root / "skill.json").read_text("utf-8")).get("type", "")
    except Exception:
        return ""


def select_output_files(
    skill_output_dirs: dict[str, Path],
    skill_roots: dict[str, Path],
) -> tuple[list[Path], list[Path]]:
    """Classify skill output files into deliverables vs execution logs.

    Returns (deliverable_files, log_files), each sorted newest-first.
    Unknown skill types are treated as deliverables (conservative).
    """
    deliverable: list[Path] = []
    logs: list[Path] = []
    for skill_id, out_dir in skill_output_dirs.items():
        stype = _skill_type(skill_roots.get(skill_id, Path("__none__")))
        files = sorted(out_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            continue
        if stype in _EXECUTION_LOG_TYPES:
            logs.extend(files)
        else:
            deliverable.extend(files)
    return deliverable, logs
