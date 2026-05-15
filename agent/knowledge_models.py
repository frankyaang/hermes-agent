from __future__ import annotations
from dataclasses import dataclass, field


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


class CandidateType:
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    SKILL = "skill"


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
