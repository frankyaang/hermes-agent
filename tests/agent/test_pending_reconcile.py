"""Tests for pending capture reconciliation logic.

Covers dry_run_reconcile, _classify_pending_disposition, replay identity preservation,
and the full write_pending_capture_tx flow.
"""
from __future__ import annotations
import json
import pytest
from pathlib import Path

from agent.knowledge_models import PendingDisposition
from agent.pending_capture import (
    _classify_pending_disposition,
    _resolve_original_user_id,
    dry_run_reconcile,
    list_pending,
    replay_pending,
    write_pending_capture,
    write_pending_capture_tx,
)


# ---------------------------------------------------------------------------
# _resolve_original_user_id
# ---------------------------------------------------------------------------

class TestResolveOriginalUserId:
    def test_explicit_original_user_id_wins(self):
        record = {"original_user_id": "feishu:ou_abc", "user_id": "cli:frank:default"}
        assert _resolve_original_user_id(record) == "feishu:ou_abc"

    def test_platform_user_id_used_when_no_original(self):
        record = {"original_user_id": "", "user_id": "feishu:ou_abc"}
        assert _resolve_original_user_id(record) == "feishu:ou_abc"

    def test_cli_user_id_raises(self):
        record = {"original_user_id": "", "user_id": "cli:frank:default"}
        with pytest.raises(ValueError, match="identity drift"):
            _resolve_original_user_id(record)

    def test_empty_both_raises(self):
        record = {"original_user_id": "", "user_id": ""}
        with pytest.raises(ValueError):
            _resolve_original_user_id(record)

    def test_telegram_identity_accepted(self):
        record = {"original_user_id": "", "user_id": "telegram:u12345"}
        assert _resolve_original_user_id(record) == "telegram:u12345"


# ---------------------------------------------------------------------------
# _classify_pending_disposition
# ---------------------------------------------------------------------------

class TestClassifyPendingDisposition:
    def _rec(self, **kw):
        defaults = {
            "capture_id": "test-id",
            "user_id": "feishu:ou_abc",
            "original_user_id": "",
            "failure_reason": "write_failed:FileNotFoundError",
            "missing_fields": [],
            "candidate_type": "knowledge",
            "scope_id": "ecovacs_company",
            "source_uri": "manual://feishu-dm/test",
            "transaction_id": "",
            "idempotency_key": "",
        }
        defaults.update(kw)
        return defaults

    def test_file_not_found_is_retryable_provider(self):
        result = _classify_pending_disposition(self._rec())
        assert result["disposition"] == PendingDisposition.RETRYABLE_PROVIDER
        assert result["retryable"] is True

    def test_executable_not_found_is_retryable_provider(self):
        result = _classify_pending_disposition(self._rec(failure_reason="provider_unavailable:executable_not_found"))
        assert result["disposition"] == PendingDisposition.RETRYABLE_PROVIDER

    def test_cli_identity_is_blocked_identity(self):
        result = _classify_pending_disposition(self._rec(user_id="cli:frank:default"))
        assert result["disposition"] == PendingDisposition.BLOCKED_IDENTITY
        assert result["retryable"] is False

    def test_explicit_original_user_id_overrides_cli_user_id(self):
        result = _classify_pending_disposition(
            self._rec(user_id="cli:frank:default", original_user_id="feishu:ou_abc")
        )
        assert result["disposition"] == PendingDisposition.RETRYABLE_PROVIDER

    def test_product_line_not_authorized_is_blocked_permission(self):
        result = _classify_pending_disposition(
            self._rec(failure_reason="product_line_not_authorized")
        )
        assert result["disposition"] == PendingDisposition.BLOCKED_PERMISSION
        assert result["retryable"] is False

    def test_missing_scope_and_no_transaction_is_needs_human_review(self):
        result = _classify_pending_disposition(
            self._rec(scope_id="", source_uri="", transaction_id="", idempotency_key="")
        )
        assert result["disposition"] == PendingDisposition.NEEDS_HUMAN_REVIEW

    def test_missing_fields_is_needs_human_review(self):
        result = _classify_pending_disposition(
            self._rec(missing_fields=["product_line_id"])
        )
        assert result["disposition"] == PendingDisposition.NEEDS_HUMAN_REVIEW

    def test_empty_original_user_id_is_blocked_identity(self):
        result = _classify_pending_disposition(self._rec(user_id="", original_user_id=""))
        assert result["disposition"] == PendingDisposition.BLOCKED_IDENTITY

    def test_original_user_id_is_preserved_in_result(self):
        result = _classify_pending_disposition(
            self._rec(original_user_id="feishu:ou_explicit")
        )
        assert result["original_user_id"] == "feishu:ou_explicit"


