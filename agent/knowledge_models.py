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
