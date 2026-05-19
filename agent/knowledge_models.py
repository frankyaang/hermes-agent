from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KnowledgeUserContext:
    user_id: str
    product_line_ids: list[str]
    default_product_line_id: str
    finance_product_line_ids: list[str]
    role: str
    is_admin: bool
    conversation_access: str = "default"


@dataclass
class KnowledgeDoc:
    slug: str
    title: str
    content: str
    product_line_id: str
    finance_flag: bool
    source_uri: str
    knowledge_type: str
    sensitivity_level: str
    confidence: str
    owner: str
    created_at: str
    updated_at: str
    updated_by: str
    snippet: str = ""


@dataclass
class AccessDecision:
    allowed: bool
    reason: str = ""

    @classmethod
    def allow(cls) -> "AccessDecision":
        return cls(allowed=True)

    @classmethod
    def deny(cls, reason: str) -> "AccessDecision":
        return cls(allowed=False, reason=reason)


@dataclass
class KnowledgeAuditEvent:
    event_id: str
    timestamp: str
    user_id: str
    action: str          # query / write / permission_denied
    product_line_id: str
    finance_flag: bool
    granted: bool
    deny_reason: str = ""
    knowledge_slugs: list[str] = field(default_factory=list)
    source_uris: list[str] = field(default_factory=list)
    query_text: str = ""


class TerminalState:
    KNOWLEDGE_SAVED = "knowledge_saved"
    MEMORY_SAVED = "memory_saved"
    SKILL_SAVED_OR_UPDATED = "skill_saved_or_updated"
    PENDING_CREATED = "pending_created"
    NO_ACTION_WITH_REASON = "no_action_with_reason"
    BLOCKED = "blocked"
    REPLAY_SUCCEEDED = "replay_succeeded"
    REPLAY_FAILED = "replay_failed"
    QUERY_VERIFIED = "query_verified"


class TransactionState:
    """Full lifecycle states for a KnowledgeWriteTransaction."""
    CANDIDATE_CREATED = "candidate_created"
    CLASSIFIED = "classified"
    IDENTITY_RESOLVED = "identity_resolved"
    IDENTITY_BLOCKED = "identity_blocked"
    ACL_GRANTED = "acl_granted"
    ACL_DENIED = "acl_denied"
    PROVIDER_STARTED = "provider_started"
    PROVIDER_SUCCEEDED = "provider_succeeded"
    PROVIDER_FAILED = "provider_failed"
    PENDING_CREATED = "pending_created"
    REPLAY_STARTED = "replay_started"
    REPLAY_SUCCEEDED = "replay_succeeded"
    REPLAY_FAILED = "replay_failed"
    QUERY_VERIFIED = "query_verified"


class CandidateType:
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    SKILL = "skill"


class AssetType:
    """Knowledge asset layering — determines scope and retention policy."""
    PERSONAL_MEMORY = "personal_memory"            # user-private; scoped to user_id
    COMPANY_KNOWLEDGE = "company_knowledge"         # org-wide; ecovacs_company scope
    PRODUCT_LINE_KNOWLEDGE = "product_line_knowledge"  # per product line
    PROJECT_KNOWLEDGE = "project_knowledge"         # time-bound; project scope
    SKILL_EXPERIENCE = "skill_experience"           # reusable workflow/procedure

    # Mapping from asset_class field values used in KnowledgeCandidate
    _FROM_ASSET_CLASS: dict = {
        "person": PERSONAL_MEMORY,
        "user_pref": PERSONAL_MEMORY,
        "company": COMPANY_KNOWLEDGE,
        "product_line": PRODUCT_LINE_KNOWLEDGE,
        "project": PROJECT_KNOWLEDGE,
        "workflow": SKILL_EXPERIENCE,
    }

    @classmethod
    def from_asset_class(cls, asset_class: str) -> str:
        return cls._FROM_ASSET_CLASS.get(asset_class, cls.COMPANY_KNOWLEDGE)


