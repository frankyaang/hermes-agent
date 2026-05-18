"""
Metrics redaction — strip sensitive fields before any write.
Covers: token, cookie, Authorization, Bearer, refresh_token,
and any key matching _SENSITIVE_PATTERNS.
"""
from __future__ import annotations

import re
from typing import Any

_SENSITIVE_PATTERNS = re.compile(
    r"(token|cookie|authorization|bearer|refresh_token|api_key|secret|password|credential)",
    re.IGNORECASE,
)

_REDACTED = "[REDACTED]"


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of data with sensitive keys redacted."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if _SENSITIVE_PATTERNS.search(str(key)):
            result[key] = _REDACTED
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = [
                redact_dict(v) if isinstance(v, dict) else v for v in value
            ]
        elif isinstance(value, str) and _looks_like_secret(value):
            result[key] = _REDACTED
        else:
            result[key] = value
    return result


def redact_string(text: str) -> str:
    """Replace obvious secret patterns in a string."""
    # Bearer <token>
    text = re.sub(r"Bearer\s+\S+", f"Bearer {_REDACTED}", text, flags=re.IGNORECASE)
    # Authorization: <value>
    text = re.sub(
        r"(Authorization:\s*)\S+", rf"\1{_REDACTED}", text, flags=re.IGNORECASE
    )
    return text


def _looks_like_secret(value: str) -> bool:
    """Heuristic: long opaque strings that resemble tokens."""
    if len(value) < 20:
        return False
    # Typical JWT / API key pattern: no whitespace, base64-ish charset
    return bool(re.match(r"^[A-Za-z0-9\-_\.]{20,}$", value))
