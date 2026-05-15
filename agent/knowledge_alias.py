"""Product-line alias resolution for knowledge system."""
from __future__ import annotations

PRODUCT_LINE_ALIASES: dict[str, str] = {
    "cleaning_robot": "deebot",
    "地宝": "deebot",
    "robot_vacuum": "deebot",
    "扫地机": "deebot",
    "pool_cleaning": "pool_robot",
    "泳池机器人": "pool_robot",
    "window_cleaning": "window_robot",
    "擦窗机": "window_robot",
    "voice": "public_software_voice",
    "yiko": "public_software_voice",
    "依刻": "public_software_voice",
    "ecovacs": "ecovacs_company",
    "科沃斯": "ecovacs_company",
    "company": "ecovacs_company",
    "pbi二期": "pbi_v2",
    "pbi 二期": "pbi_v2",
    "yiko_full_stack": "yiko_full_stack",
}

COMPANY_SCOPE_ID = "ecovacs_company"


def resolve_product_line_alias(raw: str) -> str:
    """Return canonical product_line_id; pass-through if no mapping found."""
    if not raw:
        return raw
    return PRODUCT_LINE_ALIASES.get(raw, raw)
