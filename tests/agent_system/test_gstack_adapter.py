"""Tests for gstack_control.adapter module."""
from __future__ import annotations

import pytest
from agent_system.gstack_control.adapter import (
    GstackResult,
    GSTACK_KNOWN_COMMANDS,
    detect_gstack,
    run_gstack_dry_run,
    run_gstack_shadow,
    run_gstack_advisory,
    run_gstack_controlled_execution,
    _gstack_command_for,
)


def test_detect_gstack_returns_bool():
    result = detect_gstack()
    assert isinstance(result, bool)


def test_known_commands_contains_expected():
    assert "plan-eng-review" in GSTACK_KNOWN_COMMANDS
    assert "review" in GSTACK_KNOWN_COMMANDS
    assert "qa" in GSTACK_KNOWN_COMMANDS


def test_dry_run_graceful_fallback_when_cli_missing():
    # gstack CLI is not installed in CI / local dev
    result = run_gstack_dry_run("gstack.review")
    assert isinstance(result, GstackResult)
    assert result.exit_code is None or isinstance(result.exit_code, int)
    # If not available, blocked_reason must be set
    if not result.available:
        assert result.blocked_reason != ""
        assert "not found" in result.blocked_reason or "timeout" in result.blocked_reason or "error" in result.blocked_reason


def test_shadow_graceful_fallback():
    result = run_gstack_shadow("gstack.review", {})
    assert isinstance(result, GstackResult)
    if not result.available:
        assert result.blocked_reason != ""


def test_advisory_graceful_fallback():
    result = run_gstack_advisory("gstack.review", {})
    assert isinstance(result, GstackResult)
    if not result.available:
        assert result.blocked_reason != ""


def test_controlled_execution_dry_run_only():
    result = run_gstack_controlled_execution("gstack.qa", {}, dry_run_only=True)
    assert isinstance(result, GstackResult)
    if not result.available:
        assert result.blocked_reason != ""


def test_gstack_command_for_known_phase():
    cmd = _gstack_command_for("gstack.review")
    assert cmd == "review"


def test_gstack_command_for_unknown_phase():
    cmd = _gstack_command_for("gstack.unknown_phase")
    assert isinstance(cmd, str)
    assert cmd != ""


def test_result_stdout_stderr_are_strings():
    result = run_gstack_dry_run("gstack.plan_eng_review")
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)


def test_result_duration_ms_non_negative():
    result = run_gstack_dry_run("gstack.qa")
    assert result.duration_ms >= 0


def test_no_token_in_result(monkeypatch):
    """Ensure adapter sanitizes output through redact_string."""
    import agent_system.gstack_control.adapter as mod
    import subprocess

    class FakeProc:
        returncode = 0
        stdout = "Bearer secret_token_abc123 output"
        stderr = ""

    monkeypatch.setattr(mod, "detect_gstack", lambda: True)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeProc())
    result = run_gstack_dry_run("gstack.review")
    assert "secret_token_abc123" not in result.stdout
    assert "Bearer" not in result.stdout or "[REDACTED]" in result.stdout
