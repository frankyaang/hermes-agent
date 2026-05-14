from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_system.human_approval import normalize_approval_response


SkillExecutor = Callable[[dict[str, Any]], dict[str, Any]]
HumanReviewCallback = Callable[[dict[str, Any]], str | dict[str, Any] | None]


@dataclass(frozen=True)
class RouteNode:
    key: str
    route: dict[str, Any]
    dependencies: tuple[str, ...]
    index: int


class HermesAgentSystemRuntime:
    """Runtime bridge for the example Hermes Agent System.

    The runtime keeps the closed loop local and auditable:
    routes.json -> DAG task packages -> parallel expert Skill calls ->
    audit.jsonl -> review summary -> skill_weights.json update ->
    private memory accumulation.
    """

    DEFAULT_MAX_SPAWN_DEPTH = 1
    MAX_SPAWN_DEPTH = DEFAULT_MAX_SPAWN_DEPTH

    EXCEPTION_RULES: dict[str, dict[str, Any]] = {
        "top15_missing": {
            "trigger": "Top15 < 15",
            "handling": "标记证据不足并进入复盘",
            "blocking": False,
            "audit_field": "top15_count",
            "review_trigger": True,
        },
        "frr_ffr_anomaly": {
            "trigger": "FRR/FFR 缺失或异常",
            "handling": "回退原始值并标记风险等级",
            "blocking": True,
            "audit_field": "risk_adjustment_status",
            "review_trigger": True,
        },
        "competitor_missing": {
            "trigger": "竞品字段缺失",
            "handling": "标记暂无数据并允许主流程继续",
            "blocking": False,
            "audit_field": "competitor_coverage",
            "review_trigger": False,
        },
        "voc_missing": {
            "trigger": "VOC 数据缺失",
            "handling": "阻塞节点并提示补充",
            "blocking": True,
            "audit_field": "voc_available",
            "review_trigger": True,
        },
        "pm_field_missing": {
            "trigger": "PM 输入字段缺失",
            "handling": "退回补充并暂停下游交付",
            "blocking": True,
            "audit_field": "pm_field_complete",
            "review_trigger": True,
        },
        "human_review_conflict": {
            "trigger": "人工结论与系统结论冲突",
            "handling": "标记需主专家复核",
            "blocking": True,
            "audit_field": "human_input_summary",
            "review_trigger": True,
        },
    }

    def __init__(
        self,
        *,
        project_name: str = "agent_system",
        root_dir: str | Path | None = None,
        scheduler_name: str = "main_scheduler",
        skill_executor: SkillExecutor | None = None,
        human_review_callback: HumanReviewCallback | None = None,
        now_fn: Callable[[], datetime] | None = None,
        max_spawn_depth: int = DEFAULT_MAX_SPAWN_DEPTH,
    ) -> None:
        self.project_name = project_name
        self.project_root = Path(root_dir) if root_dir else Path(__file__).resolve().parent
        self.scheduler_name = scheduler_name
        self.skill_executor_is_default = skill_executor is None
        self.skill_executor = skill_executor or self._default_skill_executor
        self.human_review_callback = human_review_callback
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.max_spawn_depth = max(1, int(max_spawn_depth))
        self.scheduler_root = self.project_root / "scheduler"
        self.skills_root = self.project_root / "skills"
        self.experts_root = self.project_root / "experts"
        self.audit_root = self.project_root / "audit"
        self.reviews_root = self.audit_root / "reviews"

    def build_delegate_flow(
        self,
        *,
        pipeline_id: str,
        input_payload: dict[str, Any] | None = None,
        human_inputs: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build single-node task packages without executing them."""
        input_payload = input_payload or {}
        human_inputs = human_inputs or {}
        nodes = self._load_pipeline_nodes(pipeline_id)
        groups = self._topological_groups(nodes)
        packages: list[dict[str, Any]] = []
        for group_index, group in enumerate(groups, start=1):
            for node_key in group:
                route_node = nodes[node_key]
                packages.append(
                    self._build_task_package(
                        pipeline_id=pipeline_id,
                        route_node=route_node,
                        input_payload=input_payload,
                        human_inputs=human_inputs,
                        parallel_group=group_index,
                    )
                )
        return {
            "pipeline_id": pipeline_id,
            "max_spawn_depth": self.max_spawn_depth,
            "execution_groups": groups,
            "delegate_tasks": packages,
            "flow_visualization": (
                "主智能体 -> Skill 执行 -> 子专家 -> Skill 执行 -> "
                "人工介入 -> 输出 + 审计 -> 复盘与权重优化"
            ),
        }

    def run_pipeline(
        self,
        *,
        pipeline_id: str,
        input_payload: dict[str, Any] | None = None,
        human_inputs: dict[str, str] | None = None,
        parallel: bool = True,
    ) -> dict[str, Any]:
        """Execute a pipeline DAG and return the closed-loop run record."""
        input_payload = input_payload or {}
        human_inputs = human_inputs or {}
        started_at = self.now_fn()
        run_id = self._make_run_id(started_at, pipeline_id)
        nodes = self._load_pipeline_nodes(pipeline_id)
        groups = self._topological_groups(nodes)
        results: dict[str, dict[str, Any]] = {}

        for group_index, group in enumerate(groups, start=1):
            blocked_results: list[dict[str, Any]] = []
            executable_nodes: list[RouteNode] = []
            for node_key in group:
                route_node = nodes[node_key]
                blocked = self._blocked_by_dependencies(route_node, nodes, results)
                if blocked:
                    blocked_results.append(
                        self._dependency_blocked_result(
                            run_id=run_id,
                            pipeline_id=pipeline_id,
                            route_node=route_node,
                            blocked_by=blocked,
                            input_payload=input_payload,
                            human_inputs=human_inputs,
                            parallel_group=group_index,
                        )
                    )
                else:
                    executable_nodes.append(route_node)

            for result in blocked_results:
                results[result["node_key"]] = result
                self._append_audit_event(result)

            if parallel and len(executable_nodes) > 1:
                with ThreadPoolExecutor(max_workers=len(executable_nodes)) as pool:
                    futures = {
                        pool.submit(
                            self._execute_node,
                            run_id=run_id,
                            pipeline_id=pipeline_id,
                            route_node=route_node,
                            input_payload=input_payload,
                            human_inputs=human_inputs,
                            prior_results=results,
                            parallel_group=group_index,
                        ): route_node.key
                        for route_node in executable_nodes
                    }
                    for future in as_completed(futures):
                        result = future.result()
                        results[result["node_key"]] = result
                        self._append_audit_event(result)
            else:
                for route_node in executable_nodes:
                    result = self._execute_node(
                        run_id=run_id,
                        pipeline_id=pipeline_id,
                        route_node=route_node,
                        input_payload=input_payload,
                        human_inputs=human_inputs,
                        prior_results=results,
                        parallel_group=group_index,
                    )
                    results[result["node_key"]] = result
                    self._append_audit_event(result)

        ordered_results = [results[key] for group in groups for key in group if key in results]
        review_summary = self._write_review_summary(
            run_id=run_id,
            pipeline_id=pipeline_id,
            started_at=started_at,
            results=ordered_results,
        )
        experience_updates = self._append_private_memory(run_id, ordered_results, review_summary)
        review_summary["experience_isolation"] = self._experience_isolation_policy()
        review_summary["experience_updates"] = experience_updates
        self._persist_review_summary(run_id, review_summary)

        return {
            "run_id": run_id,
            "pipeline_id": pipeline_id,
            "status": self._overall_status(ordered_results),
            "max_spawn_depth": self.max_spawn_depth,
            "execution_groups": groups,
            "delegate_flow": self.build_delegate_flow(
                pipeline_id=pipeline_id,
                input_payload=input_payload,
                human_inputs=human_inputs,
            ),
            "results": ordered_results,
            "audit_log": str(self.audit_root / "audit.jsonl"),
            "review_summary": review_summary,
        }

    def _execute_node(
        self,
        *,
        run_id: str,
        pipeline_id: str,
        route_node: RouteNode,
        input_payload: dict[str, Any],
        human_inputs: dict[str, str],
        prior_results: dict[str, dict[str, Any]],
        parallel_group: int,
    ) -> dict[str, Any]:
        route = route_node.route
        package = self._build_task_package(
            pipeline_id=pipeline_id,
            route_node=route_node,
            input_payload=input_payload,
            human_inputs=human_inputs,
            parallel_group=parallel_group,
        )
        started_at = self.now_fn().isoformat()
        exceptions = self._preflight_exceptions(route, input_payload)
        missing_inputs = [
            event["audit_field"]
            for event in exceptions
            if event.get("event") == "voc_missing"
        ]
        skill_calls: list[dict[str, Any]] = []
        dynamic_overrides: list[dict[str, Any]] = []

        blocking_preflight = any(event.get("blocking") for event in exceptions)
        if not blocking_preflight:
            skill_calls = self._execute_expert_skill_calls(
                package=package,
                route=route,
                input_payload=input_payload,
                prior_results=prior_results,
            )
            for call in skill_calls:
                exceptions.extend(call.get("exceptions", []))
                exceptions.extend(self._map_exceptions(call.get("output", {})))
                dynamic_overrides.extend(call.get("dynamic_overrides", []))
                missing_inputs.extend(call.get("missing_inputs", []))

        exceptions = self._dedupe_exceptions(exceptions)
        human_review_required = bool(route.get("user_gate")) or any(
            event.get("blocking") for event in exceptions
        )
        human_review_ui_available = self.human_review_callback is not None
        human_input_summary = human_inputs.get(route_node.key) or human_inputs.get(route.get("node"), "")
        human_review_result = normalize_approval_response(
            human_input_summary,
            channel="preseeded_human_input" if human_input_summary else "unavailable",
        )
        if human_review_required and not human_input_summary:
            human_review_result = self._collect_human_review(
                pipeline_id=pipeline_id,
                route_node=route_node,
                package=package,
                exceptions=exceptions,
                output=self._merge_skill_outputs(skill_calls),
            )
            human_input_summary = human_review_result["summary"]
            if human_input_summary:
                human_inputs[route_node.key] = human_input_summary
                package["human_input_summary"] = human_input_summary
        human_review_recorded = not human_review_required or bool(human_input_summary)
        human_review_blocking = human_review_required and bool(human_review_result["blocking"])

        if blocking_preflight:
            status = "blocked"
        elif any(call.get("status") == "failed" for call in skill_calls):
            status = "failed"
        elif human_review_blocking:
            status = "blocked"
        elif any(event.get("blocking") for event in exceptions) and not human_input_summary:
            status = "blocked"
        elif route.get("user_gate") and not human_input_summary:
            status = "blocked"
        else:
            status = "completed"

        if route.get("optional") and status in {"blocked", "failed"}:
            status = "optional_failed"

        output = self._merge_skill_outputs(skill_calls)
        if human_input_summary:
            output["human_input_summary"] = human_input_summary
            output["human_review_decision"] = human_review_result["decision"]
        audit_checks = self._build_audit_checks(
            output=output,
            exceptions=exceptions,
            human_review_required=human_review_required,
            human_review_recorded=human_review_recorded,
            human_review_ui_available=human_review_ui_available,
            human_review_decision=human_review_result["decision"],
            skill_calls=skill_calls,
        )
        skill_execution_modes = sorted(
            {
                str(call.get("execution_mode"))
                for call in skill_calls
                if call.get("execution_mode")
            }
        )
        real_skill_execution = bool(skill_calls) and all(
            bool(call.get("output", {}).get("real_skill_execution"))
            for call in skill_calls
            if isinstance(call.get("output"), dict)
        )
        result = {
            "run_id": run_id,
            "pipeline_id": pipeline_id,
            "node_key": route_node.key,
            "node_id": route.get("node"),
            "display_name": route.get("display_name", route.get("node")),
            "status": status,
            "optional": bool(route.get("optional")),
            "user_gate": bool(route.get("user_gate")),
            "final_output": bool(route.get("final_output")),
            "depends_on": list(route_node.dependencies),
            "parallel_group": parallel_group,
            "task_package": package,
            "primary_expert": package["primary_expert_id"],
            "secondary_experts": package["secondary_expert_ids"],
            "primary_expert_skill_calls": [
                call for call in skill_calls if call.get("expert_role") == "primary"
            ],
            "secondary_expert_skill_calls": [
                call for call in skill_calls if call.get("expert_role") == "secondary"
            ],
            "skills_loaded": sorted({call["skill_id"] for call in skill_calls}),
            "skill_weights": package["default_skill_weights"],
            "dynamic_overrides": dynamic_overrides,
            "human_review_required": "是" if human_review_required else "否",
            "human_review_ui_available": human_review_ui_available,
            "human_review_decision": human_review_result["decision"],
            "human_review_blocking": human_review_result["blocking"],
            "human_review_channel": human_review_result["channel"],
            "human_input_summary": human_input_summary,
            "skill_execution_modes": skill_execution_modes,
            "real_skill_execution": real_skill_execution,
            "memory_access_policy": package["memory_access_policy"],
            "experience_write_scope": package["experience_write_scope"],
            "output": output,
            "exceptions": exceptions,
            "missing_inputs": sorted(set(missing_inputs)),
            "audit_checks": audit_checks,
            "started_at": started_at,
            "completed_at": self.now_fn().isoformat(),
        }
        return result

    def _collect_human_review(
        self,
        *,
        pipeline_id: str,
        route_node: RouteNode,
        package: dict[str, Any],
        exceptions: list[dict[str, Any]],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        if self.human_review_callback is None:
            return normalize_approval_response(None, channel="unavailable")
        request = {
            "pipeline_id": pipeline_id,
            "node_key": route_node.key,
            "node_id": route_node.route.get("node"),
            "display_name": route_node.route.get("display_name", route_node.route.get("node")),
            "human_review_required": "是",
            "task_package": package,
            "exceptions": exceptions,
            "output": output,
            "audit_focus": [
                event.get("audit_field")
                for event in exceptions
                if event.get("audit_field")
            ],
        }
        try:
            response = self.human_review_callback(request)
        except Exception:
            return normalize_approval_response(None, channel="callback_error")
        return normalize_approval_response(response, channel="agent_system_approval_ui")

    def _execute_expert_skill_calls(
        self,
        *,
        package: dict[str, Any],
        route: dict[str, Any],
        input_payload: dict[str, Any],
        prior_results: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        call_specs: list[dict[str, Any]] = []
        primary = package.get("primary_expert_id")
        if primary:
            call_specs.append({"expert_role": "primary", "expert_id": primary, "index": 0})
        for index, expert_id in enumerate(package.get("secondary_expert_ids", []), start=1):
            call_specs.append(
                {"expert_role": "secondary", "expert_id": expert_id, "index": index}
            )
        if not call_specs:
            return [
                self._execute_skill_without_expert(
                    package=package,
                    route=route,
                    input_payload=input_payload,
                    prior_results=prior_results,
                )
            ]
        if len(call_specs) == 1:
            spec = call_specs[0]
            return [
                self._execute_single_expert_skill(
                    expert_role=spec["expert_role"],
                    expert_id=spec["expert_id"],
                    package=package,
                    route=route,
                    input_payload=input_payload,
                    prior_results=prior_results,
                )
            ]

        calls_by_index: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=len(call_specs)) as pool:
            futures = {
                pool.submit(
                    self._execute_single_expert_skill,
                    expert_role=spec["expert_role"],
                    expert_id=spec["expert_id"],
                    package=package,
                    route=route,
                    input_payload=input_payload,
                    prior_results=prior_results,
                ): spec["index"]
                for spec in call_specs
            }
            for future in as_completed(futures):
                calls_by_index[futures[future]] = future.result()
        return [calls_by_index[index] for index in sorted(calls_by_index)]

    def _execute_single_expert_skill(
        self,
        *,
        expert_role: str,
        expert_id: str,
        package: dict[str, Any],
        route: dict[str, Any],
        input_payload: dict[str, Any],
        prior_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        expert = self._load_expert(expert_id)
        requested_skill = route.get("node")
        skill_id = requested_skill if requested_skill in expert.get("skills", []) else expert["skills"][0]
        dynamic_override = skill_id != requested_skill
        return self._execute_skill_call(
            expert_role=expert_role,
            expert_id=expert_id,
            skill_id=skill_id,
            requested_skill=requested_skill,
            package=package,
            input_payload=input_payload,
            prior_results=prior_results,
            dynamic_override=dynamic_override,
        )

    def _execute_skill_without_expert(
        self,
        *,
        package: dict[str, Any],
        route: dict[str, Any],
        input_payload: dict[str, Any],
        prior_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        skill_id = route["node"]
        return self._execute_skill_call(
            expert_role="system",
            expert_id=None,
            skill_id=skill_id,
            requested_skill=skill_id,
            package=package,
            input_payload=input_payload,
            prior_results=prior_results,
            dynamic_override=False,
        )

    def _execute_skill_call(
        self,
        *,
        expert_role: str,
        expert_id: str | None,
        skill_id: str,
        requested_skill: str,
        package: dict[str, Any],
        input_payload: dict[str, Any],
        prior_results: dict[str, dict[str, Any]],
        dynamic_override: bool,
    ) -> dict[str, Any]:
        skill = self._load_skill(skill_id)
        context = {
            "task_package": package,
            "expert_role": expert_role,
            "expert_id": expert_id,
            "skill_id": skill_id,
            "requested_skill_id": requested_skill,
            "skill": skill,
            "input_payload": input_payload,
            "prior_results": prior_results,
            "max_spawn_depth": self.max_spawn_depth,
            "memory_access_policy": package["memory_access_policy"],
            "experience_write_scope": {
                "system_level": "read_only",
                "expert_level": f"read_only:{expert_id}" if expert_id else "read_only",
                "skill_level": f"write:{skill_id}",
                "write_rule": "Skill 执行结果只能写入本 Skill 经验；专家决策由运行器写入对应专家经验。",
            },
        }
        started_at = self.now_fn().isoformat()
        try:
            raw_result = self.skill_executor(context)
            if not isinstance(raw_result, dict):
                raw_result = {"result_summary": str(raw_result)}
            status = raw_result.get("status", "completed")
            output = raw_result.get("output", raw_result)
            exceptions = raw_result.get("exceptions", [])
            missing_inputs = raw_result.get("missing_inputs", [])
            audit_checks = raw_result.get("audit_checks", {})
            output_quality = float(raw_result.get("output_quality", 85 if status == "completed" else 50))
            execution_mode = raw_result.get("execution_mode") or (
                "local_default_executor" if self.skill_executor_is_default else "custom_skill_executor"
            )
        except Exception as exc:
            status = "failed"
            output = {"result_summary": f"Skill 执行失败：{exc}"}
            exceptions = [
                {
                    "event": "skill_execution_failed",
                    "trigger": str(exc),
                    "handling": "记录失败并进入复盘",
                    "blocking": True,
                    "audit_field": "skill_execution",
                    "review_trigger": True,
                }
            ]
            missing_inputs = []
            audit_checks = {}
            output_quality = 0.0
            execution_mode = "executor_exception"

        dynamic_overrides = list(output.get("dynamic_overrides", [])) if isinstance(output, dict) else []
        if dynamic_override:
            dynamic_overrides.append(
                {
                    "override_trigger": "expert_skill_scope",
                    "override_reason": f"{expert_id or 'system'} 不直接加载 {requested_skill}，改用 {skill_id}",
                    "replacement_skill_id": skill_id,
                    "coverage_result": "success" if status == "completed" else "failed",
                    "impact_on_weight": -1,
                }
            )
        return {
            "expert_role": expert_role,
            "expert_id": expert_id,
            "skill_id": skill_id,
            "requested_skill_id": requested_skill,
            "base_weight": package["default_skill_weights"].get(skill_id, 50),
            "status": status,
            "output": output,
            "execution_mode": execution_mode,
            "exceptions": exceptions,
            "missing_inputs": missing_inputs,
            "audit_checks": audit_checks,
            "output_quality": output_quality,
            "dynamic_overrides": dynamic_overrides,
            "started_at": started_at,
            "completed_at": self.now_fn().isoformat(),
        }

    def _default_skill_executor(self, context: dict[str, Any]) -> dict[str, Any]:
        skill = context["skill"]
        package = context["task_package"]
        return {
            "status": "completed",
            "output_quality": 85,
            "output": {
                "result_summary": (
                    f"{context.get('expert_id') or 'system'} 使用 "
                    f"{skill.get('display_name', context['skill_id'])} 完成节点 "
                    f"{package['node_id']}"
                ),
                "node_id": package["node_id"],
                "skill_id": context["skill_id"],
                "expert_id": context.get("expert_id"),
                "output_type": package["output_constraints"].get("output_type"),
            },
            "audit_checks": {
                "skill_execution_completed": True,
                "max_spawn_depth_respected": context["max_spawn_depth"] == self.max_spawn_depth,
            },
        }

    def _build_task_package(
        self,
        *,
        pipeline_id: str,
        route_node: RouteNode,
        input_payload: dict[str, Any],
        human_inputs: dict[str, str],
        parallel_group: int,
    ) -> dict[str, Any]:
        route = route_node.route
        supervision = route.get("supervision") or {}
        primary = supervision.get("primary_expert")
        secondary = list(supervision.get("secondary_experts") or [])
        default_skill_weights = self._default_skill_weights(primary, secondary, route["node"])
        human_review_required = bool(route.get("user_gate"))
        human_input_summary = human_inputs.get(route_node.key) or human_inputs.get(route["node"], "")
        delegate_role = "orchestrator" if self.max_spawn_depth > 1 else "leaf"
        delegate_context = (
            "单节点任务包；允许在 DAG 依赖和 max_spawn_depth 限制内继续拆分。"
            if delegate_role == "orchestrator"
            else "单节点任务包；禁止继续拆分为更深层子智能体。"
        )
        return {
            "task_id": f"{pipeline_id}:{route_node.key}",
            "flow_id": pipeline_id,
            "node_id": route["node"],
            "node_key": route_node.key,
            "display_name": route.get("display_name", route["node"]),
            "primary_expert_id": primary,
            "secondary_expert_ids": secondary,
            "default_skill_weights": default_skill_weights,
            "input_constraints": {
                "input_type": (route.get("constraints") or {}).get("input_type"),
                "max_runtime": (route.get("constraints") or {}).get("max_runtime"),
                "source_materials_count": len(input_payload.get("source_materials", []) or []),
            },
            "output_constraints": {
                "output_type": (route.get("constraints") or {}).get("output_type"),
                "final_output": bool(route.get("final_output")),
            },
            "depends_on": list(route_node.dependencies),
            "optional": bool(route.get("optional")),
            "user_gate": bool(route.get("user_gate")),
            "human_review_required": "是" if human_review_required else "否",
            "human_review_channel": "clarify_callback" if self.human_review_callback else "unavailable",
            "human_input_summary": human_input_summary,
            "parallel_group": parallel_group,
            "max_spawn_depth": self.max_spawn_depth,
            "delegate_task": {
                "goal": f"执行 {route.get('display_name', route['node'])} 单节点任务",
                "context": delegate_context,
                "role": delegate_role,
            },
            "memory_access_policy": self._memory_access_policy(
                primary_expert=primary,
                secondary_experts=secondary,
                skill_ids=sorted(default_skill_weights),
            ),
            "experience_write_scope": {
                "system_level": "Hermes 主代理 / 运行器全局摘要",
                "expert_level": [expert_id for expert_id in [primary, *secondary] if expert_id],
                "skill_level": sorted(default_skill_weights),
                "isolation_rule": "各层只写自身经验库，不跨层覆盖；复盘摘要只记录索引和路径。",
            },
        }

    def _memory_access_policy(
        self,
        *,
        primary_expert: str | None,
        secondary_experts: list[str],
        skill_ids: list[str],
    ) -> dict[str, Any]:
        expert_ids = [expert_id for expert_id in [primary_expert, *secondary_experts] if expert_id]
        return {
            "system_level": {
                "read": True,
                "write": "Hermes 主代理 / 全局运行器",
                "path": str(self.project_root / "memory" / "system_mem" / "MEMORY.md"),
            },
            "expert_level": {
                "read": expert_ids,
                "write": expert_ids,
                "paths": {
                    expert_id: str(self.experts_root / expert_id / "expert_mem" / "MEMORY.md")
                    for expert_id in expert_ids
                },
            },
            "skill_level": {
                "read": skill_ids,
                "write": skill_ids,
                "paths": {
                    skill_id: str(self.skills_root / skill_id / "skill_mem" / "MEMORY.md")
                    for skill_id in skill_ids
                },
            },
            "write_boundary": (
                "专家只写专家级经验，Skill 只写 Skill 级经验，系统级经验只由 Hermes 主代理维护。"
            ),
        }

    def _default_skill_weights(
        self,
        primary_expert: str | None,
        secondary_experts: list[str],
        route_skill: str,
    ) -> dict[str, int]:
        weights: dict[str, int] = {}
        for expert_id in [primary_expert, *secondary_experts]:
            if not expert_id:
                continue
            expert = self._load_expert(expert_id)
            for index, skill_id in enumerate(expert.get("skills", [])):
                base_weight = max(50, 90 - index * 10)
                weights[skill_id] = max(weights.get(skill_id, 0), base_weight)
        weights.setdefault(route_skill, 90)
        stored = self._read_skill_weights().get("skills", {})
        for skill_id, payload in stored.items():
            if skill_id in weights and isinstance(payload, dict) and "weight" in payload:
                weights[skill_id] = int(payload["weight"])
        return weights

    def _load_pipeline_nodes(self, pipeline_id: str) -> dict[str, RouteNode]:
        routes_path = self.scheduler_root / self.scheduler_name / "routes.json"
        payload = self._read_json(routes_path)
        routes = [
            route
            for route in payload.get("pipelines", [])
            if route.get("pipeline_id") == pipeline_id
        ]
        if not routes:
            raise ValueError(f"Pipeline does not exist in routes.json: {pipeline_id}")
        node_keys = [route["node"] for route in routes]
        duplicates = sorted({node for node in node_keys if node_keys.count(node) > 1})
        if duplicates:
            raise ValueError(
                "Runtime requires unique node ids per pipeline. Duplicates: "
                + ", ".join(duplicates)
            )
        nodes: dict[str, RouteNode] = {}
        for index, route in enumerate(routes):
            node = route.get("node")
            if not node:
                raise ValueError(f"Route #{index + 1} is missing node")
            dependencies = self._normalize_dependencies(route)
            nodes[node] = RouteNode(
                key=node,
                route=route,
                dependencies=tuple(dependencies),
                index=index,
            )
        missing_dependencies = sorted(
            {
                dependency
                for route_node in nodes.values()
                for dependency in route_node.dependencies
                if dependency not in nodes
            }
        )
        if missing_dependencies:
            raise ValueError("Pipeline references missing dependencies: " + ", ".join(missing_dependencies))
        return nodes

    @staticmethod
    def _normalize_dependencies(route: dict[str, Any]) -> list[str]:
        dependencies: list[str] = []
        for field_name in ("depends_on", "trigger"):
            value = route.get(field_name, [])
            if isinstance(value, str):
                value = [value]
            dependencies.extend(value or [])
        return list(dict.fromkeys(dependencies))

    def _topological_groups(self, nodes: dict[str, RouteNode]) -> list[list[str]]:
        remaining = set(nodes)
        resolved: set[str] = set()
        groups: list[list[str]] = []
        while remaining:
            ready = sorted(
                [
                    node_key
                    for node_key in remaining
                    if set(nodes[node_key].dependencies).issubset(resolved)
                ],
                key=lambda key: nodes[key].index,
            )
            if not ready:
                raise ValueError("Pipeline routes contain a dependency cycle")
            groups.append(ready)
            resolved.update(ready)
            remaining.difference_update(ready)
        return groups

    def _blocked_by_dependencies(
        self,
        route_node: RouteNode,
        nodes: dict[str, RouteNode],
        results: dict[str, dict[str, Any]],
    ) -> list[str]:
        blocked: list[str] = []
        for dependency in route_node.dependencies:
            dep_result = results.get(dependency)
            if dep_result is None:
                blocked.append(dependency)
                continue
            if dep_result["status"] == "completed":
                continue
            if nodes[dependency].route.get("optional"):
                continue
            blocked.append(dependency)
        return blocked

    def _dependency_blocked_result(
        self,
        *,
        run_id: str,
        pipeline_id: str,
        route_node: RouteNode,
        blocked_by: list[str],
        input_payload: dict[str, Any],
        human_inputs: dict[str, str],
        parallel_group: int,
    ) -> dict[str, Any]:
        package = self._build_task_package(
            pipeline_id=pipeline_id,
            route_node=route_node,
            input_payload=input_payload,
            human_inputs=human_inputs,
            parallel_group=parallel_group,
        )
        status = "optional_failed" if route_node.route.get("optional") else "blocked_dependency"
        return {
            "run_id": run_id,
            "pipeline_id": pipeline_id,
            "node_key": route_node.key,
            "node_id": route_node.route.get("node"),
            "display_name": route_node.route.get("display_name", route_node.key),
            "status": status,
            "optional": bool(route_node.route.get("optional")),
            "user_gate": bool(route_node.route.get("user_gate")),
            "final_output": bool(route_node.route.get("final_output")),
            "depends_on": list(route_node.dependencies),
            "parallel_group": parallel_group,
            "task_package": package,
            "primary_expert": package["primary_expert_id"],
            "secondary_experts": package["secondary_expert_ids"],
            "primary_expert_skill_calls": [],
            "secondary_expert_skill_calls": [],
            "skills_loaded": [],
            "skill_weights": package["default_skill_weights"],
            "dynamic_overrides": [],
            "human_review_required": package["human_review_required"],
            "human_input_summary": package["human_input_summary"],
            "human_review_ui_available": self.human_review_callback is not None,
            "human_review_decision": "missing",
            "human_review_blocking": True,
            "human_review_channel": package["human_review_channel"],
            "skill_execution_modes": [],
            "real_skill_execution": False,
            "memory_access_policy": package["memory_access_policy"],
            "experience_write_scope": package["experience_write_scope"],
            "output": {"result_summary": "依赖节点未完成，当前节点暂停", "blocked_by": blocked_by},
            "exceptions": [
                {
                    "event": "dependency_blocked",
                    "trigger": ",".join(blocked_by),
                    "handling": "等待依赖节点恢复",
                    "blocking": True,
                    "audit_field": "depends_on",
                    "review_trigger": True,
                }
            ],
            "missing_inputs": [],
            "audit_checks": {"dependencies_satisfied": False},
            "started_at": self.now_fn().isoformat(),
            "completed_at": self.now_fn().isoformat(),
        }

    def _preflight_exceptions(
        self,
        route: dict[str, Any],
        input_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        constraints = route.get("constraints") or {}
        input_type = str(constraints.get("input_type") or "")
        if "VOC" in input_type and not input_payload.get("source_materials"):
            return [self._exception_event("voc_missing", value=False)]
        return []

    def _map_exceptions(self, output: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(output, dict):
            return []
        events: list[dict[str, Any]] = []
        top15_count = output.get("top15_count")
        try:
            top15_value = int(top15_count) if top15_count is not None else None
        except (TypeError, ValueError):
            top15_value = 0
        if top15_value is not None and top15_value < 15:
            events.append(self._exception_event("top15_missing", value=top15_count))
        risk_status = str(output.get("risk_adjustment_status") or "").lower()
        if risk_status in {"missing", "anomaly", "异常", "缺失"}:
            events.append(self._exception_event("frr_ffr_anomaly", value=risk_status))
        competitor_coverage = output.get("competitor_coverage")
        if competitor_coverage in {0, "0", "missing", "缺失", None} and output.get("competitor_required"):
            events.append(self._exception_event("competitor_missing", value=competitor_coverage))
        if output.get("pm_field_complete") is False:
            events.append(self._exception_event("pm_field_missing", value=False))
        if output.get("human_review_conflict"):
            events.append(self._exception_event("human_review_conflict", value=output.get("human_input_summary")))
        return events

    def _exception_event(self, event: str, *, value: Any = None) -> dict[str, Any]:
        rule = self.EXCEPTION_RULES[event]
        return {
            "event": event,
            "trigger": rule["trigger"],
            "handling": rule["handling"],
            "blocking": bool(rule["blocking"]),
            "audit_field": rule["audit_field"],
            "review_trigger": bool(rule["review_trigger"]),
            "value": value,
        }

    @staticmethod
    def _dedupe_exceptions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            key = (str(event.get("event")), str(event.get("audit_field")))
            deduped[key] = event
        return list(deduped.values())

    @staticmethod
    def _merge_skill_outputs(skill_calls: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {"skill_outputs": []}
        for call in skill_calls:
            output = call.get("output", {})
            merged["skill_outputs"].append(
                {
                    "expert_id": call.get("expert_id"),
                    "expert_role": call.get("expert_role"),
                    "skill_id": call.get("skill_id"),
                    "status": call.get("status"),
                    "output": output,
                }
            )
            if isinstance(output, dict):
                for field_name in (
                    "top15_count",
                    "risk_adjustment_status",
                    "competitor_coverage",
                    "pm_field_complete",
                ):
                    if field_name in output:
                        merged[field_name] = output[field_name]
        if skill_calls:
            merged["result_summary"] = "; ".join(
                str(call.get("output", {}).get("result_summary", call.get("skill_id")))
                for call in skill_calls
            )
        return merged

    @staticmethod
    def _build_audit_checks(
        *,
        output: dict[str, Any],
        exceptions: list[dict[str, Any]],
        human_review_required: bool,
        human_review_recorded: bool,
        human_review_ui_available: bool,
        human_review_decision: str,
        skill_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        exception_names = {event.get("event") for event in exceptions}
        checks: dict[str, Any] = {
            "skill_loaded": bool(skill_calls),
            "max_spawn_depth_respected": True,
            "human_review_recorded": human_review_recorded,
            "human_review_ui_available": human_review_ui_available,
            "human_review_approved": human_review_decision == "approved",
            "blocking_exception_absent": not any(event.get("blocking") for event in exceptions),
            "real_skill_execution": bool(skill_calls) and all(
                bool(call.get("output", {}).get("real_skill_execution"))
                for call in skill_calls
                if isinstance(call.get("output"), dict)
            ),
        }
        if "top15_count" in output:
            checks["top15_complete"] = output["top15_count"] == 15
        if "frr_ffr_anomaly" in exception_names:
            checks["frr_ffr_risk_only"] = False
        else:
            checks["frr_ffr_risk_only"] = True
        if "competitor_missing" in exception_names:
            checks["competitor_row_complete"] = False
        if "pm_field_missing" in exception_names:
            checks["pm_input_complete"] = False
        if human_review_required:
            checks["human_review_required"] = True
        return checks

    def _write_review_summary(
        self,
        *,
        run_id: str,
        pipeline_id: str,
        started_at: datetime,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.reviews_root.mkdir(parents=True, exist_ok=True)
        skill_weight_suggestions = self._compute_skill_weight_suggestions(results)
        triggers = self._review_triggers(started_at, results)
        summary = {
            "run_id": run_id,
            "pipeline_id": pipeline_id,
            "review_period": self._review_period(started_at),
            "review_triggers": triggers,
            "task_count": len(results),
            "success_rate": self._success_rate(results),
            "average_output_quality": self._average_output_quality(results),
            "exception_count": sum(len(result.get("exceptions", [])) for result in results),
            "dynamic_coverage_frequency": sum(len(result.get("dynamic_overrides", [])) for result in results),
            "human_review_count": sum(
                1 for result in results if result.get("human_review_required") == "是"
            ),
            "human_input_summary": [
                result["human_input_summary"]
                for result in results
                if result.get("human_input_summary")
            ],
            "human_review_decisions": [
                {
                    "node_id": result.get("node_id"),
                    "decision": result.get("human_review_decision"),
                    "blocking": result.get("human_review_blocking"),
                    "channel": result.get("human_review_channel"),
                    "summary": result.get("human_input_summary"),
                }
                for result in results
                if result.get("human_review_required") == "是"
            ],
            "default_skill_usage": self._skill_usage(results),
            "dynamic_overrides": [
                item
                for result in results
                for item in result.get("dynamic_overrides", [])
            ],
            "exceptions": [
                item
                for result in results
                for item in result.get("exceptions", [])
            ],
            "weight_adjustments": skill_weight_suggestions,
            "skill_weights_updated": True,
            "rule_update_suggestions": self._rule_update_suggestions(results),
            "flow_visualization": (
                "主智能体 -> Skill 执行 -> 子专家 -> Skill 执行 -> "
                "人工介入 -> 输出 + 审计 -> 复盘与权重优化"
            ),
        }
        self._write_skill_weights(skill_weight_suggestions)
        review_path = self.reviews_root / f"{run_id}.json"
        latest_path = self.audit_root / "review_summary.json"
        self._write_json(review_path, summary)
        self._write_json(latest_path, summary)
        return summary

    def _persist_review_summary(self, run_id: str, summary: dict[str, Any]) -> None:
        self.reviews_root.mkdir(parents=True, exist_ok=True)
        self.audit_root.mkdir(parents=True, exist_ok=True)
        self._write_json(self.reviews_root / f"{run_id}.json", summary)
        self._write_json(self.audit_root / "review_summary.json", summary)

    def _compute_skill_weight_suggestions(
        self,
        results: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        for result in results:
            for call in [
                *result.get("primary_expert_skill_calls", []),
                *result.get("secondary_expert_skill_calls", []),
            ]:
                skill_id = call["skill_id"]
                entry = stats.setdefault(
                    skill_id,
                    {
                        "base_weight": call.get("base_weight", 50),
                        "total": 0,
                        "success": 0,
                        "quality_scores": [],
                        "exception_count": 0,
                        "dynamic_coverage_frequency": 0,
                    },
                )
                entry["total"] += 1
                if call.get("status") == "completed":
                    entry["success"] += 1
                entry["quality_scores"].append(float(call.get("output_quality", 0)))
                entry["exception_count"] += len(call.get("exceptions", []))
                entry["dynamic_coverage_frequency"] += len(call.get("dynamic_overrides", []))

        suggestions: dict[str, dict[str, Any]] = {}
        for skill_id, entry in stats.items():
            success_rate = (entry["success"] / entry["total"]) * 100 if entry["total"] else 0
            output_quality = (
                sum(entry["quality_scores"]) / len(entry["quality_scores"])
                if entry["quality_scores"]
                else 0
            )
            weight = self._skill_weight_formula(
                base_weight=entry["base_weight"],
                success_rate=success_rate,
                output_quality=output_quality,
                exception_count=entry["exception_count"],
                dynamic_coverage_frequency=entry["dynamic_coverage_frequency"],
            )
            suggestions[skill_id] = {
                "base_weight": entry["base_weight"],
                "success_rate": round(success_rate, 2),
                "output_quality": round(output_quality, 2),
                "exception_count": entry["exception_count"],
                "dynamic_coverage_frequency": entry["dynamic_coverage_frequency"],
                "weight": weight,
                "formula": (
                    "Skill_Weight = Base_Weight + Success_Rate*0.4 + "
                    "Output_Quality*0.3 - Exception_Count*0.2 + "
                    "Dynamic_Coverage_Frequency*-0.1"
                ),
            }
        return suggestions

    @staticmethod
    def _skill_weight_formula(
        *,
        base_weight: float,
        success_rate: float,
        output_quality: float,
        exception_count: float,
        dynamic_coverage_frequency: float,
    ) -> int:
        raw = (
            base_weight
            + success_rate * 0.4
            + output_quality * 0.3
            - exception_count * 0.2
            + dynamic_coverage_frequency * -0.1
        )
        return int(max(0, min(100, round(raw))))

    def _write_skill_weights(self, suggestions: dict[str, dict[str, Any]]) -> None:
        payload = {
            "version": 1,
            "updated_at": self.now_fn().isoformat(),
            "formula": (
                "Skill_Weight = Base_Weight + Success_Rate*0.4 + "
                "Output_Quality*0.3 - Exception_Count*0.2 + "
                "Dynamic_Coverage_Frequency*-0.1"
            ),
            "skills": suggestions,
        }
        (self.project_root / "skill_weights.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _read_skill_weights(self) -> dict[str, Any]:
        path = self.project_root / "skill_weights.json"
        if not path.exists():
            return {}
        return self._read_json(path)

    def _append_audit_event(self, result: dict[str, Any]) -> None:
        self.audit_root.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": self.now_fn().isoformat(),
            "run_id": result["run_id"],
            "pipeline_id": result["pipeline_id"],
            "node_id": result["node_id"],
            "status": result["status"],
            "primary_expert": result.get("primary_expert"),
            "secondary_experts": result.get("secondary_experts", []),
            "skills_loaded": result.get("skills_loaded", []),
            "human_review_required": result.get("human_review_required"),
            "human_review_ui_available": result.get("human_review_ui_available"),
            "human_review_decision": result.get("human_review_decision"),
            "human_review_blocking": result.get("human_review_blocking"),
            "human_review_channel": result.get("human_review_channel"),
            "human_input_summary": result.get("human_input_summary"),
            "skill_execution_modes": result.get("skill_execution_modes", []),
            "real_skill_execution": result.get("real_skill_execution"),
            "memory_access_policy": result.get("memory_access_policy", {}),
            "experience_write_scope": result.get("experience_write_scope", {}),
            "exceptions": result.get("exceptions", []),
            "audit_checks": result.get("audit_checks", {}),
            "dynamic_overrides": result.get("dynamic_overrides", []),
            "missing_inputs": result.get("missing_inputs", []),
        }
        with (self.audit_root / "audit.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _append_private_memory(
        self,
        run_id: str,
        results: list[dict[str, Any]],
        review_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        timestamp = self.now_fn().isoformat()
        updates: list[dict[str, Any]] = []

        system_path = self.project_root / "memory" / "system_mem" / "MEMORY.md"
        system_line = (
            f"- {timestamp} `{run_id}` 系统级经验: pipeline={review_summary['pipeline_id']}; "
            f"success_rate={review_summary['success_rate']}%; "
            f"review_triggers={','.join(review_summary.get('review_triggers', [])) or 'none'}; "
            "写入主体=Hermes 主代理；不包含专家或 Skill 私有正文。\n"
        )
        self._append_memory_line(system_path, "# 系统级经验\n\n", system_line)
        updates.append(
            {
                "layer": "system",
                "owner": "hermes_main_agent",
                "path": str(system_path),
                "write_reason": "运行级全局摘要与复盘触发索引",
                "write_scope": "system_only",
            }
        )

        for expert_id in sorted(self._touched_experts(results)):
            expert_results = [
                result
                for result in results
                if expert_id in [result.get("primary_expert"), *result.get("secondary_experts", [])]
            ]
            skill_usage = sorted(
                {
                    call.get("skill_id")
                    for result in expert_results
                    for call in [
                        *result.get("primary_expert_skill_calls", []),
                        *result.get("secondary_expert_skill_calls", []),
                    ]
                    if call.get("expert_id") == expert_id and call.get("skill_id")
                }
            )
            exceptions = sum(len(result.get("exceptions", [])) for result in expert_results)
            expert_path = self.experts_root / expert_id / "expert_mem" / "MEMORY.md"
            expert_line = (
                f"- {timestamp} `{run_id}` 专家级经验: expert={expert_id}; "
                f"nodes={','.join(result['node_id'] for result in expert_results)}; "
                f"skill_usage={','.join(skill_usage) or 'none'}; "
                f"exceptions={exceptions}; "
                f"human_reviews={sum(1 for result in expert_results if result.get('human_review_required') == '是')}; "
                "写入主体=对应专家；仅记录专家决策、复盘和 Skill 调用摘要。\n"
            )
            self._append_memory_line(expert_path, f"# {expert_id} 私域经验\n\n", expert_line)
            updates.append(
                {
                    "layer": "expert",
                    "owner": expert_id,
                    "path": str(expert_path),
                    "write_reason": "专家决策、复盘结果和 Skill 使用摘要",
                    "write_scope": "expert_only",
                    "skill_usage": skill_usage,
                }
            )

        for skill_id in sorted(self._touched_skills(results)):
            calls = [
                call
                for result in results
                for call in [
                    *result.get("primary_expert_skill_calls", []),
                    *result.get("secondary_expert_skill_calls", []),
                ]
                if call.get("skill_id") == skill_id
            ]
            completed = sum(1 for call in calls if call.get("status") == "completed")
            quality_scores = [float(call.get("output_quality", 0)) for call in calls]
            exceptions = sum(len(call.get("exceptions", [])) for call in calls)
            skill_path = self.skills_root / skill_id / "skill_mem" / "MEMORY.md"
            average_quality = round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else 0.0
            skill_line = (
                f"- {timestamp} `{run_id}` Skill级经验: skill={skill_id}; "
                f"calls={len(calls)}; completed={completed}; "
                f"average_quality={average_quality}; exceptions={exceptions}; "
                "写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。\n"
            )
            self._append_memory_line(skill_path, f"# {skill_id} Skill级经验\n\n", skill_line)
            updates.append(
                {
                    "layer": "skill",
                    "owner": skill_id,
                    "path": str(skill_path),
                    "write_reason": "Skill 执行历史、成功率、异常统计和复盘反馈",
                    "write_scope": "skill_only",
                    "call_count": len(calls),
                    "exception_count": exceptions,
                    "average_output_quality": average_quality,
                }
            )

        self._append_experience_index(run_id, updates)
        return updates

    @staticmethod
    def _append_memory_line(path: Path, header: str, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(header, encoding="utf-8")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _append_experience_index(self, run_id: str, updates: list[dict[str, Any]]) -> None:
        index_path = self.audit_root / "experience_updates.jsonl"
        self.audit_root.mkdir(parents=True, exist_ok=True)
        with index_path.open("a", encoding="utf-8") as handle:
            for update in updates:
                payload = {"run_id": run_id, "timestamp": self.now_fn().isoformat(), **update}
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _touched_experts(results: list[dict[str, Any]]) -> set[str]:
        return {
            expert_id
            for result in results
            for expert_id in [result.get("primary_expert"), *result.get("secondary_experts", [])]
            if expert_id
        }

    @staticmethod
    def _touched_skills(results: list[dict[str, Any]]) -> set[str]:
        return {
            skill_id
            for result in results
            for skill_id in result.get("skills_loaded", [])
        }

    @staticmethod
    def _experience_isolation_policy() -> dict[str, Any]:
        return {
            "system_level": {
                "owner": "Hermes 主代理",
                "write_scope": "系统级经验库",
                "contains": "全局策略、用户偏好、会话记忆、运行级复盘索引",
            },
            "expert_level": {
                "owner": "对应专家",
                "write_scope": "本专家 expert_mem",
                "contains": "专家决策、历史任务、复盘结果、Skill 调用摘要",
            },
            "skill_level": {
                "owner": "对应 Skill",
                "write_scope": "本 Skill skill_mem",
                "contains": "Skill 执行历史、成功率、异常统计、复盘反馈",
            },
            "rule": "允许按规则读取上层经验；写入只限自身层级，不跨层覆盖。",
        }

    @staticmethod
    def _review_triggers(started_at: datetime, results: list[dict[str, Any]]) -> list[str]:
        triggers: list[str] = []
        if started_at.isocalendar().week % 2 == 0:
            triggers.append("biweekly_review")
        if any(result.get("final_output") or result.get("status") == "completed" for result in results):
            triggers.append("key_node_completion")
        if any(result.get("exceptions") for result in results):
            triggers.append("exception_event")
        if any(result.get("dynamic_overrides") for result in results):
            triggers.append("dynamic_override")
        if any(result.get("human_review_required") == "是" for result in results):
            triggers.append("human_intervention")
        return list(dict.fromkeys(triggers))

    @staticmethod
    def _review_period(started_at: datetime) -> str:
        return f"{started_at.date().isoformat()} 至 {started_at.date().isoformat()}"

    @staticmethod
    def _success_rate(results: list[dict[str, Any]]) -> float:
        if not results:
            return 0.0
        completed = sum(1 for result in results if result.get("status") == "completed")
        return round(completed / len(results) * 100, 2)

    @staticmethod
    def _average_output_quality(results: list[dict[str, Any]]) -> float:
        scores = [
            float(call.get("output_quality", 0))
            for result in results
            for call in [
                *result.get("primary_expert_skill_calls", []),
                *result.get("secondary_expert_skill_calls", []),
            ]
        ]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    @staticmethod
    def _skill_usage(results: list[dict[str, Any]]) -> dict[str, int]:
        usage: dict[str, int] = {}
        for result in results:
            for skill_id in result.get("skills_loaded", []):
                usage[skill_id] = usage.get(skill_id, 0) + 1
        return usage

    @staticmethod
    def _rule_update_suggestions(results: list[dict[str, Any]]) -> list[str]:
        suggestions: list[str] = []
        if any(event.get("event") == "competitor_missing" for result in results for event in result.get("exceptions", [])):
            suggestions.append("补充竞品字段枚举或输入约束")
        if any(result.get("human_review_required") == "是" for result in results):
            suggestions.append("复核人工介入触发规则和用户确认口径")
        if any(result.get("dynamic_overrides") for result in results):
            suggestions.append("评估默认 Skill 覆盖范围和权重")
        return suggestions

    @staticmethod
    def _overall_status(results: list[dict[str, Any]]) -> str:
        if any(result.get("status") in {"blocked", "blocked_dependency"} for result in results if not result.get("optional")):
            return "blocked"
        if any(result.get("status") == "failed" for result in results if not result.get("optional")):
            return "failed"
        return "completed"

    def _load_expert(self, expert_id: str) -> dict[str, Any]:
        return self._read_json(self.experts_root / expert_id / "expert.json")

    def _load_skill(self, skill_id: str) -> dict[str, Any]:
        return self._read_json(self.skills_root / skill_id / "skill.json")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Required agent_system file does not exist: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _make_run_id(started_at: datetime, pipeline_id: str) -> str:
        stamp = started_at.strftime("%Y%m%dT%H%M%S")
        safe_pipeline = "".join(ch if ch.isalnum() else "_" for ch in pipeline_id)
        return f"Run_{safe_pipeline}_{stamp}"


def run_agent_system_pipeline(
    *,
    pipeline_id: str,
    input_payload: dict[str, Any] | None = None,
    human_inputs: dict[str, str] | None = None,
    root_dir: str | Path | None = None,
    max_spawn_depth: int = HermesAgentSystemRuntime.DEFAULT_MAX_SPAWN_DEPTH,
) -> dict[str, Any]:
    runtime = HermesAgentSystemRuntime(root_dir=root_dir, max_spawn_depth=max_spawn_depth)
    return runtime.run_pipeline(
        pipeline_id=pipeline_id,
        input_payload=input_payload,
        human_inputs=human_inputs,
    )
