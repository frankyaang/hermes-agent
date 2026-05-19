"""MemoryEvent — 所有候选沉淀内容的事件化入口。

所有信息（会话、文档、工具结果、用户纠正、写入失败）在进入任何存储目标前
先转化为 MemoryEvent，由分流器决定最终去向。

写入路径：{HERMES_HOME}/memory_events/events.jsonl
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

RISK_FLAGS = {
    "private_chat",
    "project_uncertain",
    "permission_unclear",
    "stale_version",
    "user_correction",
    "tool_failure",
    "identity_missing",
}

SOURCE_TYPES = {
    "session",
    "document",
    "tool_result",
    "user_correction",
    "write_failure",
}

DESTINATIONS = {
    "personal_memory",
    "project_process",
    "knowledge",
    "experience_card",
    "staging",
}


@dataclass
class MemoryEvent:
    id: str
    source_type: str
    source_uri: str
    timestamp: str
    actor_user_id: str
    speaker_label: str
    subject: str
    session_id: str
    project_hint: str
    product_line_hint: str
    current_task: str
    risk_flags: List[str]
    recommended_destination: str
    raw_excerpt_ref: str
    created_at: str


def create_event(
    source_type: str,
    source_uri: str,
    actor_user_id: str,
    subject: str,
    risk_flags: List[str],
    recommended_destination: str,
    *,
    speaker_label: str = "user",
    session_id: str = "",
    project_hint: str = "",
    product_line_hint: str = "",
    current_task: str = "",
    raw_excerpt_ref: str = "",
    timestamp: str = "",
) -> MemoryEvent:
    now = datetime.now(timezone.utc).isoformat()
    return MemoryEvent(
        id=str(uuid.uuid4()),
        source_type=source_type,
        source_uri=source_uri,
        timestamp=timestamp or now,
        actor_user_id=actor_user_id,
        speaker_label=speaker_label,
        subject=subject,
        session_id=session_id,
        project_hint=project_hint,
        product_line_hint=product_line_hint,
        current_task=current_task,
        risk_flags=risk_flags,
        recommended_destination=recommended_destination,
        raw_excerpt_ref=raw_excerpt_ref,
        created_at=now,
    )


def write_event(event: MemoryEvent, hermes_home: Path | None = None) -> str:
    """将 MemoryEvent 追加写入 JSONL，返回 event.id，never raises。"""
    try:
        base = hermes_home or get_hermes_home()
        path = base / "memory_events" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("write_event failed (non-fatal): %s", exc)
    return event.id


def list_events(hermes_home: Path | None = None) -> list[dict]:
    base = hermes_home or get_hermes_home()
    path = base / "memory_events" / "events.jsonl"
    if not path.exists():
        return []
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    except Exception as exc:
        logger.warning("list_events failed: %s", exc)
    return records