# ---------------------------------------------------------------------------
# dry_run_reconcile — using tmp fixture files
# ---------------------------------------------------------------------------

class TestDryRunReconcile:
    def _write_pending(self, tmp_path, **kw):
        write_pending_capture(
            title=kw.get("title", "Test"),
            summary=kw.get("summary", "Summary"),
            candidate_type=kw.get("candidate_type", "knowledge"),
            scope_id=kw.get("scope_id", "ecovacs_company"),
            source_uri=kw.get("source_uri", "manual://test"),
            confidence=kw.get("confidence", "verified"),
            missing_fields=kw.get("missing_fields", []),
            failure_reason=kw.get("failure_reason", "write_failed:FileNotFoundError"),
            session_id=kw.get("session_id", "sess-001"),
            user_id=kw.get("user_id", "feishu:ou_abc"),
            hermes_home=tmp_path,
        )

    def test_dry_run_reconcile_classifies_all_pending(self, tmp_path):
        self._write_pending(tmp_path, user_id="feishu:ou_abc", failure_reason="write_failed:FileNotFoundError")
        self._write_pending(tmp_path, user_id="cli:frank:default", failure_reason="product_line_not_authorized")
        results = dry_run_reconcile(hermes_home=tmp_path)
        assert len(results) == 2

    def test_dry_run_does_not_modify_pending_file(self, tmp_path):
        self._write_pending(tmp_path)
        path = tmp_path / "knowledge" / "pending_captures.jsonl"
        before = path.read_text(encoding="utf-8")
        dry_run_reconcile(hermes_home=tmp_path)
        after = path.read_text(encoding="utf-8")
        assert before == after, "dry_run_reconcile must not write to the pending file"

    def test_dry_run_with_empty_pending_returns_empty(self, tmp_path):
        results = dry_run_reconcile(hermes_home=tmp_path)
        assert results == []

    def test_dry_run_mixed_dispositions(self, tmp_path):
        self._write_pending(tmp_path, user_id="feishu:ou_abc", failure_reason="write_failed:FileNotFoundError")
        self._write_pending(tmp_path, user_id="cli:frank:default", failure_reason="product_line_not_authorized")
        results = dry_run_reconcile(hermes_home=tmp_path)
        dispositions = {r["disposition"] for r in results}
        assert PendingDisposition.RETRYABLE_PROVIDER in dispositions
        assert PendingDisposition.BLOCKED_IDENTITY in dispositions


# ---------------------------------------------------------------------------
# replay_pending — identity enforcement
# ---------------------------------------------------------------------------

class TestReplayPendingIdentity:
    def test_replay_blocked_on_cli_identity(self, tmp_path):
        write_pending_capture(
            title="T", summary="S", candidate_type="knowledge",
            scope_id="ecovacs_company", source_uri="manual://test",
            confidence="verified", missing_fields=[],
            failure_reason="write_failed:FileNotFoundError",
            session_id="sess-001", user_id="cli:frank:default",
            hermes_home=tmp_path,
        )
        records = list_pending(hermes_home=tmp_path)
        cid = records[0]["capture_id"]
        result = replay_pending(cid, hermes_home=tmp_path)
        assert result["status"] == "blocked_identity"

    def test_replay_dry_run_returns_original_user_id(self, tmp_path):
        write_pending_capture(
            title="T", summary="S", candidate_type="knowledge",
            scope_id="ecovacs_company", source_uri="manual://test",
            confidence="verified", missing_fields=[],
            failure_reason="write_failed:FileNotFoundError",
            session_id="sess-001", user_id="feishu:ou_abc",
            hermes_home=tmp_path,
        )
        records = list_pending(hermes_home=tmp_path)
        cid = records[0]["capture_id"]
        result = replay_pending(cid, hermes_home=tmp_path, dry_run=True)
        assert result["status"] == "dry_run_ok"
        assert result["original_user_id"] == "feishu:ou_abc"


