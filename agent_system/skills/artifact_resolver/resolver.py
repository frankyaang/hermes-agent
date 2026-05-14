"""Leaf-level artifact resolution for artifact_resolver skill.

Runs entirely in-process — does NOT call delegate_task — to avoid
recursive delegation depth errors.

Resolution priority:
  1. prior_results  — recursively scanned for path keys
  2. inline text    — Markdown links, quoted paths, tilde, relative, absolute
  3. Feishu link    — detected but not resolvable locally → needs_input
  4. task_id / session_id → search known dirs by filename
  5. directory scan — project output dirs, score > 0 required (keyword gate)

Returns:
  {"status": "completed", "path": str, "summary": str, "source": str,
   "candidates": [{"path": str, "source": str}, ...]}
  {"status": "needs_input", "reason": str}
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# ── constants ─────────────────────────────────────────────────────────────────

_REPORT_EXTS = frozenset(
    {"html", "json", "csv", "md", "txt", "pdf", "xlsx", "docx", "png", "jpg", "jpeg"}
)
_EXT_PAT = r"(?:" + "|".join(_REPORT_EXTS) + r")"

_PRIOR_PATH_KEYS = frozenset(
    {"path", "artifact_path", "file_path", "output_path", "main_report_path"}
)

_STOPWORDS = frozenset({
    "请", "帮", "我", "找", "查", "看", "一下", "刚才", "生成", "的", "报告",
    "产物", "文件", "路径", "定位", "上一", "步", "轮", "这", "个", "该",
    "the", "and", "for", "please", "find", "report", "file", "get",
})

_SCAN_LIMIT = 200

_NEEDS_INPUT_REASON = (
    "artifact_resolver needs an artifact path, report title, Feishu link, "
    "or prior result reference. Please provide one of: absolute file path, "
    "report title, Feishu document URL, or task ID."
)

_FEISHU_REASON = (
    "Feishu link detected but no local artifact mapping is available; "
    "provide exported file path or prior result reference"
)

# ── regex patterns ────────────────────────────────────────────────────────────

# Strip the internal agent-system message before keyword extraction
_INTERNAL_MSG_STRIP_RE = re.compile(
    r'\[Hermes Agent System\].*?(?:完成节点\s*`?[A-Za-z0-9_-]+`?。)',
    re.DOTALL,
)

# Feishu document links
_FEISHU_URL_RE = re.compile(
    r'https?://[a-zA-Z0-9\-]+\.feishu\.cn/(?:docx|wiki|base|sheets|drive)/\S+',
    re.IGNORECASE,
)

# task_id / session_id patterns
_TASK_ID_RE = re.compile(
    r'\btask[_\-]?id\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9\-_]{3,})',
    re.IGNORECASE,
)
_SESSION_ID_RE = re.compile(
    r'\bsession[_\-]?id\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9\-_]{3,})',
    re.IGNORECASE,
)

# Path extraction patterns (most-specific first)
_MARKDOWN_LINK_RE = re.compile(
    r'\[[^\]]*\]\(([^)]+\.(?:' + _EXT_PAT + r'))\)',
    re.IGNORECASE,
)
_DQUOTE_PATH_RE = re.compile(
    r'"([^"]{2,}\.(?:' + _EXT_PAT + r'))"',
    re.IGNORECASE,
)
_SQUOTE_PATH_RE = re.compile(
    r"'([^']{2,}\.(?:" + _EXT_PAT + r"))'",
    re.IGNORECASE,
)
_TILDE_PATH_RE = re.compile(
    r'(?<!\w)(~/[^\s，,、。！？\'\"]{1,}\.(?:' + _EXT_PAT + r'))',
    re.IGNORECASE,
)
_REL_PATH_RE = re.compile(
    r'(?<!\w)(\.{1,2}/[^\s，,、。！？\'\"]{1,}\.(?:' + _EXT_PAT + r'))',
    re.IGNORECASE,
)
_ABS_PATH_RE = re.compile(
    r'(?<!\w)(/[^\s，,、。！？\'\"]{1,}\.(?:' + _EXT_PAT + r'))',
    re.IGNORECASE,
)

_TEXT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_MARKDOWN_LINK_RE, "markdown"),
    (_DQUOTE_PATH_RE, "quoted"),
    (_SQUOTE_PATH_RE, "quoted"),
    (_TILDE_PATH_RE, "tilde"),
    (_REL_PATH_RE, "relative"),
    (_ABS_PATH_RE, "absolute"),
]


# ── path helpers ──────────────────────────────────────────────────────────────

def _try_resolve(raw: str) -> Path | None:
    try:
        expanded = os.path.expanduser(raw.strip())
        p = Path(expanded)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve() if p.exists() and p.is_file() else None
    except Exception:
        return None


def _candidate(path: Path, summary: str, source: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "summary": summary,
        "source": source,
        "mtime": path.stat().st_mtime,
        "score": 0,
    }


# ── keyword helpers ───────────────────────────────────────────────────────────

def _strip_internal_prefix(text: str) -> str:
    """Remove system-generated internal message prefix from text."""
    return _INTERNAL_MSG_STRIP_RE.sub("", text).strip()


def _extract_keywords(text: str) -> list[str]:
    words = re.findall(r'[\w\-]{2,}', text, re.UNICODE)
    return [w.lower() for w in words if w.lower() not in _STOPWORDS and not w.isdigit()]


def _extract_ids(message: str, reply_context: str) -> list[str]:
    """Extract task_id and session_id values from all available text."""
    combined = message + " " + reply_context
    ids = []
    for pat in (_TASK_ID_RE, _SESSION_ID_RE):
        ids.extend(m.group(1) for m in pat.finditer(combined))
    return list(dict.fromkeys(ids))  # deduplicate, preserve order


# ── prior_results scanner ─────────────────────────────────────────────────────

def _scan_prior(value: Any, source: str, out: list[dict], depth: int = 0) -> None:
    if depth > 5:
        return
    if isinstance(value, dict):
        for key, v in value.items():
            if key in _PRIOR_PATH_KEYS and isinstance(v, str):
                p = _try_resolve(v)
                if p:
                    out.append(_candidate(p, f"Artifact from {source}:{key}", f"prior_result:{source}"))
            else:
                _scan_prior(v, source, out, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _scan_prior(item, source, out, depth + 1)


def _collect_prior(prior_results: dict[str, Any] | None) -> list[dict]:
    out: list[dict] = []
    if not prior_results:
        return out
    for node_id, result in prior_results.items():
        _scan_prior(result, node_id, out)
    return out


# ── text extraction ───────────────────────────────────────────────────────────

def _collect_text(text: str, source: str) -> list[dict]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for pattern, _kind in _TEXT_PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group(1)
            if raw in seen:
                continue
            seen.add(raw)
            p = _try_resolve(raw)
            if p:
                out.append(_candidate(p, f"File located: {p.name}", source))
    return out


# ── directory scanner ─────────────────────────────────────────────────────────

def _scan_dirs_for(project_root: Path) -> list[Path]:
    """Return candidate scan directories under project_root."""
    dirs: list[Path] = []
    for d in project_root.glob("skills/*/output"):
        if d.is_dir():
            dirs.append(d)
    temp = project_root / "temp"
    if temp.is_dir():
        dirs.append(temp)
    return dirs


def _collect_dirs(project_root: Path, keywords: list[str]) -> list[dict]:
    """Scan known output dirs; only return candidates with score > 0."""
    out: list[dict] = []
    seen_count = 0
    for d in _scan_dirs_for(project_root):
        try:
            entries = list(d.iterdir())
        except PermissionError:
            continue
        for f in entries:
            if seen_count >= _SCAN_LIMIT:
                return out
            if not (f.is_file() and f.suffix.lstrip(".").lower() in _REPORT_EXTS):
                continue
            seen_count += 1
            score = sum(1 for k in keywords if k in f.stem.lower())
            if score == 0:
                continue  # gate: must have at least one keyword match
            c = _candidate(f, f"Found in {d.name}: {f.name}", f"scan:{d.name}")
            c["score"] = score
            out.append(c)
    return out


def _collect_by_id(project_root: Path, ids: list[str]) -> list[dict]:
    """Search known dirs for files whose names contain a task/session ID."""
    out: list[dict] = []
    seen_count = 0
    for d in _scan_dirs_for(project_root):
        try:
            entries = list(d.iterdir())
        except PermissionError:
            continue
        for f in entries:
            if seen_count >= _SCAN_LIMIT:
                return out
            if not (f.is_file() and f.suffix.lstrip(".").lower() in _REPORT_EXTS):
                continue
            seen_count += 1
            matched_id = next((i for i in ids if i.lower() in f.stem.lower()), None)
            if matched_id:
                c = _candidate(f, f"Artifact for id={matched_id}: {f.name}", f"scan_by_id:{d.name}")
                c["score"] = 10  # id match is high-confidence
                out.append(c)
    return out


# ── public API ────────────────────────────────────────────────────────────────

def resolve_artifact(
    *,
    message: str = "",
    reply_context: str = "",
    prior_results: dict[str, Any] | None = None,
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    """Locate an artifact from available context without delegating.

    Returns a completed dict with path + candidates, or needs_input with reason.
    """
    all_candidates: list[dict] = []

    # 1. Prior pipeline results (highest trust, no keyword gate)
    all_candidates.extend(_collect_prior(prior_results))

    # 2. Inline explicit paths in texts (no keyword gate)
    all_candidates.extend(_collect_text(message, "message"))
    all_candidates.extend(_collect_text(reply_context, "reply_context"))

    # Early exit: explicit hits found
    if all_candidates:
        return _build_result(all_candidates)

    # 3. Feishu link detected → cannot resolve locally
    combined = message + " " + reply_context
    if _FEISHU_URL_RE.search(combined):
        return {"status": "needs_input", "reason": _FEISHU_REASON}

    # 4. task_id / session_id → targeted search in known dirs
    if project_root is not None:
        ids = _extract_ids(message, reply_context)
        if ids:
            id_candidates = _collect_by_id(Path(project_root), ids)
            if id_candidates:
                all_candidates.extend(id_candidates)
                return _build_result(all_candidates)
            # IDs extracted but nothing found
            return {
                "status": "needs_input",
                "reason": (
                    f"task/session ID(s) detected ({', '.join(ids)}) but no matching "
                    f"artifact found in known output directories. "
                    + _NEEDS_INPUT_REASON
                ),
            }

    # 5. Keyword-gated directory scan
    # Strip system-generated prefix so internal messages contribute no keywords
    user_text = _strip_internal_prefix(message) + " " + reply_context
    user_keywords = _extract_keywords(user_text)
    if project_root is not None and user_keywords:
        all_candidates.extend(_collect_dirs(Path(project_root), user_keywords))

    if not all_candidates:
        return {"status": "needs_input", "reason": _NEEDS_INPUT_REASON}

    return _build_result(all_candidates)


def _build_result(candidates: list[dict]) -> dict[str, Any]:
    """Sort candidates and build the completed response."""
    def _sort_key(c: dict) -> tuple:
        is_prior = 1 if c["source"].startswith("prior_result") else 0
        return (is_prior, c.get("score", 0), c["mtime"])

    candidates.sort(key=_sort_key, reverse=True)
    best = candidates[0]
    return {
        "status": "completed",
        "path": best["path"],
        "summary": best["summary"],
        "source": best["source"],
        "candidates": [
            {"path": c["path"], "source": c["source"]}
            for c in candidates[:5]
        ],
    }
