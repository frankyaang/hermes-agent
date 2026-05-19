"""Runtime artifact evidence helpers.

这些字段用于把 JSONL 产物从“只有文件存在”升级为可审计证据：
status / producer_runtime_path / source_capability / sanitized_summary。
"""
from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,}]+"),
]


def sanitize_summary(*parts: Any, max_chars: int = 180) -> str:
    """生成短摘要并遮蔽常见密钥形态。"""
    text = " ".join(str(p) for p in parts if p is not None and str(p).strip())
    text = re.sub(r"\s+", " ", text).strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_redact_match, text)
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "..."
    return text


def _redact_match(match: re.Match[str]) -> str:
    value = match.group(0)
    if value.lower().startswith("bearer "):
        return "Bearer [REDACTED]"
    key_match = re.match(r"(?i)(api[_-]?key|token|secret|password)", value)
    key = key_match.group(1) if key_match else "secret"
    return f"{key}=[REDACTED]"


def with_runtime_evidence(
    record: dict[str, Any],
    *,
    status: str,
    producer_runtime_path: str,
    source_capability: str,
    summary_parts: tuple[Any, ...] = (),
) -> dict[str, Any]:
    """为 record 补齐 evidence 字段，保留已有显式值。"""
    enriched = dict(record)
    enriched.setdefault("status", status)
    enriched.setdefault("producer_runtime_path", producer_runtime_path)
    enriched.setdefault("source_capability", source_capability)
    enriched.setdefault(
        "sanitized_summary",
        sanitize_summary(*summary_parts),
    )
    return enriched
