"""Helpers for routing assistant progress UI out of visible chat text."""

from __future__ import annotations

from dataclasses import dataclass
import re


TASK_PLAN_PROGRESS_HEADING = "### 🧭 任务规划"
EXECUTION_PROGRESS_HEADING = "### 🛠 执行记录"

_TASK_PLAN_TITLES = {"专家层调度", "任务规划", "全局任务规划", "当前阶段任务规划"}
_EXECUTION_TITLES = {"执行记录"}


@dataclass(frozen=True)
class ProgressUiParts:
    task_plan: str | None
    execution_log: str | None
    remainder: str


def _heading_title(line: str) -> str:
    title = (line or "").strip()
    for _ in range(3):
        title = re.sub(r"^#{1,6}\s*", "", title).strip()
        title = re.sub(r"^[🧭🛠]\s*", "", title).strip()
    return title


def _is_task_plan_heading(line: str) -> bool:
    return _heading_title(line) in _TASK_PLAN_TITLES


def _is_execution_heading(line: str) -> bool:
    return _heading_title(line) in _EXECUTION_TITLES


def _next_nonblank_index(lines: list[str], start: int) -> int | None:
    for idx in range(start, len(lines)):
        if lines[idx].strip():
            return idx
    return None


def extract_leading_progress_ui(text: str | None) -> ProgressUiParts:
    """Extract leading task-plan / execution-log UI from assistant text.

    Only leading progress UI is extracted. References to these headings later
    in a normal answer are left untouched.
    """
    if not text:
        return ProgressUiParts(None, None, text or "")

    lines = text.splitlines()
    if not lines:
        return ProgressUiParts(None, None, text)

    first_line = lines[0]
    if not (_is_task_plan_heading(first_line) or _is_execution_heading(first_line)):
        return ProgressUiParts(None, None, text)

    task_plan_lines: list[str] | None = None
    execution_lines: list[str] | None = None
    idx = 0
    remainder_start: int | None = None

    if _is_task_plan_heading(lines[idx]):
        task_plan_lines = [TASK_PLAN_PROGRESS_HEADING]
        idx += 1
        while idx < len(lines):
            line = lines[idx]
            if _is_execution_heading(line):
                break
            if not line.strip():
                next_idx = _next_nonblank_index(lines, idx + 1)
                if next_idx is not None and _is_execution_heading(lines[next_idx]):
                    idx = next_idx
                    break
                remainder_start = idx + 1
                idx = len(lines)
                break
            task_plan_lines.append(line)
            idx += 1

    if idx < len(lines) and _is_execution_heading(lines[idx]):
        idx += 1
        execution_lines = []
        while idx < len(lines):
            line = lines[idx]
            if not line.strip():
                remainder_start = idx + 1
                break
            execution_lines.append(line)
            idx += 1

    remainder = ""
    if remainder_start is not None and remainder_start < len(lines):
        remainder = "\n".join(lines[remainder_start:]).lstrip()

    task_plan = None
    if task_plan_lines:
        task_plan = "\n".join(task_plan_lines).strip()

    execution_log = None
    if execution_lines:
        execution_log = "\n".join(execution_lines).strip()

    return ProgressUiParts(task_plan, execution_log, remainder)


def strip_leading_progress_ui(text: str | None) -> str:
    return extract_leading_progress_ui(text).remainder
