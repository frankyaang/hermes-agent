"""Tests for agent/knowledge_ops.py — KnowledgeOps Orchestrator.

Covers:
- Golden trace session identification (correct disposition per historical session)
- Identity not-drifted enforcement
- ACL-granted is NOT counted as write success (only provider_succeeded counts)
- David cross-layer knowledge classification
- Provider unavailable → pending with retryable_provider disposition
"""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from agent.knowledge_models import (
    AssetType,
    PendingDisposition,
    ProviderError,
    TransactionState,
)
from agent.knowledge_ops import (
    KnowledgeOpsOrchestrator,
    IdentityError,
    classify_david_knowledge,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ctx(user_id="feishu:ou_abc", product_line_ids=None, is_admin=False):
    from agent.knowledge_models import KnowledgeUserContext
    return KnowledgeUserContext(
        user_id=user_id,
        product_line_ids=product_line_ids or ["ecovacs_company"],
        default_product_line_id="ecovacs_company",
        finance_product_line_ids=[],
        role="member",
        is_admin=is_admin,
    )


def _make_acl(allow=True, reason=""):
    from agent.knowledge_models import AccessDecision
    acl = MagicMock()
    acl.check_write.return_value = AccessDecision(allowed=allow, reason=reason)
    return acl


def _make_provider(succeed=True, slug="pl-ecovacs_company-general-test"):
    provider = MagicMock()
    provider.name = "gbrain_cli"
    if succeed:
        provider.write.return_value = slug
    else:
        from plugins.knowledge.gbrain.provider import ProviderUnavailableError
        provider.write.side_effect = ProviderUnavailableError(
            ProviderError.EXECUTABLE_NOT_FOUND,
            "gbrain executable not found",
        )
    return provider


def _make_audit(tmp_path):
    from agent.knowledge_audit import KnowledgeAuditLogger
    return KnowledgeAuditLogger(audit_dir=tmp_path / "knowledge" / "audit")


def _make_orchestrator(tmp_path, user_id="feishu:ou_abc", allow_acl=True, provider_succeed=True):
    ctx = _make_ctx(user_id=user_id)
    return KnowledgeOpsOrchestrator(
        ctx=ctx,
        provider=_make_provider(succeed=provider_succeed),
        acl=_make_acl(allow=allow_acl),
        audit=_make_audit(tmp_path),
        hermes_home=tmp_path,
    )


WRITE_KWARGS = dict(
    original_user_id="feishu:ou_3a1f0c191d015df426a3a801ac3770c3",
    source_session_id="20260515_150231_d5806c",
    root_session_id="20260515_150231_d5806c",
    parent_session_id="",
    platform="feishu",
    title="香农 Weekly Meeting 定位区别",
    content="香农 Weekly Meeting 与产品线运营 Weekly Meeting 的定位区别",
    product_line_id="ecovacs_company",
    knowledge_type="meeting_conclusion",
    source_uri="manual://feishu-dm/yangzifeng/xiangnong-weeklymeeting-background-2026-05-15",
    finance_flag=False,
    sensitivity_level="internal",
    confidence="verified",
    doc_slug="weekly-meeting-weekly-meeting",
)


# ---------------------------------------------------------------------------
# Golden Trace 1: Feishu identity correct, provider failed → retryable_provider
# ---------------------------------------------------------------------------

class TestGoldenTrace1FeishuProviderFailed:
    """Session 20260515_150231_d5806c: Feishu identity correct, gbrain unavailable."""

    def test_identity_is_feishu_not_cli(self, tmp_path):
        orch = _make_orchestrator(tmp_path, provider_succeed=False)
        result = orch.write(**WRITE_KWARGS)
        # After provider failure the orchestrator creates a pending capture;
        # the terminal state is PENDING_CREATED (not PROVIDER_FAILED).
        assert result["current_state"] in (
            TransactionState.PROVIDER_FAILED, TransactionState.PENDING_CREATED
        ), f"unexpected state: {result['current_state']}"
        assert result["success"] is False

    def test_provider_failed_creates_pending(self, tmp_path):
        orch = _make_orchestrator(tmp_path, provider_succeed=False)
        result = orch.write(**WRITE_KWARGS)
        assert result.get("pending_capture_id"), "must create pending capture on provider failure"

    def test_failure_category_is_provider_unavailable(self, tmp_path):
        orch = _make_orchestrator(tmp_path, provider_succeed=False)
        result = orch.write(**WRITE_KWARGS)
        assert "executable_not_found" in result.get("failure_category", "")

    def test_acl_granted_does_not_count_as_success(self, tmp_path):
        """ACL granted but provider failed → still not success."""
        orch = _make_orchestrator(tmp_path, allow_acl=True, provider_succeed=False)
        result = orch.write(**WRITE_KWARGS)
        assert result["success"] is False, "acl_granted alone must not count as write success"

    def test_pending_preserves_original_user_id(self, tmp_path):
        from agent.pending_capture import list_pending
        orch = _make_orchestrator(tmp_path, provider_succeed=False)
        orch.write(**WRITE_KWARGS)
        records = list_pending(hermes_home=tmp_path)
        assert records, "pending capture must be created"
        rec = records[0]
        # original_user_id must be the Feishu identity, not CLI
        user_in_record = rec.get("original_user_id") or rec.get("user_id", "")
        assert "feishu:" in user_in_record, (
            f"pending must preserve Feishu identity, got {user_in_record!r}"
        )


# ---------------------------------------------------------------------------
# Golden Trace 2: Background review identity drift → blocked_identity
# ---------------------------------------------------------------------------

class TestGoldenTrace2BackgroundReviewIdentityDrift:
    """Session 20260515_152450_a167fb (parent) → background review drifts to cli:frank:default."""

    def test_cli_fallback_identity_is_blocked(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        result = orch.write(
            **{**WRITE_KWARGS, "original_user_id": "cli:frank:default",
               "source_session_id": "39805341-5485-403a-bbc9-bee8f799e0fa"}
        )
        assert result["current_state"] == TransactionState.IDENTITY_BLOCKED
        assert result["success"] is False

    def test_empty_original_user_id_is_blocked(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        result = orch.write(**{**WRITE_KWARGS, "original_user_id": ""})
        assert result["current_state"] == TransactionState.IDENTITY_BLOCKED

    def test_cli_blocked_does_not_create_pending_with_drifted_identity(self, tmp_path):
        from agent.pending_capture import list_pending
        orch = _make_orchestrator(tmp_path)
        orch.write(**{**WRITE_KWARGS, "original_user_id": "cli:frank:default"})
        # No pending should be created for a blocked_identity (identity drift should fail early)
        records = list_pending(hermes_home=tmp_path)
        for rec in records:
            uid = rec.get("original_user_id") or rec.get("user_id", "")
            assert not uid.startswith("cli:"), (
                f"pending must not contain CLI fallback identity, got {uid!r}"
            )

    def test_feishu_identity_not_blocked(self, tmp_path):
        orch = _make_orchestrator(tmp_path, provider_succeed=True)
        result = orch.write(**WRITE_KWARGS)
        assert result["current_state"] != TransactionState.IDENTITY_BLOCKED

    def test_telegram_identity_not_blocked(self, tmp_path):
        orch = _make_orchestrator(tmp_path, provider_succeed=True)
        result = orch.write(**{**WRITE_KWARGS, "original_user_id": "telegram:u12345", "platform": "telegram"})
        assert result["current_state"] != TransactionState.IDENTITY_BLOCKED


# ---------------------------------------------------------------------------
# Golden Trace 3: Zhang Yuan Archimedes — provider failed, correct identity
# ---------------------------------------------------------------------------

class TestGoldenTrace3ZhangYuanProviderFailed:
    """Session 20260515_161113_4f8e6e: Zhang Yuan's Archimedes knowledge, gbrain unavailable."""

    def test_zhang_yuan_identity_is_preserved(self, tmp_path):
        from agent.pending_capture import list_pending
        orch = _make_orchestrator(tmp_path, provider_succeed=False)
        orch.write(**{
            **WRITE_KWARGS,
            "original_user_id": "feishu:ou_92e78aea6cb26fd9f159aa5b367e4e84",
            "source_session_id": "20260515_161113_4f8e6e",
            "title": "阿基米德项目知识",
            "content": "阿基米德项目相关知识内容",
        })
        records = list_pending(hermes_home=tmp_path)
        assert records
        uid = records[0].get("original_user_id") or records[0].get("user_id", "")
        assert uid == "feishu:ou_92e78aea6cb26fd9f159aa5b367e4e84"

    def test_provider_failure_is_classified_as_executable_not_found(self, tmp_path):
        orch = _make_orchestrator(tmp_path, provider_succeed=False)
        result = orch.write(**{
            **WRITE_KWARGS,
            "original_user_id": "feishu:ou_92e78aea6cb26fd9f159aa5b367e4e84",
            "source_session_id": "20260515_161113_4f8e6e",
        })
        assert "executable_not_found" in result.get("failure_category", "")


# ---------------------------------------------------------------------------
# Golden Trace 4: pending replay lacks transaction semantics → needs_human_review
# ---------------------------------------------------------------------------

class TestGoldenTrace4PendingReplayMissingTransactionSemantics:
    """Session 20260515_163628_649025db: pending replay lacks idempotency_key/root_session_id."""

    def test_pending_without_transaction_id_and_missing_scope_needs_human_review(self):
        from agent.pending_capture import _classify_pending_disposition
        record = {
            "capture_id": "9216f5f1-test",
            "user_id": "feishu:ou_92e78aea6cb26fd9f159aa5b367e4e84",
            "original_user_id": "feishu:ou_92e78aea6cb26fd9f159aa5b367e4e84",
            "failure_reason": "write_failed:FileNotFoundError",
            "missing_fields": [],
            "candidate_type": "knowledge",
            "scope_id": "",  # missing scope
            "source_uri": "",  # missing source_uri
            "transaction_id": "",
            "idempotency_key": "",
        }
        result = _classify_pending_disposition(record)
        assert result["disposition"] == PendingDisposition.NEEDS_HUMAN_REVIEW

    def test_pending_with_full_transaction_semantics_is_retryable(self):
        from agent.pending_capture import _classify_pending_disposition
        record = {
            "capture_id": "9216f5f1-test2",
            "user_id": "feishu:ou_92e78aea6cb26fd9f159aa5b367e4e84",
            "original_user_id": "feishu:ou_92e78aea6cb26fd9f159aa5b367e4e84",
            "failure_reason": "provider_unavailable:executable_not_found",
            "missing_fields": [],
            "candidate_type": "knowledge",
            "scope_id": "ecovacs_company",
            "source_uri": "manual://feishu-dm/test",
            "transaction_id": "abc-123",
            "idempotency_key": "deadbeef",
        }
        result = _classify_pending_disposition(record)
        assert result["disposition"] == PendingDisposition.RETRYABLE_PROVIDER
        assert result["retryable"] is True


# ---------------------------------------------------------------------------
# Reconciliation: dry_run_reconcile classifies golden trace pending set
# ---------------------------------------------------------------------------

class TestDryRunReconcile:
    """dry_run_reconcile classifies the 8 real pending captures correctly."""

    _GOLDEN_PENDING = [
        # 5 from platform users (4 Yang Zifeng + 1 Zhang Yuan) — retryable_provider
        {"capture_id": "8b542e4c", "user_id": "feishu:ou_3a1f0c191d015df426a3a801ac3770c3",
         "original_user_id": "", "failure_reason": "write_failed:FileNotFoundError",
         "missing_fields": [], "candidate_type": "knowledge",
         "scope_id": "ecovacs_company", "source_uri": "manual://feishu-dm/test1",
         "transaction_id": "", "idempotency_key": ""},
        {"capture_id": "48182009", "user_id": "feishu:ou_3a1f0c191d015df426a3a801ac3770c3",
         "original_user_id": "", "failure_reason": "write_failed:FileNotFoundError",
         "missing_fields": [], "candidate_type": "knowledge",
         "scope_id": "ecovacs_company", "source_uri": "manual://feishu-dm/test2",
         "transaction_id": "", "idempotency_key": ""},
        {"capture_id": "58502708", "user_id": "feishu:ou_3a1f0c191d015df426a3a801ac3770c3",
         "original_user_id": "", "failure_reason": "write_failed:FileNotFoundError",
         "missing_fields": [], "candidate_type": "knowledge",
         "scope_id": "ecovacs_company", "source_uri": "manual://feishu-dm/test3",
         "transaction_id": "", "idempotency_key": ""},
        {"capture_id": "8d167f23", "user_id": "feishu:ou_3a1f0c191d015df426a3a801ac3770c3",
         "original_user_id": "", "failure_reason": "write_failed:FileNotFoundError",
         "missing_fields": [], "candidate_type": "knowledge",
         "scope_id": "ecovacs_company", "source_uri": "manual://feishu-dm/test4",
         "transaction_id": "", "idempotency_key": ""},
        # 3 from cli:frank:default (background review drift) — blocked_identity
        {"capture_id": "05d78ae6", "user_id": "cli:frank:default",
         "original_user_id": "", "failure_reason": "product_line_not_authorized",
         "missing_fields": [], "candidate_type": "knowledge",
         "scope_id": "ecovacs_company", "source_uri": "manual://feishu-dm/test5",
         "transaction_id": "", "idempotency_key": ""},
        {"capture_id": "2fa523d3", "user_id": "cli:frank:default",
         "original_user_id": "", "failure_reason": "product_line_not_authorized",
         "missing_fields": [], "candidate_type": "knowledge",
         "scope_id": "ecovacs_company", "source_uri": "manual://feishu-dm/test6",
         "transaction_id": "", "idempotency_key": ""},
        {"capture_id": "0ef7002e", "user_id": "cli:frank:default",
         "original_user_id": "", "failure_reason": "product_line_not_authorized",
         "missing_fields": [], "candidate_type": "knowledge",
         "scope_id": "ecovacs_company", "source_uri": "manual://feishu-dm/test7",
         "transaction_id": "", "idempotency_key": ""},
        # 1 from Zhang Yuan (163628) — retryable_provider (has scope+source_uri)
        {"capture_id": "9216f5f1", "user_id": "feishu:ou_92e78aea6cb26fd9f159aa5b367e4e84",
         "original_user_id": "", "failure_reason": "write_failed:FileNotFoundError",
         "missing_fields": [], "candidate_type": "knowledge",
         "scope_id": "deebot", "source_uri": "https://ecovacs.feishu.cn/docx/Fy52dMj20oiF8txEecScjJfInbh",
         "transaction_id": "", "idempotency_key": ""},
    ]

    def test_feishu_captures_classified_as_retryable_provider(self):
        from agent.pending_capture import _classify_pending_disposition
        feishu_records = [r for r in self._GOLDEN_PENDING if "feishu:" in r["user_id"]]
        for rec in feishu_records:
            result = _classify_pending_disposition(rec)
            assert result["disposition"] == PendingDisposition.RETRYABLE_PROVIDER, (
                f"capture {rec['capture_id']} should be retryable_provider, got {result['disposition']}"
            )

    def test_cli_captures_classified_as_blocked_identity(self):
        from agent.pending_capture import _classify_pending_disposition
        cli_records = [r for r in self._GOLDEN_PENDING if r["user_id"].startswith("cli:")]
        assert cli_records, "test data must include cli:frank:default records"
        for rec in cli_records:
            result = _classify_pending_disposition(rec)
            assert result["disposition"] == PendingDisposition.BLOCKED_IDENTITY, (
                f"capture {rec['capture_id']} should be blocked_identity, got {result['disposition']}"
            )

    def test_retryable_have_retryable_true(self):
        from agent.pending_capture import _classify_pending_disposition
        for rec in self._GOLDEN_PENDING:
            result = _classify_pending_disposition(rec)
            if result["disposition"] == PendingDisposition.RETRYABLE_PROVIDER:
                assert result["retryable"] is True

    def test_blocked_identity_have_retryable_false(self):
        from agent.pending_capture import _classify_pending_disposition
        for rec in self._GOLDEN_PENDING:
            result = _classify_pending_disposition(rec)
            if result["disposition"] == PendingDisposition.BLOCKED_IDENTITY:
                assert result["retryable"] is False


# ---------------------------------------------------------------------------
# Audit: lifecycle events are emitted in order
# ---------------------------------------------------------------------------

class TestTransactionAuditEvents:
    def test_successful_write_emits_lifecycle_events(self, tmp_path):
        orch = _make_orchestrator(tmp_path, provider_succeed=True)
        result = orch.write(**WRITE_KWARGS)
        assert result["success"] is True
        audit = _make_audit(tmp_path)
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        events = audit.read_tx_events(month=month)
        event_types = [e["event_type"] for e in events if e.get("transaction_id") == result["transaction_id"]]
        assert TransactionState.CANDIDATE_CREATED in event_types
        assert TransactionState.ACL_GRANTED in event_types
        assert TransactionState.PROVIDER_SUCCEEDED in event_types

    def test_provider_failed_emits_pending_created_event(self, tmp_path):
        orch = _make_orchestrator(tmp_path, provider_succeed=False)
        result = orch.write(**WRITE_KWARGS)
        audit = _make_audit(tmp_path)
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        events = audit.read_tx_events(month=month)
        tx_events = [e for e in events if e.get("transaction_id") == result["transaction_id"]]
        event_types = [e["event_type"] for e in tx_events]
        assert TransactionState.PROVIDER_FAILED in event_types
        assert TransactionState.PENDING_CREATED in event_types

    def test_identity_blocked_does_not_emit_acl_events(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        result = orch.write(**{**WRITE_KWARGS, "original_user_id": "cli:frank:default"})
        audit = _make_audit(tmp_path)
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        events = audit.read_tx_events(month=month)
        tx_events = [e for e in events if e.get("transaction_id") == result.get("transaction_id", "")]
        event_types = [e["event_type"] for e in tx_events]
        assert TransactionState.IDENTITY_BLOCKED in event_types
        assert TransactionState.ACL_GRANTED not in event_types


# ---------------------------------------------------------------------------
# David cross-layer knowledge classification
# ---------------------------------------------------------------------------

class TestDavidKnowledgeClassification:
    def test_david_values_are_company_knowledge(self):
        result = classify_david_knowledge("David's values and decision frameworks")
        assert result["asset_type"] == AssetType.COMPANY_KNOWLEDGE

    def test_user_report_to_david_is_personal_memory(self):
        result = classify_david_knowledge("how to report to David")
        assert result["asset_type"] == AssetType.PERSONAL_MEMORY

    def test_david_instruction_to_product_line_is_product_line_knowledge(self):
        result = classify_david_knowledge("David's directive for deebot product line", scope_hint="deebot")
        assert result["asset_type"] == AssetType.PRODUCT_LINE_KNOWLEDGE

    def test_david_project_meeting_judgment_is_project_knowledge(self):
        result = classify_david_knowledge("David's judgment on project meeting", scope_hint="archimedes")
        assert result["asset_type"] == AssetType.PROJECT_KNOWLEDGE

    def test_david_ceo_org_statement_is_company_knowledge(self):
        result = classify_david_knowledge("David CEO org-level statement on strategy")
        assert result["asset_type"] == AssetType.COMPANY_KNOWLEDGE

    def test_how_to_tell_david_zh_is_personal_memory(self):
        result = classify_david_knowledge("如何向 David 汇报")
        assert result["asset_type"] == AssetType.PERSONAL_MEMORY
