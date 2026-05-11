"""Tests for agent-system phase-based model routing.

Covers:
- Config parsing for agent_system.models.{execution,audit}
- Node phase classification (_classify_node_phase)
- Full routing summary (no kimi in execution/audit)
- delegate_task explicit override_provider/override_model
- Codex auth fail-closed on codex-cli-auth-json source
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent_system.cli_bridge import (
    _classify_node_phase,
    _resolve_all_phase_models,
)


# ── Phase classification ─────────────────────────────────────────────────────

class TestClassifyNodePhase:
    def test_execution_nodes(self):
        for node_id in [
            "voc_insight", "ops_dashboard", "dashboard_html",
            "data_fetch", "competitive_analysis", "user_survey",
        ]:
            assert _classify_node_phase(node_id) == "execution", node_id

    def test_audit_nodes(self):
        for node_id in [
            "briefing", "audit_report", "review_summary",
            "quality_gate", "completion_report", "retrospective",
            "final_briefing", "peer_review", "node_audit",
        ]:
            assert _classify_node_phase(node_id) == "audit", node_id

    def test_empty_node_id(self):
        assert _classify_node_phase("") == "execution"
        assert _classify_node_phase(None) == "execution"

    def test_case_insensitive(self):
        assert _classify_node_phase("BRIEFING") == "audit"
        assert _classify_node_phase("Audit_Summary") == "audit"


# ── Config parsing ───────────────────────────────────────────────────────────

class TestResolveAllPhaseModels:
    def _with_cfg(self, cfg: dict) -> dict:
        with patch("hermes_cli.config.load_config", return_value=cfg):
            return _resolve_all_phase_models()

    def test_structured_config_is_used(self):
        cfg = {
            "agent_system": {
                "models": {
                    "planning": {"provider": "xiamiapi", "model": "claude-opus-4-7"},
                    "execution": {"provider": "openai-codex", "model": "gpt-5.5"},
                    "audit": {"provider": "openai-codex", "model": "gpt-5.5"},
                }
            },
            "delegation": {"provider": "kimi-coding", "model": "kimi-for-coding"},
        }
        phases = self._with_cfg(cfg)
        assert phases["execution"]["provider"] == "openai-codex"
        assert phases["execution"]["model"] == "gpt-5.5"
        assert phases["audit"]["provider"] == "openai-codex"
        assert phases["audit"]["model"] == "gpt-5.5"

    def test_falls_back_to_delegation_when_no_agent_system_models(self):
        cfg = {
            "agent_system": {"models": {}},
            "delegation": {"provider": "openai-codex", "model": "gpt-5.5"},
        }
        phases = self._with_cfg(cfg)
        assert phases["execution"]["provider"] == "openai-codex"
        assert phases["execution"]["model"] == "gpt-5.5"
        assert phases["audit"]["provider"] == "openai-codex"
        assert phases["audit"]["model"] == "gpt-5.5"

    def test_no_kimi_when_config_correct(self):
        cfg = {
            "agent_system": {
                "models": {
                    "execution": {"provider": "openai-codex", "model": "gpt-5.5"},
                    "audit": {"provider": "openai-codex", "model": "gpt-5.5"},
                }
            },
            "delegation": {"provider": "openai-codex", "model": "gpt-5.5"},
        }
        phases = self._with_cfg(cfg)
        for phase_name in ("execution", "audit"):
            assert phases[phase_name]["model"] != "kimi-for-coding", \
                f"{phase_name} must not use kimi-for-coding"
            assert phases[phase_name]["provider"] != "kimi-coding", \
                f"{phase_name} must not use kimi-coding"

    def test_partial_override_uses_delegation_fallback(self):
        # Only execution is structured; audit falls back to delegation
        cfg = {
            "agent_system": {
                "models": {
                    "execution": {"provider": "openai-codex", "model": "gpt-5.5"},
                }
            },
            "delegation": {"provider": "openai-codex", "model": "gpt-5.5"},
        }
        phases = self._with_cfg(cfg)
        assert phases["audit"]["provider"] == "openai-codex"
        assert phases["audit"]["model"] == "gpt-5.5"

    def test_exception_returns_empty_strings(self):
        with patch("hermes_cli.config.load_config", side_effect=RuntimeError("disk error")):
            phases = _resolve_all_phase_models()
        for phase_name in ("planning", "execution", "audit"):
            assert phases[phase_name]["provider"] == ""
            assert phases[phase_name]["model"] == ""


# ── delegate_task explicit override ─────────────────────────────────────────

class TestDelegateTaskOverride:
    def _make_parent(self):
        import threading
        parent = MagicMock()
        parent.base_url = "https://xiamiapi.xyz/v1"
        parent.api_key = "test-key"
        parent.provider = "xiamiapi"
        parent.api_mode = "chat_completions"
        parent.model = "claude-opus-4-7"
        parent.platform = "cli"
        parent.providers_allowed = None
        parent.providers_ignored = None
        parent.providers_order = None
        parent.provider_sort = None
        parent._session_db = None
        parent._delegate_depth = 0
        parent._active_children = []
        parent._active_children_lock = threading.Lock()
        parent._print_fn = None
        parent.tool_progress_callback = None
        parent.thinking_callback = None
        return parent

    def test_override_provider_is_resolved(self, monkeypatch):
        """When override_provider is passed, _resolve_delegation_credentials is called
        with that provider instead of the global delegation.provider."""
        from tools.delegate_tool import delegate_task

        resolved_cfgs = []

        def fake_resolve(cfg, parent_agent):
            resolved_cfgs.append(dict(cfg))
            return {
                "model": cfg.get("model") or "gpt-5.5",
                "provider": cfg.get("provider") or "openai-codex",
                "base_url": "https://chatgpt.com/backend-api/codex",
                "api_key": "test-codex-key",
                "api_mode": "codex_responses",
            }

        monkeypatch.setattr("tools.delegate_tool._resolve_delegation_credentials", fake_resolve)
        # Intercept _build_child_agent to stop execution but still verify resolved_cfgs
        call_kwargs: list[dict] = []
        original_build = None

        def fake_build(**kwargs):
            call_kwargs.append(kwargs)
            raise RuntimeError("stop-here")

        monkeypatch.setattr("tools.delegate_tool._build_child_agent", fake_build)

        parent = self._make_parent()
        # RuntimeError from fake_build propagates out of delegate_task
        with pytest.raises(RuntimeError, match="stop-here"):
            delegate_task(
                goal="test goal",
                parent_agent=parent,
                override_provider="openai-codex",
                override_model="gpt-5.5",
            )
        # _resolve_delegation_credentials must have been called with overridden values
        assert resolved_cfgs, "Expected _resolve_delegation_credentials to be called"
        assert resolved_cfgs[0]["provider"] == "openai-codex"
        assert resolved_cfgs[0]["model"] == "gpt-5.5"
        # The child was built with gpt-5.5
        assert call_kwargs and call_kwargs[0]["model"] == "gpt-5.5"

    def test_no_override_uses_global_config(self, monkeypatch):
        """Without overrides, uses global delegation config as before."""
        from tools.delegate_tool import delegate_task

        resolved_cfgs = []

        def fake_resolve(cfg, parent_agent):
            resolved_cfgs.append(dict(cfg))
            return {
                "model": "gpt-5.5",
                "provider": "openai-codex",
                "base_url": "https://chatgpt.com/backend-api/codex",
                "api_key": "test-codex-key",
                "api_mode": "codex_responses",
            }

        monkeypatch.setattr("tools.delegate_tool._resolve_delegation_credentials", fake_resolve)

        def fake_build(**kwargs):
            raise RuntimeError("stop-here")

        monkeypatch.setattr("tools.delegate_tool._build_child_agent", fake_build)
        monkeypatch.setattr(
            "tools.delegate_tool._load_config",
            lambda: {"model": "gpt-5.5", "provider": "openai-codex", "max_iterations": 45},
        )

        parent = self._make_parent()
        with pytest.raises(RuntimeError, match="stop-here"):
            delegate_task(goal="test goal", parent_agent=parent)
        assert resolved_cfgs, "Expected _resolve_delegation_credentials to be called"
        assert resolved_cfgs[0].get("provider") == "openai-codex"


# ── Codex auth fail-closed ───────────────────────────────────────────────────

class TestCodexAuthFailClosed:
    def test_raises_when_only_cli_tokens_available(self, monkeypatch, tmp_path):
        """When Hermes has no Codex tokens but ~/.codex/auth.json exists, must raise AuthError."""
        from hermes_cli.auth import AuthError, resolve_codex_runtime_credentials, _read_codex_tokens

        fake_cli_tokens = {"access_token": "cli-tok", "refresh_token": "cli-refresh"}

        # Simulate: no hermes tokens
        monkeypatch.setattr(
            "hermes_cli.auth._read_codex_tokens",
            MagicMock(side_effect=AuthError(
                "No Codex credentials stored.",
                provider="openai-codex",
                code="codex_auth_missing",
                relogin_required=True,
            )),
        )
        # Simulate: CLI tokens found
        monkeypatch.setattr(
            "hermes_cli.auth._import_codex_cli_tokens",
            MagicMock(return_value=fake_cli_tokens),
        )

        with pytest.raises(AuthError) as exc_info:
            resolve_codex_runtime_credentials()

        assert exc_info.value.code == "codex_cli_auth_json_rejected"
        assert "hermes auth login openai-codex" in str(exc_info.value)

    def test_does_not_raise_when_hermes_tokens_present(self, monkeypatch):
        """When Hermes has its own tokens, proceed normally without touching CLI tokens."""
        from hermes_cli.auth import resolve_codex_runtime_credentials

        fake_data = {
            "tokens": {
                "access_token": "hermes-access-tok",
                "refresh_token": "hermes-refresh-tok",
            },
            "last_refresh": "2026-01-01T00:00:00Z",
        }
        monkeypatch.setattr(
            "hermes_cli.auth._read_codex_tokens",
            MagicMock(return_value=fake_data),
        )
        monkeypatch.setattr(
            "hermes_cli.auth._codex_access_token_is_expiring",
            MagicMock(return_value=False),
        )

        result = resolve_codex_runtime_credentials()
        assert result["source"] == "hermes-auth-store"
        assert result["api_key"] == "hermes-access-tok"
        assert result["provider"] == "openai-codex"
