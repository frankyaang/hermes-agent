"""Tests for agent-system phase-based model routing (dev version).

Covers:
- Node phase classification (_classify_node_phase)
- Config parsing for agent_system.models.{execution,audit}
- delegate_task override_provider/override_model — verified without **kwargs masking
- Kimi fail-closed in _make_delegate_skill_executor
- Codex auth: no CLI token fallback in resolve_codex_runtime_credentials
"""
from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from agent_system.cli_bridge import (
    _classify_node_phase,
    _resolve_all_phase_models,
    _make_delegate_skill_executor,
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

    def test_empty_and_none(self):
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

    def test_falls_back_to_delegation_when_no_structured_models(self):
        cfg = {
            "agent_system": {"models": {}},
            "delegation": {"provider": "openai-codex", "model": "gpt-5.5"},
        }
        phases = self._with_cfg(cfg)
        assert phases["execution"]["provider"] == "openai-codex"
        assert phases["execution"]["model"] == "gpt-5.5"
        assert phases["audit"]["provider"] == "openai-codex"
        assert phases["audit"]["model"] == "gpt-5.5"

    def test_no_kimi_in_correctly_configured_routing(self):
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

    def test_exception_returns_empty_strings(self):
        with patch("hermes_cli.config.load_config", side_effect=RuntimeError("disk error")):
            phases = _resolve_all_phase_models()
        for phase_name in ("planning", "execution", "audit"):
            assert phases[phase_name]["provider"] == ""
            assert phases[phase_name]["model"] == ""


# ── delegate_task override: real signature check (no **kwargs masking) ───────

def _make_mock_parent():
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


class TestDelegateTaskOverride:
    """Verify override_provider/override_model are properly accepted and routed.

    Uses a fake that does NOT accept **kwargs — if delegate_task() tries to pass
    an unexpected kwarg, the inner _build_child_agent mock will raise TypeError
    (not RuntimeError), causing the test to fail with a clear signature error.
    """

    def test_override_provider_reaches_resolve_delegation_credentials(self, monkeypatch):
        from tools.delegate_tool import delegate_task

        resolved_cfgs: list[dict] = []

        def fake_resolve(cfg, parent_agent):
            resolved_cfgs.append(dict(cfg))
            return {
                "model": cfg.get("model") or "gpt-5.5",
                "provider": cfg.get("provider") or "openai-codex",
                "base_url": "https://chatgpt.com/backend-api/codex",
                "api_key": "test-codex-key",
                "api_mode": "codex_responses",
            }

        build_calls: list[dict] = []

        def fake_build(**kwargs):
            build_calls.append(kwargs)
            raise RuntimeError("stop-build")

        monkeypatch.setattr("tools.delegate_tool._resolve_delegation_credentials", fake_resolve)
        monkeypatch.setattr("tools.delegate_tool._build_child_agent", fake_build)

        parent = _make_mock_parent()
        with pytest.raises(RuntimeError, match="stop-build"):
            delegate_task(
                goal="test goal",
                parent_agent=parent,
                override_provider="openai-codex",
                override_model="gpt-5.5",
            )

        assert resolved_cfgs, "_resolve_delegation_credentials must have been called"
        assert resolved_cfgs[0]["provider"] == "openai-codex"
        assert resolved_cfgs[0]["model"] == "gpt-5.5"
        assert build_calls and build_calls[0]["model"] == "gpt-5.5"

    def test_no_override_uses_delegation_config(self, monkeypatch):
        from tools.delegate_tool import delegate_task

        resolved_cfgs: list[dict] = []

        def fake_resolve(cfg, parent_agent):
            resolved_cfgs.append(dict(cfg))
            return {
                "model": "gpt-5.5",
                "provider": "openai-codex",
                "base_url": "https://chatgpt.com/backend-api/codex",
                "api_key": "test-codex-key",
                "api_mode": "codex_responses",
            }

        def fake_build(**kwargs):
            raise RuntimeError("stop-build")

        monkeypatch.setattr("tools.delegate_tool._resolve_delegation_credentials", fake_resolve)
        monkeypatch.setattr("tools.delegate_tool._build_child_agent", fake_build)
        monkeypatch.setattr(
            "tools.delegate_tool._load_config",
            lambda: {"model": "gpt-5.5", "provider": "openai-codex", "max_iterations": 45},
        )

        parent = _make_mock_parent()
        with pytest.raises(RuntimeError, match="stop-build"):
            delegate_task(goal="test goal", parent_agent=parent)

        assert resolved_cfgs, "_resolve_delegation_credentials must have been called"
        assert resolved_cfgs[0].get("provider") == "openai-codex"


# ── Kimi fail-closed in _make_delegate_skill_executor ────────────────────────

class TestKimiFailClosed:
    def _make_executor_context(self, node_id: str) -> dict:
        return {
            "task_package": {
                "node_id": node_id,
                "delegate_task": {},
            },
            "skill_id": "test_skill",
            "expert_id": "test_expert",
            "expert_role": "analyst",
            "requested_skill_id": "test_skill",
            "skill": {},
            "input_payload": {},
            "prior_results": [],
            "max_spawn_depth": 2,
        }

    def test_kimi_execution_node_fails_closed(self, monkeypatch):
        """If execution phase resolves to kimi-for-coding, executor returns status=failed."""
        monkeypatch.setattr(
            "agent_system.cli_bridge._resolve_all_phase_models",
            lambda: {
                "planning": {"provider": "xiamiapi", "model": "claude-opus-4-7"},
                "execution": {"provider": "kimi-coding", "model": "kimi-for-coding"},
                "audit": {"provider": "openai-codex", "model": "gpt-5.5"},
            },
        )

        parent = MagicMock()
        parent.model = "claude-opus-4-7"
        parent.provider = "xiamiapi"
        parent.api_key = "test-key"
        parent.base_url = "https://xiamiapi.xyz/v1"
        parent._client_kwargs = {}
        parent._credential_pool = None

        executor = _make_delegate_skill_executor(parent)
        ctx = self._make_executor_context("voc_insight")
        result = executor(ctx)

        assert result["status"] == "failed"
        assert "ROUTING FAIL-CLOSED" in result["output"]["result_summary"]
        assert "kimi-for-coding" in result["output"]["result_summary"]

    def test_kimi_audit_node_fails_closed(self, monkeypatch):
        """If audit phase resolves to kimi-for-coding, executor returns status=failed."""
        monkeypatch.setattr(
            "agent_system.cli_bridge._resolve_all_phase_models",
            lambda: {
                "planning": {"provider": "xiamiapi", "model": "claude-opus-4-7"},
                "execution": {"provider": "openai-codex", "model": "gpt-5.5"},
                "audit": {"provider": "kimi-coding", "model": "kimi-for-coding"},
            },
        )

        parent = MagicMock()
        parent.model = "claude-opus-4-7"
        parent.provider = "xiamiapi"
        parent.api_key = "test-key"
        parent.base_url = "https://xiamiapi.xyz/v1"
        parent._client_kwargs = {}
        parent._credential_pool = None

        executor = _make_delegate_skill_executor(parent)
        ctx = self._make_executor_context("briefing")
        result = executor(ctx)

        assert result["status"] == "failed"
        assert "ROUTING FAIL-CLOSED" in result["output"]["result_summary"]

    def test_correct_routing_does_not_fail_closed(self, monkeypatch):
        """With openai-codex/gpt-5.5, executor proceeds to delegate_task (no fail-closed)."""
        monkeypatch.setattr(
            "agent_system.cli_bridge._resolve_all_phase_models",
            lambda: {
                "planning": {"provider": "xiamiapi", "model": "claude-opus-4-7"},
                "execution": {"provider": "openai-codex", "model": "gpt-5.5"},
                "audit": {"provider": "openai-codex", "model": "gpt-5.5"},
            },
        )

        called_with: list[dict] = []

        def fake_delegate(goal=None, context=None, role=None, parent_agent=None,
                          override_provider=None, override_model=None):
            # No **kwargs — this fake only accepts the exact params cli_bridge passes.
            # If cli_bridge tries to pass an unknown kwarg, this will TypeError.
            called_with.append({
                "override_provider": override_provider,
                "override_model": override_model,
            })
            return json.dumps({"results": [{"status": "completed", "summary": "ok", "api_calls": 1}]})

        monkeypatch.setattr("tools.delegate_tool.delegate_task", fake_delegate)

        parent = MagicMock()
        parent.model = "claude-opus-4-7"
        parent.provider = "xiamiapi"
        parent.api_key = "test-key"
        parent.base_url = "https://xiamiapi.xyz/v1"
        parent._client_kwargs = {}
        parent._credential_pool = None

        executor = _make_delegate_skill_executor(parent)
        ctx = self._make_executor_context("voc_insight")
        result = executor(ctx)

        assert result["status"] == "completed"
        assert called_with, "delegate_task must have been called"
        assert called_with[0]["override_provider"] == "openai-codex"
        assert called_with[0]["override_model"] == "gpt-5.5"


# ── Codex auth: no CLI token fallback in dev auth.py ────────────────────────

class TestCodexAuthNoCliFallback:
    def test_raises_when_hermes_tokens_missing(self, monkeypatch):
        """Dev resolve_codex_runtime_credentials raises directly when no hermes tokens."""
        from hermes_cli.auth import AuthError, resolve_codex_runtime_credentials

        monkeypatch.setattr(
            "hermes_cli.auth._read_codex_tokens",
            MagicMock(side_effect=AuthError(
                "No Codex credentials stored.",
                provider="openai-codex",
                code="codex_auth_missing",
                relogin_required=True,
            )),
        )

        with pytest.raises(AuthError) as exc_info:
            resolve_codex_runtime_credentials()

        # Dev raises codex_auth_missing (no CLI fallback attempted)
        assert exc_info.value.code == "codex_auth_missing"

    def test_resolves_when_hermes_tokens_present(self, monkeypatch):
        """Normal case: hermes tokens resolve to hermes-auth-store source."""
        from hermes_cli.auth import resolve_codex_runtime_credentials

        fake_data = {
            "tokens": {
                "access_token": "hermes-tok",
                "refresh_token": "hermes-refresh",
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
        assert result["api_key"] == "hermes-tok"
        assert result["provider"] == "openai-codex"
