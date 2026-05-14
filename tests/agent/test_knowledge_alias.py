"""Tests for agent/knowledge_alias.py — product-line alias resolution."""
from __future__ import annotations
from agent.knowledge_alias import resolve_product_line_alias, COMPANY_SCOPE_ID

def test_cleaning_robot_resolves_to_deebot():
    assert resolve_product_line_alias("cleaning_robot") == "deebot"

def test_chinese_alias_地宝_resolves_to_deebot():
    assert resolve_product_line_alias("地宝") == "deebot"

def test_ecovacs_resolves_to_company_scope():
    assert resolve_product_line_alias("ecovacs") == COMPANY_SCOPE_ID
    assert COMPANY_SCOPE_ID == "ecovacs_company"

def test_科沃斯_resolves_to_company_scope():
    assert resolve_product_line_alias("科沃斯") == "ecovacs_company"

def test_company_resolves_to_company_scope():
    assert resolve_product_line_alias("company") == "ecovacs_company"

def test_unknown_alias_passthrough():
    assert resolve_product_line_alias("lawn_robot") == "lawn_robot"

def test_empty_string_passthrough():
    assert resolve_product_line_alias("") == ""

def test_deebot_canonical_passthrough():
    assert resolve_product_line_alias("deebot") == "deebot"

def test_yiko_full_stack_passthrough():
    assert resolve_product_line_alias("yiko_full_stack") == "yiko_full_stack"
