"""Tests for background review identity inheritance.

Verifies that:
1. ContextVar values are inherited by background review threads via copy_context()
2. The review agent receives user_id from the parent session
3. Knowledge writes in background review use the original platform identity
"""
from __future__ import annotations
import contextvars
import threading
from unittest.mock import patch, MagicMock

from gateway.session_context import (
    get_session_env,
    set_session_vars,
    clear_session_vars,
)
from agent.knowledge_models import PendingDisposition
from agent.pending_capture import _classify_pending_disposition


class TestContextVarInheritanceAcrossThreads:
    """ContextVar values must be inherited by threads when copy_context() is used."""

    def test_copy_context_propagates_user_id_to_thread(self):
        tokens = set_session_vars(
            platform="feishu",
            user_id="feishu:ou_testuser",
        )
        captured = {}
        ctx = contextvars.copy_context()

        def _thread_read():
            captured["user_id"] = get_session_env("HERMES_SESSION_USER_ID", "")
            captured["platform"] = get_session_env("HERMES_SESSION_PLATFORM", "")

        t = threading.Thread(target=lambda: ctx.run(_thread_read))
        t.start()
        t.join(timeout=5)
        clear_session_vars(tokens)

        assert captured["user_id"] == "feishu:ou_testuser", (
            f"copy_context() must propagate user_id to thread, got {captured['user_id']!r}"
        )
        assert captured["platform"] == "feishu"

    def test_without_copy_context_thread_loses_user_id(self):
        """Baseline: confirm that without copy_context, thread sees os.environ fallback."""
        import os
        # Ensure os.environ doesn't have the session user set
        saved = os.environ.pop("HERMES_SESSION_USER_ID", None)
        tokens = set_session_vars(platform="feishu", user_id="feishu:ou_testuser")
        captured = {}

        def _thread_read():
            # Without copy_context, contextvars are at default (_UNSET) in this thread
            # so get_session_env falls back to os.environ, which doesn't have it set
            captured["user_id"] = get_session_env("HERMES_SESSION_USER_ID", "NO_VALUE")

        t = threading.Thread(target=_thread_read)
        t.start()
        t.join(timeout=5)
        clear_session_vars(tokens)
        if saved is not None:
            os.environ["HERMES_SESSION_USER_ID"] = saved

        # Without copy_context the thread should NOT see the feishu user
        # (it sees os.environ or the default)
        assert captured["user_id"] != "feishu:ou_testuser", (
            "Baseline test: without copy_context, thread must not see parent's ContextVar"
        )

    def test_background_review_pattern_preserves_feishu_user(self):
        """Simulate the _spawn_background_review fix: copy_context + user_id forwarding."""
        tokens = set_session_vars(platform="feishu", user_id="feishu:ou_parent_user")
        captured = {}

        def _review_work():
            # Simulates what the background review agent does: reads session env
            captured["user_id"] = get_session_env("HERMES_SESSION_USER_ID", "")

        ctx = contextvars.copy_context()
        t = threading.Thread(target=lambda: ctx.run(_review_work), daemon=True, name="bg-review")
        t.start()
        t.join(timeout=5)
        clear_session_vars(tokens)

        assert captured["user_id"] == "feishu:ou_parent_user", (
            f"Background review must inherit Feishu user_id, got {captured['user_id']!r}"
        )


class TestBackgroundReviewIdentityDriftPrevention:
    """Knowledge writes from background review must use the original identity."""

    def test_cli_identity_blocked_by_orchestrator(self):
        """If a background review leaks cli:frank:default, the orchestrator must block it."""
        result = _classify_pending_disposition({
            "capture_id": "bg-drift-001",
            "user_id": "cli:frank:default",
            "original_user_id": "",
            "failure_reason": "product_line_not_authorized",
            "missing_fields": [],
            "candidate_type": "knowledge",
            "scope_id": "ecovacs_company",
            "source_uri": "manual://test",
            "transaction_id": "",
            "idempotency_key": "",
        })
        assert result["disposition"] == PendingDisposition.BLOCKED_IDENTITY, (
            f"CLI fallback from background review drift must be blocked_identity, got {result['disposition']}"
        )

    def test_feishu_identity_from_background_review_is_retryable(self):
        """If background review correctly inherited Feishu identity, it should be retryable."""
        result = _classify_pending_disposition({
            "capture_id": "bg-correct-001",
            "user_id": "feishu:ou_parent_user",
            "original_user_id": "feishu:ou_parent_user",
            "failure_reason": "write_failed:FileNotFoundError",
            "missing_fields": [],
            "candidate_type": "knowledge",
            "scope_id": "ecovacs_company",
            "source_uri": "manual://test",
            "transaction_id": "tx-001",
            "idempotency_key": "key001",
        })
        assert result["disposition"] == PendingDisposition.RETRYABLE_PROVIDER

    def test_session_id_uuid_pattern_indicates_background_review(self):
        """Session IDs matching UUID pattern (not timestamp) are background review sessions."""
        import re
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        )
        bg_session_id = "39805341-5485-403a-bbc9-bee8f799e0fa"
        assert uuid_pattern.match(bg_session_id), (
            "Background review session IDs follow UUID format"
        )
        # A Hermes timestamp session ID does NOT match UUID pattern
        ts_session_id = "20260515_150231_d5806c"
        assert not uuid_pattern.match(ts_session_id)
