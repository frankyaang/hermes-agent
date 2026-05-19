#!/usr/bin/env python3
"""认知治理工具 — 提供 CognitiveState 快照持久化和 InsightDelta 记录。

两个工具：
  - cognitive_state_snapshot: 将当前认知状态快照写入 HERMES_HOME/cognitive/states.jsonl
  - insight_delta_record:     将 InsightDelta 追加写入 HERMES_HOME/cognitive/insights.jsonl

两者均不修改 MEMORY.md / USER.md，不影响 prompt cache，可独立禁用（关闭 toolset）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_COGNITIVE_DIR_NAME = "cognitive"


def _cognitive_dir() -> Path:
    from hermes_constants import get_hermes_home
    d = get_hermes_home() / _COGNITIVE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def cognitive_state_snapshot(
    known_facts: str,
    unknowns: str,
    assumptions: str,
    confidence_change: str = "",
) -> str:
    """将 CognitiveState 快照追加写入 states.jsonl 并返回确认。"""
    if not known_facts.strip():
        return json.dumps({"error": "known_facts 不能为空"}, ensure_ascii=False)

    record = {
        "type": "cognitive_state",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "known_facts": known_facts.strip(),
        "unknowns": unknowns.strip(),
        "assumptions": assumptions.strip(),
        "confidence_change": confidence_change.strip(),
    }
    try:
        path = _cognitive_dir() / "states.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return json.dumps({"status": "ok", "path": str(path)}, ensure_ascii=False)
    except Exception as e:
        logger.warning("cognitive_state_snapshot 写入失败: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def insight_delta_record(
    insight: str,
    source_evidence: str,
    scope: str,
    generalizable: bool = False,
    delta_type: str = "insight",
) -> str:
    """将 InsightDelta 追加写入 insights.jsonl 并返回确认。"""
    if not insight.strip():
        return json.dumps({"error": "insight 不能为空"}, ensure_ascii=False)
    if not source_evidence.strip():
        return json.dumps({"error": "source_evidence 不能为空（来源证据必填）"}, ensure_ascii=False)
    if delta_type not in ("insight", "gap", "version_conflict"):
        return json.dumps(
            {"error": f"delta_type 必须为 insight/gap/version_conflict，收到：{delta_type}"},
            ensure_ascii=False,
        )

    record = {
        "type": "insight_delta",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "delta_type": delta_type,
        "insight": insight.strip(),
        "source_evidence": source_evidence.strip(),
        "scope": scope.strip(),
        "generalizable": generalizable,
    }
    try:
        path = _cognitive_dir() / "insights.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return json.dumps({"status": "ok", "path": str(path)}, ensure_ascii=False)
    except Exception as e:
        logger.warning("insight_delta_record 写入失败: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def check_cognitive_tool_requirements() -> bool:
    return True


# =============================================================================
# Schemas
# =============================================================================

COGNITIVE_STATE_SNAPSHOT_SCHEMA: Dict[str, Any] = {
    "name": "cognitive_state_snapshot",
    "description": (
        "保存当前认知状态快照（CognitiveState）到本地 JSONL 文件。\n\n"
        "仅在复杂任务（跨层级分析、含版本混用、含隐性前提）中使用。\n"
        "不修改 MEMORY.md，不影响 prompt cache，不自动触发经验沉淀。\n\n"
        "字段说明：\n"
        "- known_facts: 有证据支撑的已知事实（必填）\n"
        "- unknowns: 明确不知道的内容和信息缺口（必填）\n"
        "- assumptions: 当前假设，须标注置信度 high/medium/low（必填）\n"
        "- confidence_change: 相比上一轮，确定性变化说明（可选）"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "known_facts": {
                "type": "string",
                "description": "有证据支撑的已知事实，可引用具体来源",
            },
            "unknowns": {
                "type": "string",
                "description": "明确不知道的内容，包含信息缺口（图片遮挡、文件缺失等）",
            },
            "assumptions": {
                "type": "string",
                "description": "当前假设，无直接证据但合理的推断，标注置信度 high/medium/low",
            },
            "confidence_change": {
                "type": "string",
                "description": "相比上一轮，哪里确定性提升了/降低了（可选）",
            },
        },
        "required": ["known_facts", "unknowns", "assumptions"],
    },
}

INSIGHT_DELTA_RECORD_SCHEMA: Dict[str, Any] = {
    "name": "insight_delta_record",
    "description": (
        "记录一条 InsightDelta（新增洞察或信息缺口）到本地 JSONL 文件。\n\n"
        "规则：\n"
        "- source_evidence 必填，不允许'综合判断'作为唯一来源\n"
        "- gap 类型只标记缺口位置，不填充缺口内容\n"
        "- 不修改 MEMORY.md，不影响 prompt cache\n\n"
        "delta_type 可选值：\n"
        "- insight: 新增洞察\n"
        "- gap: 信息缺口\n"
        "- version_conflict: 版本冲突"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "insight": {
                "type": "string",
                "description": "洞察内容或缺口描述（必填）",
            },
            "source_evidence": {
                "type": "string",
                "description": "引用具体来源，不允许'综合判断'作为唯一来源（必填）",
            },
            "scope": {
                "type": "string",
                "description": "这个洞察在哪个 scope 内有效",
            },
            "generalizable": {
                "type": "boolean",
                "description": "是否可推广到其他场景（true）或仅限本次任务（false）",
                "default": False,
            },
            "delta_type": {
                "type": "string",
                "enum": ["insight", "gap", "version_conflict"],
                "description": "洞察类型",
                "default": "insight",
            },
        },
        "required": ["insight", "source_evidence", "scope"],
    },
}


def cognitive_state_query(last_n: int = 5) -> str:
    """读取最近 N 条 CognitiveState 快照，返回 JSON 列表。"""
    path = _cognitive_dir() / "states.jsonl"
    if not path.exists():
        return json.dumps([], ensure_ascii=False)
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    records = []
    for line in lines[-last_n:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return json.dumps(records, ensure_ascii=False)


def insight_delta_query(last_n: int = 10, delta_type: str = "") -> str:
    """读取最近 N 条 InsightDelta 记录，可按 delta_type 过滤，返回 JSON 列表。"""
    path = _cognitive_dir() / "insights.jsonl"
    if not path.exists():
        return json.dumps([], ensure_ascii=False)
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    records = []
    for line in lines:
        try:
            rec = json.loads(line)
            if delta_type and rec.get("delta_type") != delta_type:
                continue
            records.append(rec)
        except json.JSONDecodeError:
            pass
    return json.dumps(records[-last_n:], ensure_ascii=False)


# =============================================================================
# Schemas (read tools)
# =============================================================================

COGNITIVE_STATE_QUERY_SCHEMA: Dict[str, Any] = {
    "name": "cognitive_state_query",
    "description": (
        "读取最近 N 条 CognitiveState 快照，返回 JSON 数组。\n\n"
        "用于跨轮次引用认知状态历史，不写入任何文件。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "last_n": {
                "type": "integer",
                "description": "返回最近 N 条记录（默认 5）",
                "default": 5,
            },
        },
        "required": [],
    },
}

INSIGHT_DELTA_QUERY_SCHEMA: Dict[str, Any] = {
    "name": "insight_delta_query",
    "description": (
        "读取最近 N 条 InsightDelta 记录，可按 delta_type 过滤，返回 JSON 数组。\n\n"
        "delta_type 可选：insight | gap | version_conflict | 空字符串（不过滤）"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "last_n": {
                "type": "integer",
                "description": "返回最近 N 条记录（默认 10）",
                "default": 10,
            },
            "delta_type": {
                "type": "string",
                "description": "过滤 delta_type（空字符串 = 不过滤）",
                "default": "",
            },
        },
        "required": [],
    },
}


# =============================================================================
# Registry
# =============================================================================

from tools.registry import registry, tool_error  # noqa: E402

registry.register(
    name="cognitive_state_snapshot",
    toolset="cognitive_governance",
    schema=COGNITIVE_STATE_SNAPSHOT_SCHEMA,
    handler=lambda args, **kw: cognitive_state_snapshot(
        known_facts=args.get("known_facts", ""),
        unknowns=args.get("unknowns", ""),
        assumptions=args.get("assumptions", ""),
        confidence_change=args.get("confidence_change", ""),
    ),
    check_fn=check_cognitive_tool_requirements,
    description="保存 CognitiveState 快照到 HERMES_HOME/cognitive/states.jsonl",
    emoji="🧠",
)

registry.register(
    name="insight_delta_record",
    toolset="cognitive_governance",
    schema=INSIGHT_DELTA_RECORD_SCHEMA,
    handler=lambda args, **kw: insight_delta_record(
        insight=args.get("insight", ""),
        source_evidence=args.get("source_evidence", ""),
        scope=args.get("scope", ""),
        generalizable=args.get("generalizable", False),
        delta_type=args.get("delta_type", "insight"),
    ),
    check_fn=check_cognitive_tool_requirements,
    description="记录 InsightDelta 到 HERMES_HOME/cognitive/insights.jsonl",
    emoji="💡",
)

registry.register(
    name="cognitive_state_query",
    toolset="cognitive_governance",
    schema=COGNITIVE_STATE_QUERY_SCHEMA,
    handler=lambda args, **kw: cognitive_state_query(
        last_n=args.get("last_n", 5),
    ),
    check_fn=check_cognitive_tool_requirements,
    description="读取最近 N 条 CognitiveState 快照",
    emoji="🔍",
)

registry.register(
    name="insight_delta_query",
    toolset="cognitive_governance",
    schema=INSIGHT_DELTA_QUERY_SCHEMA,
    handler=lambda args, **kw: insight_delta_query(
        last_n=args.get("last_n", 10),
        delta_type=args.get("delta_type", ""),
    ),
    check_fn=check_cognitive_tool_requirements,
    description="读取最近 N 条 InsightDelta 记录，可按类型过滤",
    emoji="🔍",
)
