# agent/scope_resolver.py
"""Scope resolution: alias normalization + company/product_line/project/person classification."""
from __future__ import annotations
from agent.knowledge_alias import resolve_product_line_alias

COMPANY_SCOPE_ID = "ecovacs_company"

_COMPANY_SCOPES = frozenset({
    "ecovacs_company", "ecovacs", "科沃斯", "company",
})

_PROJECT_SCOPE_MAP: dict[str, str] = {
    "pbi_v2": "pbi_v2",
    "pbi二期": "pbi_v2",
    "pbi 二期": "pbi_v2",
}

_PERSON_KEYWORDS = frozenset({"david", "钱程", "ceo"})


class ScopeType:
    COMPANY = "company"
    PRODUCT_LINE = "product_line"
    PROJECT = "project"
    PERSON = "person"
    UNKNOWN = "unknown"


def resolve_scope(raw_scope: str, asset_class: str = "") -> tuple[str, str]:
    """Return (canonical_scope, scope_type).

    Resolution order:
    1. Empty → ("", UNKNOWN)
    2. alias normalization via knowledge_alias
    3. Company keyword check
    4. Project keyword check
    5. Person keyword / asset_class=person → company scope (executive profile)
    6. Default → PRODUCT_LINE
    """
    if not raw_scope:
        return ("", ScopeType.UNKNOWN)

    canonical = resolve_product_line_alias(raw_scope)

    if canonical in _COMPANY_SCOPES or canonical == COMPANY_SCOPE_ID:
        return (COMPANY_SCOPE_ID, ScopeType.COMPANY)

    if canonical in _PROJECT_SCOPE_MAP:
        return (_PROJECT_SCOPE_MAP[canonical], ScopeType.PROJECT)
    if raw_scope in _PROJECT_SCOPE_MAP:
        return (_PROJECT_SCOPE_MAP[raw_scope], ScopeType.PROJECT)

    if raw_scope.lower() in _PERSON_KEYWORDS or asset_class == "person":
        return (COMPANY_SCOPE_ID, ScopeType.COMPANY)

    return (canonical, ScopeType.PRODUCT_LINE)
