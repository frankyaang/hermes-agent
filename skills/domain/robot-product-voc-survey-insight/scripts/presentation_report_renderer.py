#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def sanitize_presentation_text(text: str, banned_phrases: list[str]) -> str:
    sanitized = text
    replacements = {
        "supported": "能直接回答",
        "partial": "只能部分回答",
        "unsupported": "现在还不能定",
    }
    for source_text, target_text in replacements.items():
        sanitized = sanitized.replace(source_text, target_text)
    for phrase in banned_phrases:
        if phrase in {"支持", "不支持", "部分支持"}:
            continue
        sanitized = sanitized.replace(phrase, "")
    return " ".join(sanitized.split()).strip()


def replace_title(report_text: str, new_title: str) -> str:
    lines = report_text.splitlines()
    if lines and lines[0].startswith("# "):
        lines[0] = f"# {new_title}"
    else:
        lines.insert(0, f"# {new_title}")
    return "\n".join(lines)


def insert_lead_lines(report_text: str, leads_by_heading: dict[str, list[str]]) -> str:
    lines = report_text.splitlines()
    rendered: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        rendered.append(line)
        heading = line.strip()
        if heading in leads_by_heading:
            if index + 1 >= len(lines) or lines[index + 1].strip() != "":
                rendered.append("")
            for lead in leads_by_heading[heading]:
                rendered.append(f"- {lead}")
            rendered.append("")
        index += 1
    return "\n".join(rendered)


def render_presentation_main_report(
    report_text: str,
    *,
    style_profile: dict[str, Any],
    new_title: str,
    lead_lines: dict[str, list[str]],
) -> str:
    banned_phrases = list(style_profile.get("banned_phrases", []))
    rewritten = replace_title(report_text, new_title)
    rewritten = insert_lead_lines(rewritten, lead_lines)
    final_lines: list[str] = []
    for raw_line in rewritten.splitlines():
        if raw_line.startswith("- "):
            final_lines.append(f"- {sanitize_presentation_text(raw_line[2:], banned_phrases)}")
        else:
            final_lines.append(raw_line)
    return "\n".join(final_lines).strip() + "\n"


def validate_presentation_main_report_text(report_text: str) -> list[str]:
    required_headings_frontstage = [
        "## 0. 执行摘要",
        "## 1. 结论适用范围",
        "## 2. 看用户",
        "### 2.0 用户根判断",
        "### 2.1 X / T / N 总对比表",
        "### 2.2 系列判断表",
        "### 2.3 关键问题证据表",
        "### 2.4 问题下钻表",
        "### 2.5 边界与不能讲满",
        "### 2.6 真缺口与补数动作",
        "### 2.7 本章小结",
        "## 3. 看竞争",
        "### 3.1 竞争门槛总表",
        "### 3.2 竞争带总对比表",
        "### 3.4 本章小结",
        "## 4. 看自己",
        "### 4.1 系列角色与不做清单",
        "### 4.2 本章小结",
        "## 5. 真缺口与补数计划",
        "## 6. 最终结论",
        "## 附：数据口径与备查表",
    ]
    required_table_headers = [
        "| 一级判断 | 当前结论 | 核心依据 | 主要边界 | 对分工意味着什么 |",
        "| 根判断 | 一句话结论 | 核心支撑 | 当前边界 |",
        "| 对象 | 用户主命题 | 最伤问题 | 最稳锚点 | 证据来源 | 市场口径 | 成熟度 | 当前动作 |",
        "| 对象 | 当前稳定结论 | 为什么成立 | 不要误讲成什么 | 当前不能讲满 |",
        "| 问题 | 伤害的是 | 主要证据 | 影响对象 | 优先级 | 当前边界 |",
        "| 问题 | 主要类型 | 主要场景 | 主要工况 | 用户期待 | 当前判断 |",
        "| 对象 / 范围 | 当前状态 | 为什么不能讲满 | 当前允许怎么讲 |",
        "| 竞争带 | 真正对手 | 真正战场 | 不能讲歪成什么 | 当前最该防什么 | 当前状态 |",
        "| 系列 | 必须承接 | 不再承接 | 错配代价 | 当前不做 |",
        "| 缺口 | 当前状态 | 卡住哪条结论 | 补什么 | 补完后能升级什么 |",
    ]
    if all(heading in report_text for heading in required_headings_frontstage) and all(header in report_text for header in required_table_headers):
        return []

    required_headings_new = [
        "## 0. 问题回答",
        "## 1. 看用户",
        "## 2. 看竞争",
        "## 3. 看自己",
        "## 4. 需求优先级讨论",
        "## 5. 路线图 / 当前动作",
        "## 6. 数据能力声明与附录",
    ]
    if all(heading in report_text for heading in required_headings_new):
        return []

    required_headings_legacy = [
        "## 0. 问题回答",
        "## 1. 分析对象与证据边界",
        "## 2. 一级结论树",
        "## 3. 递归论证",
        "## 4. 反证 / 缺口 / 风险",
        "## 5. 下一步行动（5W2H）",
        "## 6. 数据能力声明与附录",
    ]
    missing = [heading for heading in required_headings_legacy if heading not in report_text]
    return missing
