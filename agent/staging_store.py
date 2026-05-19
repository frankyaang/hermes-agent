"""StagingStore — 条件不足时的内容暂存区。

以下情形进入 Staging（不丢失，但不立即写入目标存储）：
- 身份不清（identity_missing）
- 项目归属不清（project_uncertain）
- 权限不清（permission_unclear）
- 私聊但有项目价值（private_chat + project_hint 非空）
- 写入失败但内容有价值（tool_failure）
- 旧版/新版关系不清（stale_version）
- 用户纠正但影响范围不清（user_correction）

写入路径：{HERMES_HOME}/staging/staging.jsonl
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from hermes_constants import get_hermes_home
from agent.runtime_artifact_evidence import sanitize_summary

logger = logging.getLogger(__name__)

# next_action 枚举
NEXT_ACTIONS = {
    "wait_for_source",          # 等待来源确认
    "needs_user_confirmation",  # 需要用户确认归属/范围
    "needs_project_mapping",    # 需要映射到具体项目
    "retry_write",              # 条件满足后重试写入
    "archive_as_reference",     # 归档为参考，不主动使用
}

# visibility_scope 枚举
VISIBILITY_SCOPES = {"private", "team", "project", "company"}

# retrieval_scope 枚举
RETRIEVAL_SCOPES = {"owner_only", "project_members", "all"}


@dataclass
class StagingEntry:
    staging_id: str
    event_id: str          # 关联 MemoryEvent.id
    reason: str            # 进入 staging 的原因
    visibility_scope: str  # VISIBILITY_SCOPES 之一
    retrieval_scope: str   # RETRIEVAL_SCOPES 之一
    next_action: str       # NEXT_ACTIONS 之一
    created_at: str
    source_uri: str
    raw_content: str       # 暂存原文内容
    status: str = "staged"
    producer_runtime_path: str = "agent.staging_store.write_staging"
    source_capability: str = "staging_store"
    sanitized_summary: str = ""


def write_staging(
    event_id: str,
    reason: str,
    next_action: str,
    source_uri: str,
    raw_content: str = "",
    visibility_scope: str = "private",
    retrieval_scope: str = "owner_only",
    hermes_home: Path | None = None,
) -> str:
    """将 StagingEntry 追加写入 JSONL 文件，返回 staging_id，never raises。"""
    staging_id = str(uuid.uuid4())
    try:
        base = hermes_home or get_hermes_home()
        path = base / "staging" / "staging.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = StagingEntry(
            staging_id=staging_id,
            event_id=event_id,
            reason=reason,
            visibility_scope=visibility_scope,
            retrieval_scope=retrieval_scope,
            next_action=next_action,
            created_at=datetime.now(timezone.utc).isoformat(),
            source_uri=source_uri,
            raw_content=raw_content,
            sanitized_summary=sanitize_summary(reason, source_uri, raw_content),
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("write_staging failed (non-fatal): %s", exc)
    return staging_id


def list_staging(hermes_home: Path | None = None) -> list[dict]:
    """读取全部 staging 记录。"""
    base = hermes_home or get_hermes_home()
    path = base / "staging" / "staging.jsonl"
    if not path.exists():
        return []
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rec = json.loads(line)
                rec["usage_hint"] = "needs_source_check"
                records.append(rec)
    except Exception as exc:
        logger.warning("list_staging failed: %s", exc)
    return records


def read_staging(staging_id: str, hermes_home: Path | None = None) -> dict | None:
    """按 staging_id 查找单条记录。"""
    for rec in list_staging(hermes_home=hermes_home):
        if rec.get("staging_id") == staging_id:
            return rec
    return None