class ProviderError:
    """Error codes for provider-level failures."""
    EXECUTABLE_NOT_FOUND = "executable_not_found"
    DEPENDENCY_MISSING = "dependency_missing"
    LOCK_TIMEOUT = "provider_lock_timeout"
    PERMISSION_DENIED = "provider_permission_denied"
    WRITE_FAILED = "provider_write_failed"
    UNAVAILABLE = "provider_unavailable"

    @classmethod
    def classify(cls, exc: Exception) -> str:
        name = type(exc).__name__
        msg = str(exc).lower()
        if name == "FileNotFoundError":
            return cls.EXECUTABLE_NOT_FOUND
        if "timeout" in msg:
            return cls.LOCK_TIMEOUT
        if "permission" in msg or "denied" in msg:
            return cls.PERMISSION_DENIED
        return cls.WRITE_FAILED


class PendingDisposition:
    """Classification of a pending capture for reconciliation."""
    RETRYABLE_PROVIDER = "retryable_provider"      # provider temporarily unavailable
    BLOCKED_IDENTITY = "blocked_identity"           # original_user_id missing or drifted
    BLOCKED_PERMISSION = "blocked_permission"       # ACL denial (not retryable without config change)
    DUPLICATE = "duplicate"                         # already written (idempotency)
    READY_TO_REPLAY = "ready_to_replay"             # can be replayed now
    NEEDS_HUMAN_REVIEW = "needs_human_review"       # missing required fields or ambiguous


@dataclass
class KnowledgeCandidate:
    candidate_id: str
    candidate_type: str          # CandidateType value
    title: str
    summary: str
    structured_content: dict     # extracted fields, not raw chat log
    source_uri: str
    source_type: str             # feishu_doc / session / manual / agent_system
    origin_session_id: str
    origin_platform: str
    origin_user_id: str
    asset_class: str             # company / product_line / project / person / user_pref / workflow
    target_scope: str            # canonical product_line_id or scope identifier
    confidence: str              # draft / unverified / verified / deprecated
    sensitivity_level: str       # public / internal / confidential / secret
    knowledge_type: str          # from allowed enum
    routing_decision: str        # route_to_knowledge / route_to_memory / route_to_skill / pending / no_action
    routing_reason: str
    missing_fields: list[str] = field(default_factory=list)
    failure_reason: str = ""
    terminal_state: str = ""     # TerminalState value; "" = not yet terminal
    created_at: str = ""


@dataclass
class KnowledgeWriteTransaction:
    """Unified transaction record for the full knowledge write lifecycle.

    All knowledge writes — from initial intent to final query_verified — must
    go through a single transaction. The Orchestrator creates this on
    candidate_created and advances current_state through TransactionState values.
    """
    transaction_id: str
    idempotency_key: str              # hash of (source_uri, title, product_line_id)

    # Identity (immutable once set on candidate_created)
    original_user_id: str             # user who triggered the write intent
    resolved_user_id: str             # matched registry user_id (may differ if alias)
    platform: str
    chat_id: str = ""
    chat_name: str = ""
    chat_type: str = ""

    # Source lineage (immutable once set)
    source_session_id: str = ""       # session that produced the candidate
    root_session_id: str = ""         # top-level session (not a background review)
    parent_session_id: str = ""       # direct parent session (for background reviews)
    source_uri: str = ""
    evidence_snippet: str = ""

    # Asset classification
    asset_type: str = ""              # AssetType value
    candidate_type: str = ""          # CandidateType value
    target_scope_type: str = ""       # "product_line" | "company" | "project" | "user"
    target_scope_id: str = ""

    # Write payload (snapshot at transaction creation)
    title: str = ""
    content_summary: str = ""
    knowledge_type: str = ""
    finance_flag: bool = False
    sensitivity_level: str = "internal"
    confidence: str = "unverified"
    doc_slug: str = ""

    # Provider
    provider_name: str = ""

    # Lifecycle state
    current_state: str = TransactionState.CANDIDATE_CREATED
    failure_reason: str = ""
    failure_category: str = ""        # ProviderError or ACL deny_reason
    pending_capture_id: str = ""      # set when pending_created

    created_at: str = ""
    updated_at: str = ""
