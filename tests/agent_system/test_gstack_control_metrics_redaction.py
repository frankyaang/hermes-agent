"""
Tests for agent_system.gstack_control.metrics_redaction.

Key invariants:
  - token / cookie / Authorization / Bearer / refresh_token are never preserved
  - Non-sensitive keys pass through unchanged
  - Nested dicts are recursively redacted
"""
import pytest
from agent_system.gstack_control.metrics_redaction import redact_dict, redact_string

_REDACTED = "[REDACTED]"


def test_redacts_token_key():
    result = redact_dict({"token": "abc123secret"})
    assert result["token"] == _REDACTED


def test_redacts_authorization_key():
    result = redact_dict({"Authorization": "Bearer eyJhbGciOiJ..."})
    assert result["Authorization"] == _REDACTED


def test_redacts_bearer_key():
    result = redact_dict({"bearer": "some_value"})
    assert result["bearer"] == _REDACTED


def test_redacts_refresh_token_key():
    result = redact_dict({"refresh_token": "xyzRefresh"})
    assert result["refresh_token"] == _REDACTED


def test_redacts_cookie_key():
    result = redact_dict({"cookie": "session=abc; path=/"})
    assert result["cookie"] == _REDACTED


def test_redacts_api_key():
    result = redact_dict({"api_key": "sk-12345678901234567890"})
    assert result["api_key"] == _REDACTED


def test_preserves_safe_keys():
    result = redact_dict({"phase_id": "gstack.qa", "latency_ms": 500})
    assert result["phase_id"] == "gstack.qa"
    assert result["latency_ms"] == 500


def test_recursive_redaction():
    result = redact_dict({"meta": {"token": "secret", "count": 5}})
    assert result["meta"]["token"] == _REDACTED
    assert result["meta"]["count"] == 5


def test_list_values_are_recursively_redacted():
    result = redact_dict({"items": [{"token": "s"}, {"safe": "ok"}]})
    assert result["items"][0]["token"] == _REDACTED
    assert result["items"][1]["safe"] == "ok"


def test_redact_string_strips_bearer():
    s = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc"
    out = redact_string(s)
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert _REDACTED in out


def test_empty_dict_unchanged():
    assert redact_dict({}) == {}


def test_redacts_long_opaque_string_value():
    """A value that looks like a JWT/API key should be redacted."""
    result = redact_dict({"some_field": "A" * 30})
    assert result["some_field"] == _REDACTED


def test_short_values_not_redacted():
    result = redact_dict({"some_field": "short"})
    assert result["some_field"] == "short"