# ---------------------------------------------------------------------------
# write_pending_capture_tx — full transaction context preservation
# ---------------------------------------------------------------------------

class TestWritePendingCaptureTx:
    def _make_tx(self, **kw):
        from agent.knowledge_models import KnowledgeWriteTransaction, TransactionState, AssetType
        import uuid
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        defaults = dict(
            transaction_id=str(uuid.uuid4()),
            idempotency_key="deadbeef12345678",
            original_user_id="feishu:ou_abc",
            resolved_user_id="feishu:ou_abc",
            platform="feishu",
            source_session_id="20260515_150231_d5806c",
            root_session_id="20260515_150231_d5806c",
            parent_session_id="",
            source_uri="manual://feishu-dm/test",
            asset_type=AssetType.COMPANY_KNOWLEDGE,
            candidate_type="knowledge",
            target_scope_type="product_line",
            target_scope_id="ecovacs_company",
            title="Test Title",
            content_summary="Test content",
            knowledge_type="meeting_conclusion",
            finance_flag=False,
            sensitivity_level="internal",
            confidence="verified",
            doc_slug="test-title",
            provider_name="gbrain_cli",
            current_state=TransactionState.PENDING_CREATED,
            failure_reason="provider_unavailable:executable_not_found",
            failure_category="provider_unavailable:executable_not_found",
            pending_capture_id="",
            created_at=now,
            updated_at=now,
        )
        defaults.update(kw)
        return KnowledgeWriteTransaction(**defaults)

    def test_write_tx_preserves_original_user_id(self, tmp_path):
        tx = self._make_tx(original_user_id="feishu:ou_specialuser")
        write_pending_capture_tx(tx, "content", "test-slug", "meeting_conclusion", False, "internal", hermes_home=tmp_path)
        records = list_pending(hermes_home=tmp_path)
        assert records
        assert records[0]["original_user_id"] == "feishu:ou_specialuser"
        assert records[0]["user_id"] == "feishu:ou_specialuser"

    def test_write_tx_preserves_transaction_id(self, tmp_path):
        tx = self._make_tx()
        write_pending_capture_tx(tx, "content", "test-slug", "meeting_conclusion", False, "internal", hermes_home=tmp_path)
        records = list_pending(hermes_home=tmp_path)
        assert records[0]["transaction_id"] == tx.transaction_id

    def test_write_tx_preserves_idempotency_key(self, tmp_path):
        tx = self._make_tx(idempotency_key="mykey123")
        write_pending_capture_tx(tx, "content", "test-slug", "meeting_conclusion", False, "internal", hermes_home=tmp_path)
        records = list_pending(hermes_home=tmp_path)
        assert records[0]["idempotency_key"] == "mykey123"

    def test_write_tx_preserves_root_session_id(self, tmp_path):
        tx = self._make_tx(root_session_id="20260515_150231_d5806c")
        write_pending_capture_tx(tx, "content", "test-slug", "meeting_conclusion", False, "internal", hermes_home=tmp_path)
        records = list_pending(hermes_home=tmp_path)
        assert records[0]["root_session_id"] == "20260515_150231_d5806c"

    def test_write_tx_preserves_asset_type(self, tmp_path):
        from agent.knowledge_models import AssetType
        tx = self._make_tx(asset_type=AssetType.PRODUCT_LINE_KNOWLEDGE)
        write_pending_capture_tx(tx, "content", "test-slug", "meeting_conclusion", False, "internal", hermes_home=tmp_path)
        records = list_pending(hermes_home=tmp_path)
        assert records[0]["asset_type"] == AssetType.PRODUCT_LINE_KNOWLEDGE
