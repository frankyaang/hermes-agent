"""Deterministic in-process executors for low-risk agent-system skills.

These executors are used only when readiness_manifest.json declares a skill as
``executor_type=system``. They avoid delegate recursion and external side
effects for artifact lookup/status/delivery/doc-publish fallback flows.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_system.skills.artifact_resolver.resolver import resolve_artifact


_SYSTEM_SKILLS = {
    "artifact_resolver",
    "artifact_status",
    "artifact_delivery",
    "doc_publish",
}

_TEXT_EXTS = {".csv", ".html", ".json", ".md", ".txt"}
_PREVIEW_LIMIT = 20000


def can_execute_system_skill(skill_id: str) -> bool:
    return skill_id in _SYSTEM_SKILLS


def execute_system_skill(
    *,
    skill_id: str,
    context: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    """Execute a manifest-approved system skill without calling an LLM."""
    if skill_id not in _SYSTEM_SKILLS:
        return _blocked(skill_id, f"unsupported system skill: {skill_id}")

    resolved = _resolve_from_context(context, project_root)
    if skill_id == "artifact_resolver":
        if resolved.get("status") != "completed":
            return _blocked(skill_id, str(resolved.get("reason") or "artifact not resolved"))
        return _completed(
            skill_id,
            {
                "result_summary": f"产物定位完成：{resolved['path']} — {resolved['summary']}",
                "artifact_path": resolved["path"],
                "main_report_path": resolved["path"],
                "artifact_source": resolved.get("source", ""),
                "candidates": resolved.get("candidates", []),
            },
        )

    if resolved.get("status") != "completed":
        return _blocked(skill_id, str(resolved.get("reason") or "artifact not resolved"))

    path = Path(str(resolved["path"]))
    if skill_id == "artifact_status":
        return _artifact_status(path, resolved)
    if skill_id == "artifact_delivery":
        return _artifact_delivery(path, resolved)
    return _doc_publish(path, resolved)


def _resolve_from_context(context: dict[str, Any], project_root: Path) -> dict[str, Any]:
    package = context.get("task_package") or {}
    payload = context.get("input_payload") or {}
    prior_results = context.get("prior_results") or {}
    source_materials = payload.get("source_materials") or []
    message_parts = [str(v) for v in source_materials if v is not None]
    node_id = package.get("node_id")
    if node_id:
        message_parts.append(str(node_id))
    return resolve_artifact(
        message="\n".join(message_parts),
        prior_results=prior_results,
        project_root=project_root,
    )


def _artifact_status(path: Path, resolved: dict[str, Any]) -> dict[str, Any]:
    meta = _file_meta(path)
    summary = (
        f"产物状态正常：{path}；大小 {meta['size_bytes']} bytes；"
        f"修改时间 {meta['modified_at']}。"
    )
    return _completed(
        "artifact_status",
        {
            "result_summary": summary,
            "artifact_path": str(path),
            "main_report_path": str(path),
            "artifact_source": resolved.get("source", ""),
            "artifact_status": "available",
            "file_meta": meta,
        },
    )


def _artifact_delivery(path: Path, resolved: dict[str, Any]) -> dict[str, Any]:
    preview = _read_text_preview(path)
    summary = f"产物交付完成：{path}"
    output = {
        "result_summary": summary,
        "artifact_path": str(path),
        "main_report_path": str(path),
        "artifact_source": resolved.get("source", ""),
        "delivery_mode": "inline_preview" if preview["text_available"] else "path_only",
        "file_meta": _file_meta(path),
    }
    output.update(preview)
    return _completed("artifact_delivery", output)


def _doc_publish(path: Path, resolved: dict[str, Any]) -> dict[str, Any]:
    preview = _read_text_preview(path)
    publish_mode = "local_fallback_package"
    summary = (
        f"文档发布包已准备：{path}。当前执行器不直接调用飞书 API；"
        "可使用返回的本地路径和正文预览继续发布。"
    )
    output = {
        "result_summary": summary,
        "artifact_path": str(path),
        "main_report_path": str(path),
        "artifact_source": resolved.get("source", ""),
        "publish_mode": publish_mode,
        "requires_external_publish": True,
        "file_meta": _file_meta(path),
    }
    output.update(preview)
    return _completed("doc_publish", output)


def _file_meta(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "suffix": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _read_text_preview(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in _TEXT_EXTS:
        return {
            "text_available": False,
            "content_preview": "",
            "content_truncated": False,
        }
    raw = path.read_text(encoding="utf-8", errors="replace")
    return {
        "text_available": True,
        "content_preview": raw[:_PREVIEW_LIMIT],
        "content_truncated": len(raw) > _PREVIEW_LIMIT,
    }


def _completed(skill_id: str, output: dict[str, Any]) -> dict[str, Any]:
    output = dict(output)
    output.update(
        {
            "skill_id": skill_id,
            "real_skill_execution": True,
            "system_executor": True,
        }
    )
    return {
        "status": "completed",
        "output_quality": 95,
        "execution_mode": "system_skill_executor",
        "output": output,
        "audit_checks": {
            "system_skill_executor": True,
            "real_skill_execution": True,
        },
        "exceptions": [],
    }


def _blocked(skill_id: str, reason: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "output_quality": 0,
        "execution_mode": "system_skill_executor_blocked",
        "output": {
            "result_summary": f"{skill_id} 需要补充输入：{reason}",
            "skill_id": skill_id,
            "real_skill_execution": True,
            "system_executor": True,
        },
        "audit_checks": {
            "system_skill_executor": True,
            "real_skill_execution": True,
            "needs_input": True,
        },
        "exceptions": [
            {
                "event": "artifact_input_missing",
                "trigger": reason,
                "handling": "提示用户补充产物路径、标题、任务ID或可解析引用",
                "blocking": True,
                "audit_field": "artifact_reference",
                "review_trigger": False,
            }
        ],
        "missing_inputs": ["artifact_reference"],
    }


def dumps_sanitized(result: dict[str, Any]) -> str:
    """Small helper for tests and debug output."""
    return json.dumps(result, ensure_ascii=False, default=str)
