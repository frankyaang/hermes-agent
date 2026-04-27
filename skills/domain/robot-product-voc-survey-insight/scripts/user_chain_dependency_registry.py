#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


USER_CHAIN_DEPENDENCY_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "references" / "user_chain_dependency_registry.json"
)
VALID_USER_CHAIN_STAGES = {"user_exposure", "user_reasoning", "user_closure"}
USER_CHAIN_SCOPE_ALIAS = {"user_chain": "user_exposure"}


class UserChainDependencyRegistryError(ValueError):
    pass


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = normalize_text(value)
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return ordered


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_user_refresh_scope(scope: Any) -> str:
    text = normalize_text(scope) or "user_chain"
    return USER_CHAIN_SCOPE_ALIAS.get(text, text)


def coerce_registry_targets(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [normalize_text(item) for item in value if normalize_text(item)]
    text = normalize_text(value)
    return [text] if text else []


def validate_user_chain_dependency_registry(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    steps = ensure_list(payload.get("steps"))
    scope_base_steps = dict(payload.get("scope_base_steps") or {})
    builder_aliases = dict(payload.get("builder_aliases") or {})
    loopback_targets = dict(payload.get("loopback_targets") or {})

    step_ids: list[str] = []
    builder_ids: list[str] = []
    produced_artifact_owners: dict[str, str] = {}
    step_by_id: dict[str, dict[str, Any]] = {}
    downstream_refs: list[tuple[str, str]] = []

    for raw_step in steps:
        if not isinstance(raw_step, dict):
            errors.append("steps 中存在非对象条目。")
            continue
        step_id = normalize_text(raw_step.get("step_id"))
        builder_id = normalize_text(raw_step.get("builder_id"))
        stage = normalize_text(raw_step.get("stage"))
        produced_artifacts = [normalize_text(item) for item in ensure_list(raw_step.get("produced_artifacts")) if normalize_text(item)]
        downstream_steps = [normalize_text(item) for item in ensure_list(raw_step.get("downstream_steps")) if normalize_text(item)]

        if not step_id:
            errors.append("存在缺少 step_id 的 step。")
            continue
        if not builder_id:
            errors.append(f"step `{step_id}` 缺少 builder_id。")
        if stage not in VALID_USER_CHAIN_STAGES:
            errors.append(f"step `{step_id}` 的 stage `{stage}` 非法。")
        if not produced_artifacts:
            errors.append(f"step `{step_id}` 缺少 produced_artifacts。")

        if step_id in step_by_id:
            errors.append(f"step_id `{step_id}` 重复。")
        else:
            step_by_id[step_id] = raw_step
            step_ids.append(step_id)

        if builder_id:
            builder_ids.append(builder_id)

        for artifact in produced_artifacts:
            owner = produced_artifact_owners.get(artifact)
            if owner and owner != step_id:
                errors.append(f"artifact `{artifact}` 被多个 step 产出：`{owner}` 与 `{step_id}`。")
            else:
                produced_artifact_owners[artifact] = step_id
        for downstream in downstream_steps:
            downstream_refs.append((step_id, downstream))

    if len(builder_ids) != len(set(builder_ids)):
        errors.append("builder_id 存在重复。")

    for scope, step_id in scope_base_steps.items():
        normalized_scope = normalize_user_refresh_scope(scope)
        if normalized_scope not in VALID_USER_CHAIN_STAGES:
            errors.append(f"scope_base_steps 中 scope `{scope}` 非法。")
        if step_id not in step_by_id:
            errors.append(f"scope_base_steps 中 `{scope}` 指向不存在的 step `{step_id}`。")

    for step_id, downstream in downstream_refs:
        if downstream not in step_by_id:
            errors.append(f"step `{step_id}` 的 downstream_step `{downstream}` 不存在。")

    for alias, target in builder_aliases.items():
        alias_text = normalize_text(alias)
        target_text = normalize_text(target)
        if not alias_text or not target_text:
            errors.append("builder_aliases 中存在空键或空值。")
            continue
        if target_text not in set(builder_ids):
            errors.append(f"builder_alias `{alias_text}` 指向不存在的 builder `{target_text}`。")

    builder_set = set(builder_ids)
    artifact_set = set(produced_artifact_owners.keys())
    loopback_target_names = set(loopback_targets.keys())
    for target_name, target_payload in loopback_targets.items():
        if not isinstance(target_payload, dict):
            errors.append(f"loopback_target `{target_name}` 不是对象。")
            continue
        mapped_scope = normalize_text(target_payload.get("mapped_refresh_scope"))
        if mapped_scope and mapped_scope not in VALID_USER_CHAIN_STAGES:
            errors.append(f"loopback_target `{target_name}` 的 mapped_refresh_scope `{mapped_scope}` 非法。")
        for builder in [normalize_text(item) for item in ensure_list(target_payload.get("default_target_builders")) if normalize_text(item)]:
            if builder not in builder_set:
                errors.append(f"loopback_target `{target_name}` 的 default builder `{builder}` 未注册。")
        for artifact in [normalize_text(item) for item in ensure_list(target_payload.get("default_target_artifacts")) if normalize_text(item)]:
            if artifact not in artifact_set:
                errors.append(f"loopback_target `{target_name}` 的 default artifact `{artifact}` 未注册。")
        overrides = dict(target_payload.get("artifact_overrides") or {})
        for artifact_name, override_payload in overrides.items():
            normalized_artifact = normalize_text(artifact_name)
            if normalized_artifact not in artifact_set:
                errors.append(f"loopback_target `{target_name}` 的 override artifact `{normalized_artifact}` 未注册。")
            if not isinstance(override_payload, dict):
                errors.append(f"loopback_target `{target_name}` 的 override `{normalized_artifact}` 不是对象。")
                continue
            for builder in [normalize_text(item) for item in ensure_list(override_payload.get("target_builders")) if normalize_text(item)]:
                if builder not in builder_set:
                    errors.append(f"loopback_target `{target_name}` 的 override builder `{builder}` 未注册。")
            for artifact in [normalize_text(item) for item in ensure_list(override_payload.get("target_artifacts")) if normalize_text(item)]:
                if artifact not in artifact_set:
                    errors.append(f"loopback_target `{target_name}` 的 override artifact `{artifact}` 未注册。")

    def detect_cycle() -> list[str]:
        graph = {
            normalize_text(step.get("step_id")): [normalize_text(item) for item in ensure_list(step.get("downstream_steps")) if normalize_text(item)]
            for step in step_by_id.values()
        }
        visited: dict[str, int] = {}
        stack: list[str] = []

        def dfs(node: str) -> list[str]:
            visited[node] = 1
            stack.append(node)
            for child in graph.get(node, []):
                state = visited.get(child, 0)
                if state == 0:
                    cycle = dfs(child)
                    if cycle:
                        return cycle
                elif state == 1:
                    cycle_start = stack.index(child)
                    return stack[cycle_start:] + [child]
            stack.pop()
            visited[node] = 2
            return []

        for node in graph:
            if visited.get(node, 0) == 0:
                cycle = dfs(node)
                if cycle:
                    return cycle
        return []

    cycle = detect_cycle()
    if cycle:
        errors.append(f"registry 存在 DAG 环：{' -> '.join(cycle)}")

    if not steps:
        warnings.append("registry 当前没有 steps。")
    if not loopback_target_names:
        warnings.append("registry 当前没有 loopback_targets。")

    return {
        "valid": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "step_count": len(step_by_id),
        "artifact_count": len(artifact_set),
        "builder_count": len(builder_set),
        "loopback_target_count": len(loopback_target_names),
    }


def _raise_if_invalid(report: dict[str, Any], path: Path) -> None:
    if report.get("valid"):
        return
    joined = " / ".join(str(item) for item in report.get("errors", [])) or "unknown registry validation error"
    raise UserChainDependencyRegistryError(f"user chain dependency registry invalid: {path} :: {joined}")


@lru_cache(maxsize=1)
def load_user_chain_dependency_registry(path: str | Path | None = None) -> dict[str, Any]:
    registry_path = Path(path).expanduser().resolve() if path else USER_CHAIN_DEPENDENCY_REGISTRY_PATH
    payload = read_json(registry_path)
    if not isinstance(payload, dict):
        raise UserChainDependencyRegistryError(f"user chain dependency registry payload must be object: {registry_path}")
    report = validate_user_chain_dependency_registry(payload)
    _raise_if_invalid(report, registry_path)
    return payload


@lru_cache(maxsize=1)
def build_user_chain_dependency_registry_index(path: str | Path | None = None) -> dict[str, Any]:
    payload = load_user_chain_dependency_registry(path)
    steps = ensure_list(payload.get("steps"))
    step_order = [normalize_text(step.get("step_id")) for step in steps if isinstance(step, dict) and normalize_text(step.get("step_id"))]
    step_by_id = {normalize_text(step.get("step_id")): step for step in steps if isinstance(step, dict) and normalize_text(step.get("step_id"))}
    builder_to_step = {
        normalize_text(step.get("builder_id")): normalize_text(step.get("step_id"))
        for step in steps
        if isinstance(step, dict) and normalize_text(step.get("builder_id")) and normalize_text(step.get("step_id"))
    }
    artifact_to_step = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = normalize_text(step.get("step_id"))
        for artifact in ensure_list(step.get("produced_artifacts")):
            artifact_name = normalize_text(artifact)
            if artifact_name:
                artifact_to_step[artifact_name] = step_id
    downstream_graph = {
        normalize_text(step.get("step_id")): [normalize_text(item) for item in ensure_list(step.get("downstream_steps")) if normalize_text(item)]
        for step in steps
        if isinstance(step, dict) and normalize_text(step.get("step_id"))
    }
    return {
        "registry": payload,
        "step_order": step_order,
        "step_by_id": step_by_id,
        "builder_to_step": builder_to_step,
        "artifact_to_step": artifact_to_step,
        "scope_base_steps": dict(payload.get("scope_base_steps") or {}),
        "builder_aliases": dict(payload.get("builder_aliases") or {}),
        "loopback_targets": dict(payload.get("loopback_targets") or {}),
        "downstream_graph": downstream_graph,
    }


def resolve_user_chain_start_step(
    *,
    refresh_scope: str,
    target_builders: list[str] | None = None,
    target_artifacts: list[str] | None = None,
    registry_index: dict[str, Any] | None = None,
) -> str:
    index = registry_index or build_user_chain_dependency_registry_index()
    normalized_scope = normalize_user_refresh_scope(refresh_scope)
    scope_base_steps = dict(index.get("scope_base_steps") or {})
    base_step = normalize_text(scope_base_steps.get(normalized_scope))
    if not base_step:
        raise UserChainDependencyRegistryError(f"missing scope base step for `{normalized_scope}`")
    builder_aliases = dict(index.get("builder_aliases") or {})
    step_order = list(index.get("step_order") or [])
    artifact_to_step = dict(index.get("artifact_to_step") or {})
    builder_to_step = dict(index.get("builder_to_step") or {})
    order_lookup = {step: idx for idx, step in enumerate(step_order)}

    candidate_steps: list[str] = []
    for builder in target_builders or []:
        normalized_builder = builder_aliases.get(normalize_text(builder), normalize_text(builder))
        mapped_step = builder_to_step.get(normalized_builder) or normalized_builder if normalized_builder in order_lookup else builder_to_step.get(normalized_builder, "")
        if mapped_step and mapped_step in order_lookup and order_lookup[mapped_step] >= order_lookup[base_step]:
            candidate_steps.append(mapped_step)
    for artifact in target_artifacts or []:
        mapped_step = artifact_to_step.get(normalize_text(artifact), "")
        if mapped_step and mapped_step in order_lookup and order_lookup[mapped_step] >= order_lookup[base_step]:
            candidate_steps.append(mapped_step)
    if not candidate_steps:
        return base_step
    return min(candidate_steps, key=lambda step: order_lookup[step])


def resolve_user_chain_active_steps(
    *,
    refresh_scope: str,
    target_builders: list[str] | None = None,
    target_artifacts: list[str] | None = None,
    registry_index: dict[str, Any] | None = None,
) -> set[str]:
    index = registry_index or build_user_chain_dependency_registry_index()
    start_step = resolve_user_chain_start_step(
        refresh_scope=refresh_scope,
        target_builders=target_builders,
        target_artifacts=target_artifacts,
        registry_index=index,
    )
    graph = dict(index.get("downstream_graph") or {})
    active_steps: set[str] = set()
    stack = [start_step]
    while stack:
        step = stack.pop()
        if step in active_steps:
            continue
        active_steps.add(step)
        stack.extend(graph.get(step, []))
    return active_steps


def build_user_chain_loopback_execution_plan(
    *,
    loopback_target: Any,
    affected_artifact: Any,
    runtime_dir: str,
    auto_round: int,
    max_auto_loopback_rounds: int = 1,
    registry_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = registry_index or build_user_chain_dependency_registry_index()
    normalized_target = normalize_text(loopback_target)
    target_payload = dict(index.get("loopback_targets", {}).get(normalized_target) or {})
    if not target_payload:
        raise UserChainDependencyRegistryError(f"unknown loopback target: {normalized_target}")
    normalized_artifact = normalize_text(affected_artifact)
    override = dict(target_payload.get("artifact_overrides", {}).get(normalized_artifact) or {})
    target_artifacts = [normalize_text(item) for item in ensure_list(override.get("target_artifacts") or target_payload.get("default_target_artifacts")) if normalize_text(item)]
    target_builders = [normalize_text(item) for item in ensure_list(override.get("target_builders") or target_payload.get("default_target_builders")) if normalize_text(item)]
    mapped_refresh_scope = normalize_text(target_payload.get("mapped_refresh_scope"))
    return {
        "loopback_target": normalized_target,
        "mapped_refresh_scope": mapped_refresh_scope,
        "runtime_dir": runtime_dir,
        "recovery_point": "robot_product_user_insight:post_bundle",
        "will_auto_rerun": bool(mapped_refresh_scope) and auto_round < int(max_auto_loopback_rounds),
        "affected_artifact": normalized_artifact,
        "target_artifacts": target_artifacts,
        "target_builders": target_builders,
        "rerun_rationale": "",
        "auto_round": auto_round,
        "max_auto_loopback_rounds": int(max_auto_loopback_rounds),
        "priority": int(target_payload.get("priority", 99)),
    }


def select_user_chain_loopback_action(
    loopback_actions: list[dict[str, Any]],
    *,
    registry_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = registry_index or build_user_chain_dependency_registry_index()
    loopback_targets = dict(index.get("loopback_targets") or {})
    selected: dict[str, Any] = {}
    selected_priority = 999
    for action in loopback_actions:
        if not isinstance(action, dict):
            continue
        target = normalize_text(action.get("loopback_target"))
        priority = int(dict(loopback_targets.get(target) or {}).get("priority", 999))
        if priority < selected_priority:
            selected_priority = priority
            selected = dict(action)
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate user-chain dependency registry.")
    parser.add_argument("--registry-path", default=str(USER_CHAIN_DEPENDENCY_REGISTRY_PATH), help="Path to registry JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.registry_path).expanduser().resolve()
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise SystemExit("registry payload must be a JSON object")
    report = validate_user_chain_dependency_registry(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("valid"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
