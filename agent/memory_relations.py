"""MemoryRelations — 最小强关系记录。

只做强关系：提醒冲突、覆盖、权限风险和旧新关系。
关系只提醒，不直接决定权限或事实。

写入路径：{HERMES_HOME}/memory_relations/relations.jsonl
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

# 10 类强关系
RELATION_TYPES = {
    "person",           # 关联人物
    "project",          # 关联项目
    "product_line",     # 关联产品线
    "session",          # 关联会话
    "document",         # 关联文档
    "time",             # 时间关系
    "version_supersedes",  # 新版本覆盖旧版本
    "user_correction",  # 用户纠正了之前的内容
    "tool_failure",     # 工具写入失败产生的替代记录
    "experience_source",   # 经验卡的来源 case
}


@dataclass
class MemoryRelation:
    id: str
    relation_type: str  # RELATION_TYPES 之一
    source_id: str      # MemoryEvent.id 或其他实体 id
    target_id: str      # 关联目标 id
    note: str           # 提醒文字（冲突/覆盖/权限风险/新旧关系）
    created_at: str


def write_relation(
    relation_type: str,
    source_id: str,
    target_id: str,
    note: str = "",
    hermes_home: Path | None = None,
) -> str:
    """写入 MemoryRelation，返回 relation.id，never raises。"""
    relation_id = str(uuid.uuid4())
    try:
        base = hermes_home or get_hermes_home()
        path = base / "memory_relations" / "relations.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        rel = MemoryRelation(
            id=relation_id,
            relation_type=relation_type,
            source_id=source_id,
            target_id=target_id,
            note=note,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(rel), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("write_relation failed (non-fatal): %s", exc)
    return relation_id


def query_relations(
    source_id: str,
    hermes_home: Path | None = None,
) -> list[dict]:
    """线性扫描返回 source_id 相关的全部关系记录。"""
    base = hermes_home or get_hermes_home()
    path = base / "memory_relations" / "relations.jsonl"
    if not path.exists():
        return []
    results = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("source_id") == source_id or rec.get("target_id") == source_id:
                results.append(rec)
    except Exception as exc:
        logger.warning("query_relations failed: %s", exc)
    return results


def list_relations(hermes_home: Path | None = None) -> list[dict]:
    """读取全部关系记录。"""
    base = hermes_home or get_hermes_home()
    path = base / "memory_relations" / "relations.jsonl"
    if not path.exists():
        return []
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    except Exception as exc:
        logger.warning("list_relations failed: %s", exc)
    return records
