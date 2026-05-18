"""
Tests for agent_system.gstack_control.feature_flags.
All flags must default to OFF (safe defaults).
"""
import pytest
from agent_system.gstack_control.feature_flags import (
    GSTACK_FEATURE_FLAGS,
    get_flag,
    is_enabled,
    get_mode,
    is_blocking_allowed,
)


def test_master_switch_off_by_default():
    assert GSTACK_FEATURE_FLAGS["enabled"] is False


def test_mode_is_disabled_by_default():
    assert GSTACK_FEATURE_FLAGS["mode"] == "disabled"


def test_allow_blocking_false_by_default():
    assert GSTACK_FEATURE_FLAGS["allow_blocking"] is False


def test_use_real_gstack_false():
    assert GSTACK_FEATURE_FLAGS["use_real_gstack"] is False


def test_browser_daemon_false():
    assert GSTACK_FEATURE_FLAGS["browser_daemon"] is False


def test_gbrain_false():
    assert GSTACK_FEATURE_FLAGS["gbrain"] is False


def test_telemetry_false():
    assert GSTACK_FEATURE_FLAGS["telemetry"] is False


def test_proactive_mode_false():
    assert GSTACK_FEATURE_FLAGS["proactive_mode"] is False


def test_continuous_checkpoint_false():
    assert GSTACK_FEATURE_FLAGS["continuous_checkpoint"] is False


def test_is_enabled_returns_false():
    assert is_enabled() is False


def test_get_mode_returns_disabled():
    assert get_mode() == "disabled"


def test_is_blocking_allowed_returns_false():
    assert is_blocking_allowed() is False


def test_get_flag_unknown_key_returns_default():
    assert get_flag("nonexistent_key", "fallback") == "fallback"
