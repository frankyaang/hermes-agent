"""MemoryEvent — 所有候选沉淀内容的事件化入口。

所有信息（会话、文档、工具结果、用户纠正、写入失败）在进入任何存储目标前
先转化为 MemoryEvent，由分流器决定最终去向。

写入路径：{HERMES_HOME}/memory_events/events.jsonl
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from hermes_constants import get_hermes_home
from agent.runtime_artifact_evidence import sanitize_summary

logger = logging.getLogger(__name__)

# risk_flags 支持值
RISK_FLAGS = {
    "private_chat",         # 来自私聊，不可直接项目化
    "project_uncertain",    # 项目归属不清
    "permission_unclear",   # 权限范围不清
    "stale_version",        # 可能是旧版本内容
    "user_correction",      # 用户纠正了之前的内容
    "tool_failure",         # 工具写入失败
    "identity_missing",     # 说话者/来源身份不清
}

# source_type 支持值
SOURCE_TYPES = {
    "session",          # 来自对话会话
    "document",         # 来自文档/飞书等
    "tool_result",      # 来自工具调用结果
    "user_correction",  # 来自用户纠正
    "write_failure",    # 来自写入失败的替代路径
}

# recommended_destination 支持值
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
    source_type: str            # SOURCE_TYPES 之一
    source_uri: str
    timestamp: str              # ISO8601 UTC
    actor_user_id: str
    speaker_label: str          # user | assistant | system
    subject: str                # 内容主题一句话
    session_id: str
    project_hint: str           # 可为空
    product_line_hint: str      # 可为空
    current_task: str           # 可为空
    risk_flags: List[str]       # RISK_FLAGS 子集
    recommended_destination: str  # DESTINATIONS 之一
    raw_excerpt_ref: str        # 可为空，指向原始内容片段
    created_at: str
    status: str = "captured"
    producer_runtime_path: str = "agent.memory_event.write_event"
    source_capability: str = "memory_event"
    sanitized_summary: str = ""


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
    status: str = "captured",
    producer_runtime_path: str = "agent.memory_event.write_event",
    source_capability: str = "memory_event",
    sanitized_summary: str = "",
) -> MemoryEvent:
    """创建 MemoryEvent，自动填充 id 和 created_at。"""
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
        status=status,
        producer_runtime_path=producer_runtime_path,
        source_capability=source_capability,
        sanitized_summary=sanitized_summary or sanitize_summary(subject, current_task, source_uri),
    )


def write_event(event: MemoryEvent, hermes_home: Path | None = None) -> str:
    """将 MemoryEvent 追加写入 JSONL 文件，返回 event.id，never raises。"""
    try:
        if not event.sanitized_summary:
            event.sanitized_summary = sanitize_summary(
                event.subject, event.current_task, event.source_uri
            )
        base = hermes_home or get_hermes_home()
        path = base / "memory_events" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("write_event failed (non-fatal): %s", exc)
    return event.id


def list_events(hermes_home: Path | None = None) -> list[dict]:
    """从 JSONL 读取全部 MemoryEvent 记录。"""
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
