"""Tests for scope_resolver — product-line scope classification."""
from __future__ import annotations
from agent.scope_resolver import resolve_scope, ScopeType


def test_cleaning_robot_resolves_to_deebot_product_line():
    scope, scope_type = resolve_scope("cleaning_robot")
    assert scope == "deebot"
    assert scope_type == ScopeType.PRODUCT_LINE


def test_地宝_resolves_to_deebot():
    scope, scope_type = resolve_scope("地宝")
    assert scope == "deebot"
    assert scope_type == ScopeType.PRODUCT_LINE


def test_ecovacs_resolves_to_company():
    scope, scope_type = resolve_scope("ecovacs")
    assert scope == "ecovacs_company"
    assert scope_type == ScopeType.COMPANY


def test_科沃斯_resolves_to_company():
    scope, scope_type = resolve_scope("科沃斯")
    assert scope == "ecovacs_company"
    assert scope_type == ScopeType.COMPANY


def test_company_resolves_to_company():
    scope, scope_type = resolve_scope("company")
    assert scope == "ecovacs_company"
    assert scope_type == ScopeType.COMPANY


def test_deebot_canonical_product_line():
    scope, scope_type = resolve_scope("deebot")
    assert scope == "deebot"
    assert scope_type == ScopeType.PRODUCT_LINE


def test_ecovacs_company_canonical_company():
    scope, scope_type = resolve_scope("ecovacs_company")
    assert scope == "ecovacs_company"
    assert scope_type == ScopeType.COMPANY


def test_unknown_scope_is_product_line_by_default():
    scope, scope_type = resolve_scope("lawn_robot")
    assert scope == "lawn_robot"
    assert scope_type == ScopeType.PRODUCT_LINE


def test_empty_scope_returns_unknown():
    scope, scope_type = resolve_scope("")
    assert scope == ""
    assert scope_type == ScopeType.UNKNOWN


def test_person_scope_keyword_routes_to_company():
    scope, scope_type = resolve_scope("david", asset_class="person")
    assert scope_type == ScopeType.COMPANY
    assert scope == "ecovacs_company"


def test_pbi二期_resolves_to_project():
    scope, scope_type = resolve_scope("pbi二期")
    assert scope == "pbi_v2"
    assert scope_type == ScopeType.PROJECT
