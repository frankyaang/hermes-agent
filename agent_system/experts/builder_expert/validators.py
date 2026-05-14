"""
DRAFT validators — Stage 5 (VALIDATE) checks per EXPERT.md §5.

Each validator returns (ok, errors). `errors` is a list of human-readable
strings used both for retry triage and for the form-fallback prompt shown
to the user when auto-recovery fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ---------- helpers ----------


def _agent_system_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- (1) JSON schema check ----------

# Required fields per artifact type. Type checks are deliberately loose —
# we only catch obvious template breakage, not enforce a full spec.
_REQUIRED_FIELDS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "skill": {
        "name": str,
        "display_name": str,
        "description": str,
        "type": str,
        "pipeline": str,
        "private_memory": bool,
        "root": str,
    },
    "expert": {
        "name": str,
        "display_name": str,
        "description": str,
        "skills": list,
        "private_memory": bool,
        "root": str,
    },
    "pipeline": {
        "name": str,
        "version": int,
        "steps": list,
    },
    "route_entry": {
        "pipeline_id": str,
        "pipeline_name": str,
        "step": (int, str),
        "node": str,
        "constraints": dict,
        "supervision": dict,
    },
}


def _check_required(label: str, kind: str, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    spec = _REQUIRED_FIELDS[kind]
    for field, expected_type in spec.items():
        if field not in data:
            errors.append(f"[{label}] 缺少必填字段 `{field}`")
            continue
        if not isinstance(data[field], expected_type):
            errors.append(
                f"[{label}] 字段 `{field}` 类型不对：期望 {expected_type}，实际 {type(data[field]).__name__}"
            )
    return errors


def validate_json_schema(drafts: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []

    # Skill files
    for p_str in drafts.get("skill_paths", []):
        p = Path(p_str)
        if p.name == "skill.json":
            try:
                errors += _check_required(p_str, "skill", _load_json(p))
            except Exception as e:
                errors.append(f"[{p_str}] JSON 解析失败: {e}")
        elif p.suffix == ".json" and "pipeline" in p.parts:
            try:
                errors += _check_required(p_str, "pipeline", _load_json(p))
            except Exception as e:
                errors.append(f"[{p_str}] JSON 解析失败: {e}")

    # Expert files
    for p_str in drafts.get("expert_paths", []):
        p = Path(p_str)
        if p.name == "expert.json":
            try:
                errors += _check_required(p_str, "expert", _load_json(p))
            except Exception as e:
                errors.append(f"[{p_str}] JSON 解析失败: {e}")

    # Routes draft
    routes_path = drafts.get("routes_draft_path")
    if routes_path:
        try:
            data = _load_json(Path(routes_path))
            for entry in data.get("pipelines", []):
                errors += _check_required(
                    f"{routes_path}#{entry.get('pipeline_id', '?')}",
                    "route_entry",
                    entry,
                )
        except Exception as e:
            errors.append(f"[{routes_path}] JSON 解析失败: {e}")

    return (len(errors) == 0, errors)


# ---------- (2) Name collision check ----------


def validate_name_collision(drafts: dict[str, Any]) -> tuple[bool, list[str]]:
    """Skill/expert draft names must not clash with already-deployed names."""
    errors: list[str] = []
    root = _agent_system_root()

    skill_name = drafts.get("skill_name")
    if skill_name:
        prod_path = root / "skills" / skill_name
        if prod_path.exists():
            errors.append(
                f"重名：`skills/{skill_name}` 已存在（位于 {prod_path}），"
                f"draft 落正式位置时会冲突"
            )

    expert_name = drafts.get("expert_name")
    expert_action = drafts.get("expert_action")
    if expert_action == "create" and expert_name:
        prod_path = root / "experts" / expert_name
        if prod_path.exists():
            errors.append(
                f"重名：`experts/{expert_name}` 已存在（位于 {prod_path}），"
                f"draft 落正式位置时会冲突"
            )

    return (len(errors) == 0, errors)


# ---------- (3) Dependency completeness ----------


def _resolve_expert(name: str, root: Path, session_draft_root: Path | None = None) -> bool:
    """Expert resolves to either a deployed or a session-draft directory."""
    if (root / "experts" / name).exists():
        return True
    if session_draft_root and (session_draft_root / "experts" / "_drafts" / name).exists():
        return True
    return False


def _resolve_skill(name: str, root: Path, session_draft_root: Path | None = None) -> bool:
    if (root / "skills" / name).exists():
        return True
    if session_draft_root and (session_draft_root / "skills" / "_drafts" / name).exists():
        return True
    return False


def validate_dependencies(drafts: dict[str, Any]) -> tuple[bool, list[str]]:
    """Routes must reference experts/skills that resolve to a draft or prod path."""
    errors: list[str] = []
    root = _agent_system_root()

    session_draft_root_str = drafts.get("session_draft_root")
    session_draft_root = Path(session_draft_root_str) if session_draft_root_str else None

    routes_path = drafts.get("routes_draft_path")
    if not routes_path or not Path(routes_path).exists():
        return (False, [f"依赖检查跳过：routes.draft.json 缺失（{routes_path}）"])

    try:
        data = _load_json(Path(routes_path))
    except Exception as e:
        return (False, [f"routes.draft.json 解析失败: {e}"])

    for entry in data.get("pipelines", []):
        node = entry.get("node")
        pid = entry.get("pipeline_id", "?")
        if node and not _resolve_skill(node, root, session_draft_root):
            errors.append(f"路由 `{pid}` 的 node `{node}` 找不到对应 skill 目录")
        primary = entry.get("supervision", {}).get("primary_expert")
        if primary and not _resolve_expert(primary, root, session_draft_root):
            errors.append(
                f"路由 `{pid}` 的 primary_expert `{primary}` 找不到对应 expert 目录"
            )
        for sec in entry.get("supervision", {}).get("secondary_experts", []) or []:
            if not _resolve_expert(sec, root, session_draft_root):
                errors.append(
                    f"路由 `{pid}` 的 secondary_expert `{sec}` 找不到对应 expert 目录"
                )

    return (len(errors) == 0, errors)


# ---------- aggregate ----------


def run_all(drafts: dict[str, Any]) -> dict[str, Any]:
    """Run every validator, return structured report.

    Report shape:
        {
          "ok": bool,
          "checks": [
            {"name": "json_schema", "ok": bool, "errors": [..]},
            ...
          ],
          "all_errors": [..],   # flat list for prompt rendering
          "failed_check_names": ["json_schema", ...]
        }
    """
    checks: list[dict[str, Any]] = []
    failed_names: list[str] = []
    all_errors: list[str] = []

    for name, fn in [
        ("json_schema", validate_json_schema),
        ("name_collision", validate_name_collision),
        ("dependencies", validate_dependencies),
    ]:
        ok, errors = fn(drafts)
        checks.append({"name": name, "ok": ok, "errors": errors})
        if not ok:
            failed_names.append(name)
            all_errors.extend(errors)

    return {
        "ok": not failed_names,
        "checks": checks,
        "all_errors": all_errors,
        "failed_check_names": failed_names,
    }
