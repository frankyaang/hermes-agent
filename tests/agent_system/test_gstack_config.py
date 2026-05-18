"""Tests for gstack_control.config module."""
from __future__ import annotations

import pytest
from agent_system.gstack_control.config import GstackConfig, load_gstack_config


def test_load_gstack_config_returns_safe_defaults_when_no_block():
    cfg = load_gstack_config()
    assert isinstance(cfg, GstackConfig)
    assert cfg.enabled is False
    assert cfg.mode == "disabled"
    assert cfg.allow_blocking is False
    assert cfg.controlled is False
    assert cfg.kill_switch is True
    assert cfg.use_real_gstack is False
    assert cfg.allowlist_phases == []


def test_gstack_config_is_frozen():
    cfg = GstackConfig()
    with pytest.raises((AttributeError, TypeError)):
        cfg.enabled = True  # type: ignore[misc]


def test_gstack_config_budget_defaults():
    cfg = GstackConfig()
    assert cfg.budget_limit_tokens == 4000
    assert cfg.max_runtime_seconds == 30


def test_load_gstack_config_does_not_raise():
    # Should never raise, even if hermes_cli.config is unavailable
    cfg = load_gstack_config()
    assert cfg is not None
