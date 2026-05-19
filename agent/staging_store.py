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

logger = logging.getLogger(__name__)

NEXT_ACTIONS = {
    "wait_for_source",
    "needs_user_confirmation",
    "needs_project_mapping",
    "retry_write",
    "archive_as_reference",
}

VISIBILITY_SCOPES = {"private", "team", "project", "company"}
RETRIEVAL_SCOPES = {"owner_only", "project_members", "all"}


@dataclass
class StagingEntry:
    staging_id: str
    event_id: str
    reason: str
    visibility_scope: str
    retrieval_scope: str
    next_action: str
    created_at: str
    source_uri: str
    raw_content: str


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
    """将 StagingEntry 追加写入 JSONL，返回 staging_id，never raises。"""
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
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("write_staging failed (non-fatal): %s", exc)
    return staging_id


def list_staging(hermes_home: Path | None = None) -> list[dict]:
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
    for rec in list_staging(hermes_home=hermes_home):
        if rec.get("staging_id") == staging_id:
            return rec
    return None


# ── ops: state transitions ─────────────────────────────────────────────────────

_OPS_STATES = NEXT_ACTIONS | {"approved", "rejected"}


def _rewrite_staging(records: list[dict], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _write_audit(staging_id: str, action: str, detail: str, base: Path) -> None:
    import time
    audit_path = base / "staging" / "staging_audit.jsonl"
    entry = {
        "staging_id": staging_id,
        "action": action,
        "detail": detail,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("staging audit write failed (non-fatal): %s", exc)


def _update_staging_field(
    staging_id: str,
    updates: dict,
    hermes_home: Path | None,
    audit_action: str,
    audit_detail: str = "",
) -> bool:
    base = hermes_home or get_hermes_home()
    path = base / "staging" / "staging.jsonl"
    if not path.exists():
        return False
    try:
        records = []
        found = False
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # Remove usage_hint sentinel added by list_staging()
            rec.pop("usage_hint", None)
            if rec.get("staging_id") == staging_id:
                rec.update(updates)
                found = True
            records.append(rec)
        if not found:
            return False
        _rewrite_staging(records, path)
        _write_audit(staging_id, audit_action, audit_detail, base)
        return True
    except Exception as exc:
        logger.warning("_update_staging_field failed (non-fatal): %s", exc)
        return False


def approve(staging_id: str, hermes_home: Path | None = None) -> bool:
    """Mark a staging entry as approved; idempotent."""
    return _update_staging_field(
        staging_id,
        {"next_action": "approved"},
        hermes_home,
        audit_action="approve",
    )


def reject(staging_id: str, reason: str = "", hermes_home: Path | None = None) -> bool:
    """Mark a staging entry as rejected, storing the reason."""
    return _update_staging_field(
        staging_id,
        {"next_action": "rejected", "rejection_reason": reason},
        hermes_home,
        audit_action="reject",
        audit_detail=reason,
    )


def archive(staging_id: str, hermes_home: Path | None = None) -> bool:
    """Transition a staging entry to archive_as_reference."""
    return _update_staging_field(
        staging_id,
        {"next_action": "archive_as_reference"},
        hermes_home,
        audit_action="archive",
    )


def update_next_action(
    staging_id: str,
    next_action: str,
    hermes_home: Path | None = None,
) -> bool:
    """Update next_action to any valid state; rejects unknown states."""
    if next_action not in _OPS_STATES:
        logger.warning("update_next_action: invalid state %r", next_action)
        return False
    return _update_staging_field(
        staging_id,
        {"next_action": next_action},
        hermes_home,
        audit_action="update_next_action",
        audit_detail=next_action,
    )


def stats(hermes_home: Path | None = None) -> dict:
    """Return count statistics by next_action."""
    records = list_staging(hermes_home=hermes_home)
    by_action: dict[str, int] = {}
    for rec in records:
        action = rec.get("next_action", "unknown")
        by_action[action] = by_action.get(action, 0) + 1
    return {"total": len(records), "by_next_action": by_action}
