from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

_MANIFEST_FILE = "readiness_manifest.json"
_MANIFEST_CACHE: dict[str, dict] = {}


@dataclass
class ReadinessResult:
    id: str
    kind: Literal["route", "skill"]
    state: Literal["ready", "non_ready", "unknown"]
    registered: bool
    executable: bool
    production_ready: bool
    executor_type: str
    allowed_entrypoints: list[str]
    blocking: bool
    reasons: list[str]
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocked(self) -> bool:
        return self.blocking


def load_readiness_manifest(root: Path) -> dict[str, Any]:
    path = Path(root) / "agent_system" / _MANIFEST_FILE
    key = str(path)
    if key not in _MANIFEST_CACHE:
        if path.exists():
            _MANIFEST_CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
        else:
            _MANIFEST_CACHE[key] = {"routes": [], "skills": []}
    return _MANIFEST_CACHE[key]


def _invalidate_manifest_cache(root: Path) -> None:
    key = str(Path(root) / "agent_system" / _MANIFEST_FILE)
    _MANIFEST_CACHE.pop(key, None)


def validate_readiness_manifest(root: Path, routes_payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    manifest = load_readiness_manifest(root)
    manifest_pipeline_ids = {r["pipeline_id"] for r in manifest.get("routes", [])}
    manifest_skill_ids = {s["skill_id"] for s in manifest.get("skills", [])}

    for route in routes_payload.get("pipelines", []):
        pid = str(route.get("pipeline_id") or "")
        if pid and pid not in manifest_pipeline_ids:
            errors.append(f"MANIFEST_MISSING: pipeline {pid!r} not in readiness_manifest.json")

    skills_root = Path(root) / "agent_system" / "skills"
    if skills_root.exists():
        for skill_dir in sorted(skills_root.iterdir()):
            if skill_dir.is_dir() and not skill_dir.name.startswith("_"):
                sid = skill_dir.name
                if sid not in manifest_skill_ids:
                    errors.append(f"MANIFEST_MISSING: skill {sid!r} not in readiness_manifest.json")

    for route_entry in manifest.get("routes", []):
        pid = route_entry.get("pipeline_id", "")
        state = route_entry.get("readiness_state", "unknown")
        if state == "ready":
            if not route_entry.get("allowed_entrypoints"):
                errors.append(f"MANIFEST_INVALID: ready route {pid!r} missing allowed_entrypoints")
            if not route_entry.get("output_contract"):
                errors.append(f"MANIFEST_INVALID: ready route {pid!r} missing output_contract")
            for req_skill in route_entry.get("required_skills", []):
                skill_entry = next(
                    (s for s in manifest.get("skills", []) if s["skill_id"] == req_skill), None
                )
                if skill_entry is None or not skill_entry.get("executable"):
                    errors.append(
                        f"MANIFEST_INVALID: ready route {pid!r} requires skill {req_skill!r} "
                        f"but skill is not executable in manifest"
                    )

    for skill_entry in manifest.get("skills", []):
        sid = skill_entry.get("skill_id", "")
        state = skill_entry.get("readiness_state", "unknown")
        if state == "ready" or skill_entry.get("executable"):
            if not skill_entry.get("output_contract"):
                errors.append(
                    f"MANIFEST_INVALID: executable skill {sid!r} missing output_contract"
                )

    return errors


def check_skill_readiness(
    root: Path,
    skill_id: str,
    entrypoint: str = "gateway",
) -> ReadinessResult:
    manifest = load_readiness_manifest(root)
    skill_entry = next(
        (s for s in manifest.get("skills", []) if s["skill_id"] == skill_id), None
    )

    if skill_entry is None:
        return ReadinessResult(
            id=skill_id,
            kind="skill",
            state="unknown",
            registered=False,
            executable=False,
            production_ready=False,
            executor_type="unknown",
            allowed_entrypoints=[],
            blocking=True,
            reasons=[f"skill {skill_id!r} not found in readiness manifest"],
            evidence={},
        )

    state: Literal["ready", "non_ready", "unknown"] = skill_entry.get("readiness_state", "unknown")
    executable = bool(skill_entry.get("executable", False))
    production_ready = bool(skill_entry.get("production_ready", False))
    executor_type = str(skill_entry.get("executor_type", "unknown"))
    output_contract = str(skill_entry.get("output_contract", ""))
    reasons = []

    if state == "non_ready":
        reasons.append(skill_entry.get("readiness_reason", "skill is non-ready"))
        return ReadinessResult(
            id=skill_id,
            kind="skill",
            state="non_ready",
            registered=True,
            executable=False,
            production_ready=False,
            executor_type=executor_type,
            allowed_entrypoints=[],
            blocking=True,
            reasons=reasons,
            evidence={"manifest_entry": skill_entry},
        )

    if state == "unknown":
        reasons.append(skill_entry.get("readiness_reason", "skill readiness unknown"))
        return ReadinessResult(
            id=skill_id,
            kind="skill",
            state="unknown",
            registered=True,
            executable=False,
            production_ready=False,
            executor_type=executor_type,
            allowed_entrypoints=[],
            blocking=True,
            reasons=reasons,
            evidence={"manifest_entry": skill_entry},
        )

    if not executable:
        reasons.append("skill is not executable per manifest")
    if executable and not output_contract:
        reasons.append("executable skill missing output_contract")
        return ReadinessResult(
            id=skill_id,
            kind="skill",
            state="non_ready",
            registered=True,
            executable=False,
            production_ready=False,
            executor_type=executor_type,
            allowed_entrypoints=[],
            blocking=True,
            reasons=reasons,
            evidence={"manifest_entry": skill_entry},
        )

    blocking = not executable or not production_ready
    return ReadinessResult(
        id=skill_id,
        kind="skill",
        state=state,
        registered=True,
        executable=executable,
        production_ready=production_ready,
        executor_type=executor_type,
        allowed_entrypoints=[],
        blocking=blocking,
        reasons=reasons,
        evidence={"manifest_entry": skill_entry},
    )


def check_pipeline_readiness(
    root: Path,
    routes_payload: dict[str, Any],
    pipeline_id: str,
    entrypoint: str = "gateway",
) -> ReadinessResult:
    manifest = load_readiness_manifest(root)
    route_entry = next(
        (r for r in manifest.get("routes", []) if r["pipeline_id"] == pipeline_id), None
    )

    all_pipeline_ids = {
        str(r.get("pipeline_id") or "")
        for r in routes_payload.get("pipelines", [])
        if r.get("pipeline_id")
    }

    if route_entry is None:
        registered = pipeline_id in all_pipeline_ids
        return ReadinessResult(
            id=pipeline_id,
            kind="route",
            state="unknown",
            registered=registered,
            executable=False,
            production_ready=False,
            executor_type="unknown",
            allowed_entrypoints=[],
            blocking=True,
            reasons=[f"pipeline {pipeline_id!r} not found in readiness manifest"],
            evidence={},
        )

    state: Literal["ready", "non_ready", "unknown"] = route_entry.get("readiness_state", "unknown")
    production_ready = bool(route_entry.get("production_ready", False))
    allowed_entrypoints = list(route_entry.get("allowed_entrypoints") or [])
    reasons = []

    if state == "non_ready":
        reasons.append(route_entry.get("readiness_reason", "pipeline is non-ready"))
        return ReadinessResult(
            id=pipeline_id,
            kind="route",
            state="non_ready",
            registered=True,
            executable=False,
            production_ready=False,
            executor_type="unknown",
            allowed_entrypoints=allowed_entrypoints,
            blocking=True,
            reasons=reasons,
            evidence={"manifest_entry": route_entry},
        )

    if state == "unknown":
        reasons.append(route_entry.get("readiness_reason", "pipeline readiness unknown"))
        return ReadinessResult(
            id=pipeline_id,
            kind="route",
            state="unknown",
            registered=True,
            executable=False,
            production_ready=False,
            executor_type="unknown",
            allowed_entrypoints=allowed_entrypoints,
            blocking=True,
            reasons=reasons,
            evidence={"manifest_entry": route_entry},
        )

    if entrypoint and allowed_entrypoints and entrypoint not in allowed_entrypoints:
        reasons.append(
            f"entrypoint {entrypoint!r} not in allowed_entrypoints {allowed_entrypoints}"
        )
        return ReadinessResult(
            id=pipeline_id,
            kind="route",
            state="non_ready",
            registered=True,
            executable=False,
            production_ready=production_ready,
            executor_type="unknown",
            allowed_entrypoints=allowed_entrypoints,
            blocking=True,
            reasons=reasons,
            evidence={"manifest_entry": route_entry},
        )

    for req_skill in route_entry.get("required_skills", []):
        skill_result = check_skill_readiness(root, req_skill, entrypoint)
        if skill_result.blocking:
            reasons.append(
                f"required skill {req_skill!r} is not ready: {'; '.join(skill_result.reasons)}"
            )
    if reasons:
        return ReadinessResult(
            id=pipeline_id,
            kind="route",
            state="non_ready",
            registered=True,
            executable=False,
            production_ready=production_ready,
            executor_type="unknown",
            allowed_entrypoints=allowed_entrypoints,
            blocking=True,
            reasons=reasons,
            evidence={"manifest_entry": route_entry},
        )

    return ReadinessResult(
        id=pipeline_id,
        kind="route",
        state="ready",
        registered=True,
        executable=True,
        production_ready=production_ready,
        executor_type="system",
        allowed_entrypoints=allowed_entrypoints,
        blocking=False,
        reasons=[],
        evidence={"manifest_entry": route_entry},
    )


def ready_route_candidates(
    root: Path,
    routes_payload: dict[str, Any],
    entrypoint: str = "gateway",
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for route in routes_payload.get("pipelines", []):
        pipeline_id = str(route.get("pipeline_id") or "")
        if not pipeline_id:
            continue
        entry = grouped.setdefault(
            pipeline_id,
            {
                "pipeline_id": pipeline_id,
                "pipeline_name": route.get("pipeline_name") or pipeline_id,
                "nodes": [],
            },
        )
        entry["nodes"].append(
            {
                "node": route.get("node"),
                "display_name": route.get("display_name"),
                "depends_on": route.get("depends_on") or [],
                "final_output": bool(route.get("final_output")),
            }
        )

    ready = []
    for pipeline_id, entry in grouped.items():
        result = check_pipeline_readiness(root, routes_payload, pipeline_id, entrypoint)
        if not result.blocking:
            ready.append(entry)
    return ready


def explain_readiness(result: ReadinessResult) -> str:
    lines = [
        f"[{result.kind}:{result.id}] state={result.state} "
        f"production_ready={result.production_ready} "
        f"executable={result.executable} "
        f"blocking={result.blocking}"
    ]
    if result.reasons:
        for r in result.reasons:
            lines.append(f"  reason: {r}")
    return "\n".join(lines)
