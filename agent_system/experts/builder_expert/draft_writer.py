"""
DRAFT stage file generator — Task #8 second slice (MVP).

Reads the (intake, architect_proposal) pair from the builder state and
materialises files under a per-session directory:
  agent_system/temp/builder_sessions/<state_identity>/

Each concurrent 深度养马 session gets its own isolated draft tree; files
are only moved to the shared production directories at COMMIT time.

Templates are deliberately minimal — they mirror the shape of existing
references (`skills/briefing/`, `experts/ops_expert/`). LLM-driven content
fill (skills拆分推断、route step串联) is the follow-up half of Task #8.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _agent_system_root() -> Path:
    """builder_expert lives at agent_system/experts/builder_expert/, go up 2."""
    return Path(__file__).resolve().parent.parent.parent


def _session_draft_root(state_identity: str) -> Path:
    """agent_system/temp/builder_sessions/<state_identity>/"""
    return _agent_system_root() / "temp" / "builder_sessions" / (state_identity or "default")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_skill_files(skill_dir: Path, skill_name: str, pipeline_id: str, intake: dict[str, Any]) -> list[Path]:
    """Generate skill.json + SKILL.md + pipeline json + skill_mem/.gitkeep."""
    written: list[Path] = []
    description = intake.get("business_goal", "(待补充)")

    skill_json = {
        "name": skill_name,
        "display_name": skill_name,
        "description": description,
        "type": "draft",
        "pipeline": pipeline_id,
        "private_memory": True,
        "root": f"skills/_drafts/{skill_name}",
    }
    p = skill_dir / "skill.json"
    _write_json(p, skill_json)
    written.append(p)

    skill_md = (
        f"# {skill_name}\n\n"
        f"- English name: `{skill_name}`\n"
        f"- Type: `draft`\n"
        f"- Default pipeline: `{pipeline_id}`\n"
        f"- Private memory: `true`\n\n"
        f"{description}\n\n"
        f"## Pipeline\n\n"
        f"默认执行入口记录在 `pipeline/{pipeline_id}.json`。\n\n"
        f"## INTAKE 原始记录\n\n"
        f"- 业务目标：{intake.get('business_goal', '')}\n"
        f"- 触发场景：{intake.get('scenario', '')}（归类：{intake.get('_scenario_kind') or '未归类'}）\n"
        f"- 输入类型：{intake.get('input_type', '')}\n"
        f"- 输出类型：{intake.get('output_type', '')}\n"
        f"- 执行流程：{intake.get('pipeline_description', '')}\n\n"
        f"## Memory\n\n私域经验记录在 `skill_mem/`。\n"
    )
    p = skill_dir / "SKILL.md"
    _write_text(p, skill_md)
    written.append(p)

    pipeline_json = {
        "name": pipeline_id,
        "version": 1,
        "steps": [],
        "status": "draft_pending_llm_synthesis",
    }
    p = skill_dir / "pipeline" / f"{pipeline_id}.json"
    _write_json(p, pipeline_json)
    written.append(p)

    p = skill_dir / "skill_mem" / ".gitkeep"
    _write_text(p, "")
    written.append(p)

    return written


def _build_expert_files(expert_dir: Path, expert_name: str, skill_name: str, intake: dict[str, Any]) -> list[Path]:
    """Generate expert.json + EXPERT.md + expert_mem/.gitkeep (only for action=create)."""
    written: list[Path] = []
    description = intake.get("business_goal", "(待补充)")

    expert_json = {
        "name": expert_name,
        "display_name": expert_name,
        "description": description,
        "skills": [skill_name],
        "private_memory": True,
        "root": f"experts/_drafts/{expert_name}",
    }
    p = expert_dir / "expert.json"
    _write_json(p, expert_json)
    written.append(p)

    expert_md = (
        f"# {expert_name}\n\n"
        f"- English name: `{expert_name}`\n"
        f"- Type: draft expert\n"
        f"- Private memory: `true`\n\n"
        f"{description}\n\n"
        f"## Skills\n\n- `{skill_name}`\n\n"
        f"## Memory\n\n私域经验记录在 `expert_mem/`。\n"
    )
    p = expert_dir / "EXPERT.md"
    _write_text(p, expert_md)
    written.append(p)

    p = expert_dir / "expert_mem" / ".gitkeep"
    _write_text(p, "")
    written.append(p)

    return written


def _build_routes_patch(
    routes_path: Path,
    pipeline_id: str,
    skill_name: str,
    expert_name: str,
    expert_action: str,
    intake: dict[str, Any],
) -> Path:
    """Write/merge a draft route entry into routes.draft.json (separate from prod routes.json)."""
    if routes_path.exists():
        try:
            existing = json.loads(routes_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {"scheduler": "main_scheduler", "version": 1, "pipelines": []}
    else:
        existing = {"scheduler": "main_scheduler", "version": 1, "pipelines": []}

    new_entry = {
        "pipeline_id": pipeline_id,
        "pipeline_name": skill_name,
        "priority": intake.get("priority", "normal"),
        "step": 1,
        "node": skill_name,
        "display_name": skill_name,
        "constraints": {
            "input_type": intake.get("input_type", ""),
            "output_type": intake.get("output_type", ""),
            "max_runtime": intake.get("max_runtime", 300),
        },
        "supervision": {
            "scheduler_monitor": True,
            "expert_required": True,
            "primary_expert": expert_name,
            "secondary_experts": [],
        },
        "user_gate": bool(intake.get("user_gate", False)),
        "_draft_meta": {
            "expert_action": expert_action,
            "scenario_kind": intake.get("_scenario_kind"),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    existing.setdefault("pipelines", []).append(new_entry)
    _write_json(routes_path, existing)
    return routes_path


def write_drafts(state: dict[str, Any]) -> dict[str, Any]:
    """Generate all draft artifacts into a per-session isolated directory.

    All files land under:
      agent_system/temp/builder_sessions/<state_identity>/

    Returns a summary including `session_draft_root` so that handle_commit
    and validators can locate the files without guessing shared paths.
    Caller (handle_draft) is responsible for updating state['drafts'] with the result.
    """
    intake = state.get("intake", {}) or {}
    proposal = state.get("architect_proposal") or {}

    experts = proposal.get("experts") or []
    skills = proposal.get("skills") or []
    routes = proposal.get("routes") or []

    if not experts or not skills or not routes:
        raise ValueError(
            "architect_proposal incomplete: need experts/skills/routes; "
            f"got experts={len(experts)} skills={len(skills)} routes={len(routes)}"
        )

    expert_action = experts[0].get("action") or "create"
    expert_name = experts[0].get("name") or "unknown_expert"
    skill_name = skills[0].get("name") or "unknown_skill"
    pipeline_id = routes[0].get("pipeline_id") or f"{skill_name}_pipeline"

    state_identity = state.get("state_identity") or "default"
    session_root = _session_draft_root(state_identity)

    # 1. Skill draft (always written)
    skill_dir = session_root / "skills" / "_drafts" / skill_name
    skill_paths = _build_skill_files(skill_dir, skill_name, pipeline_id, intake)

    # 2. Expert draft (only when newly created)
    expert_paths: list[Path] = []
    if expert_action == "create":
        expert_dir = session_root / "experts" / "_drafts" / expert_name
        expert_paths = _build_expert_files(expert_dir, expert_name, skill_name, intake)

    # 3. Routes draft patch (session-level, never touches shared routes.draft.json)
    routes_draft_path = session_root / "scheduler" / "main_scheduler" / "routes.draft.json"
    routes_path = _build_routes_patch(
        routes_draft_path, pipeline_id, skill_name, expert_name, expert_action, intake
    )

    return {
        "session_draft_root": str(session_root),
        "skill_paths": [str(p) for p in skill_paths],
        "expert_paths": [str(p) for p in expert_paths],
        "routes_draft_path": str(routes_path),
        "skill_name": skill_name,
        "expert_name": expert_name,
        "pipeline_id": pipeline_id,
        "expert_action": expert_action,
    }
