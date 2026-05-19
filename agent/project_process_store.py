"""project_process_store — 项目过程内容持久化存储。

存储路径：{HERMES_HOME}/project_process/records.jsonl

只负责写入和查询，不做权限判断（权限由 dispatcher 在路由前保证）。
never raises — 所有失败均静默记录。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


def write_record(
    event_id: str,
    subject: str,
    project_hint: str = "",
    source_uri: str = "",
    actor_user_id: str = "",
    hermes_home: Path | None = None,
) -> str:
    """将 project_process 记录追加写入 JSONL，返回 record_id，never raises。"""
    record_id = str(uuid.uuid4())
    try:
        base = hermes_home or get_hermes_home()
        path = base / "project_process" / "records.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "record_id": record_id,
            "event_id": event_id,
            "subject": subject,
            "project_hint": project_hint,
            "source_uri": source_uri,
            "actor_user_id": actor_user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("write_record failed (non-fatal): %s", exc)
    return record_id


def list_records(hermes_home: Path | None = None) -> list[dict]:
    """从 JSONL 读取全部 project_process 记录。"""
    base = hermes_home or get_hermes_home()
    path = base / "project_process" / "records.jsonl"
    if not path.exists():
        return []
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    except Exception as exc:
        logger.warning("list_records failed: %s", exc)
    return records
