from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from agent_system.builder_dispatcher import maybe_handle_builder_mode
from agent_system.human_approval import AgentSystemApprovalUI
from agent_system.planner import DynamicPipelineSpec, ExpertSelection, PlannerEngine, TaskContext, TaskSpec
from agent_system.runtime import HermesAgentSystemRuntime
from agent_system import capability_readiness as cr

logger = logging.getLogger(__name__)


_AGENT_SYSTEM_MARKERS = (
    "/agent_system",
    "agent_system",
    "hermes agent system",
    "hermes-agent-system",
)

_FEISHU_REPLY_RE = re.compile(r'^\[Replying to:\s*"(.+?)"\]\s*\n?', re.DOTALL)

_INTERNAL_SKILL_CALL_RE = re.compile(
    r'\[Hermes Agent System\]\s+以\s+\S+\s+身份调用\s+Skill\s+'
    r'`?(?P<skill_id>[A-Za-z0-9_-]+)`?，完成节点\s+`?(?P<node_id>[A-Za-z0-9_-]+)`?。',
    re.DOTALL,
)

_PLANNING_LLM_ALLOWED_TASK_TYPES = frozenset({
    "status_lookup",
    "artifact_delivery",
    "doc_format",
    "report_revision",
    "dashboard_from_artifact",
    "voc_analysis",
    "generic",
})

def _parse_internal_skill_call(message: str) -> dict[str, str] | None:
    """Detect internal agent-system skill execution messages.

    Returns {"skill_id": ..., "node_id": ...} when matched, else None.
    These messages must NOT re-enter planning or delegation — doing so causes
    artifact_resolver to recurse until hitting max_spawn_depth.
    """
    m = _INTERNAL_SKILL_CALL_RE.search(message)
    if not m:
        return None
    return {"skill_id": m.group("skill_id"), "node_id": m.group("node_id")}


def _check_skill_pipeline_executable(project_root: Path, skill_id: str) -> str:
    """Return an error reason string if the skill has no runnable pipeline; empty string if OK."""
    pipeline_file = (
        project_root / "skills" / skill_id / "pipeline" / f"{skill_id}_pipeline.json"
    )
    try:
        if not pipeline_file.exists():
            return f"{skill_id} has no executable pipeline or direct implementation"
        data = json.loads(pipeline_file.read_text(encoding="utf-8"))
        steps = data.get("steps") if isinstance(data, dict) else None
        if not steps:
            return f"{skill_id} has no executable pipeline or direct implementation"
        return ""
    except Exception as exc:
        return f"{skill_id} pipeline load error: {exc}"


def check_pipeline_readiness(
    routes_payload: dict,
    pipeline_id: str,
    project_root: "Path | None" = None,
    entrypoint: str = "gateway",
) -> tuple[bool, str]:
    """Delegate to capability_readiness; fall back to routes.json opt-out model if root unavailable."""
    if project_root is not None:
        result = cr.check_pipeline_readiness(
            Path(project_root), routes_payload, pipeline_id, entrypoint
        )
        return (not result.blocking), ("; ".join(result.reasons) if result.blocking else "")
    routes = [
        r for r in routes_payload.get("pipelines", []) if r.get("pipeline_id") == pipeline_id
    ]
    if not routes:
        return False, f"pipeline {pipeline_id!r} not found in routes"
    if any(r.get("production_ready") is False for r in routes):
        return False, f"pipeline {pipeline_id!r} is not production-ready (stub/draft)"
    return True, ""


def _handle_internal_skill_call(
    internal_call: dict[str, str],
    project_root: Path,
    parent_agent: Any,
    task_id: str | None,
    *,
    message: str = "",
    reply_context: str = "",
) -> dict[str, Any]:
    """Return a leaf result for internal skill messages without re-planning or delegating.

    Bypasses all planning, routing, and delegation to prevent recursive depth errors.
    For artifact_resolver: attempts in-process resolution and returns needs_input if
    no artifact reference is found. For other skills: returns unsupported with reason.
    """
    skill_id = internal_call["skill_id"]
    node_id = internal_call["node_id"]

    if skill_id == "artifact_resolver":
        from agent_system.skills.artifact_resolver.resolver import resolve_artifact
        resolved = resolve_artifact(
            message=message,
            reply_context=reply_context,
            project_root=project_root,
        )
        status = resolved.get("status", "needs_input")
        if status == "completed":
            return {
                "final_response": f"[产物定位完成] {resolved['path']} — {resolved['summary']}",
                "agent_system_result": {
                    "status": "completed",
                    "skill_id": skill_id,
                    "node_id": node_id,
                    "path": resolved["path"],
                    "summary": resolved["summary"],
                    "source": resolved["source"],
                    "agent_system_internal_skill_call": True,
                },
                "completed": True,
                "agent_system_status": "completed",
                "interrupted": False,
                "api_calls": 0,
                "model": getattr(parent_agent, "model", None),
                "provider": getattr(parent_agent, "provider", None),
                "task_id": task_id,
            }
        # needs_input — no usable artifact reference available
        reason = resolved.get("reason", "")
        return {
            "final_response": f"[产物定位] needs_input: {reason}",
            "agent_system_result": {
                "status": "needs_input",
                "skill_id": skill_id,
                "node_id": node_id,
                "reason": reason,
                "agent_system_internal_skill_call": True,
            },
            "completed": True,
            "agent_system_status": "needs_input",
            "interrupted": False,
            "api_calls": 0,
            "model": getattr(parent_agent, "model", None),
            "provider": getattr(parent_agent, "provider", None),
            "task_id": task_id,
        }

    # Other skills: check pipeline and return unsupported
    reason = _check_skill_pipeline_executable(project_root, skill_id)
    if not reason:
        reason = f"{skill_id} internal call completed; no re-planning needed"
    return {
        "final_response": f"[内部节点已完成] skill={skill_id} node={node_id}: {reason}",
        "agent_system_result": {
            "status": "unsupported",
            "skill_id": skill_id,
            "node_id": node_id,
            "reason": reason,
            "agent_system_internal_skill_call": True,
        },
        "completed": True,
        "agent_system_status": "unsupported",
        "interrupted": False,
        "api_calls": 0,
        "model": getattr(parent_agent, "model", None),
        "provider": getattr(parent_agent, "provider", None),
        "task_id": task_id,
    }


def _parse_feishu_reply_context(message: str) -> tuple[str, str]:
    """Split Feishu reply prefix out of the current user message."""
    m = _FEISHU_REPLY_RE.match(message)
    if not m:
        return message, ""
    return message[m.end():].lstrip(), m.group(1)

def _requests_agent_system(message: str) -> bool:
    """决定是否触发 agent-system，由动态 planner 的任务关键词兜底判断。"""
    lowered = message.lower()
    if any(marker in lowered for marker in _AGENT_SYSTEM_MARKERS):
        return True

    from agent_system.planner import matches_any_task_keyword

    cleaned, _ = _parse_feishu_reply_context(message)
    return matches_any_task_keyword(cleaned)


def _gstack_phase_gate(phase_id: str, entrypoint: str) -> None:
    """
    Minimal gstack control gate. Returns None (noop) in all default cases.

    Safety contract:
    - disabled (default): immediate return, 2-line noop
    - config missing or any exception: return None (fail-closed)
    - shadow: evaluate + write metric, no output change
    - advisory: evaluate only, advisory note logged but not injected here
    - controlled: requires kill_switch=False + allowlist (MVP: dry_run_only)
    - adapter error: quarantined + logged, Hermes chain continues unchanged
    """
    from agent_system.gstack_control.feature_flags import is_enabled
    if not is_enabled():
        return
    try:
        from agent_system.gstack_control.state_machine import evaluate
        from agent_system.gstack_control.modes import (
            run_shadow, run_advisory, run_controlled, run_quarantined,
        )
        decision = evaluate(phase_id)
        if decision.mode == "disabled":
            return
        elif decision.mode == "shadow":
            run_shadow(phase_id, {"entrypoint": entrypoint})
        elif decision.mode == "advisory":
            run_advisory(phase_id, {"entrypoint": entrypoint})
        elif decision.mode == "controlled":
            run_controlled(phase_id, {"entrypoint": entrypoint})
    except Exception as exc:  # noqa: BLE001
        try:
            from agent_system.gstack_control.modes import run_quarantined
            run_quarantined(phase_id, exc)
        except Exception:  # noqa: BLE001
            pass


def maybe_run_agent_system_from_message(
    user_message: str,
    *,
    parent_agent: Any,
    task_id: str | None = None,
    root_dir: str | Path | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
    reply_context: str = "",
) -> dict[str, Any] | None:
    """Run an agent_system pipeline when a CLI turn explicitly requests it.

    Explicit pipeline_id= in message keeps the old static route path.
    Otherwise PlannerEngine selects the primary expert and builds a dynamic
    pipeline from the current user intent.
    """
    _gstack_phase_gate("gstack.plan_eng_review", "maybe_run_agent_system_from_message")

    if not isinstance(user_message, str):
        return None

    # Guard: internal skill execution messages must never re-enter planning.
    # The message "[Hermes Agent System] 以 system 身份调用 Skill X，完成节点 Y。"
    # contains "hermes agent system" which would otherwise trigger _requests_agent_system,
    # causing artifact_resolver to recurse until hitting max_spawn_depth=3.
    internal_call = _parse_internal_skill_call(user_message)
    if internal_call:
        _root = _find_agent_system_root(root_dir)
        if _root is not None:
            return _handle_internal_skill_call(
                internal_call, _root, parent_agent, task_id,
                message=user_message, reply_context=reply_context,
            )
        return None

    # 深度养马模式优先级最高：在常规 routes 分发之前先看是否处于 / 进入此模式。
    # 它的 short-circuit 不依赖 routes.json，所以放在 root 解析之前。
    project_root = _find_agent_system_root(root_dir)
    if project_root is not None:
        builder_result = maybe_handle_builder_mode(
            user_message,
            parent_agent=parent_agent,
            project_root=project_root,
            task_id=task_id,
            progress_callback=progress_callback,
        )
        if builder_result is not None:
            return builder_result

    if not reply_context:
        user_message, reply_context = _parse_feishu_reply_context(user_message)

    if not _requests_agent_system(user_message):
        return None

    if project_root is None:
        return None

    routes_payload = _read_routes(project_root)
    max_spawn_depth = _configured_max_spawn_depth()
    runtime = HermesAgentSystemRuntime(
        root_dir=project_root,
        skill_executor=_make_delegate_skill_executor(parent_agent),
        human_review_callback=_make_human_review_callback(parent_agent),
        planning_react_callback=_make_planning_react_callback(routes_payload),
        max_spawn_depth=max_spawn_depth,
        progress_callback=progress_callback,
        enforce_skill_readiness=True,
    )
    explicit_pipeline_id = _resolve_explicit_pipeline_id(user_message, routes_payload)
    planning_llm_calls = 0
    if explicit_pipeline_id:
        ready, not_ready_reason = check_pipeline_readiness(
            routes_payload, explicit_pipeline_id, project_root=project_root
        )
        if not ready:
            return _non_executable_route_response(
                explicit_pipeline_id, not_ready_reason, parent_agent, task_id
            )
        result = runtime.run_pipeline(
            pipeline_id=explicit_pipeline_id,
            input_payload=_input_payload_from_message(user_message),
            human_inputs={},
            parallel=True,
        )
    else:
        planning_llm_used = False
        planner = PlannerEngine(project_root, routes_payload)
        ctx = planner.build_task_context(user_message, reply_context=reply_context)
        selection = planner.select_primary_expert(ctx)
        spec = planner.plan_task(ctx, selection)
        pipeline_spec = planner.generate_pipeline(ctx, selection, spec)
        # Readiness gate BEFORE Opus: implicit messages return None, explicit messages return block
        _pre_ready, _pre_reason = check_pipeline_readiness(
            routes_payload, pipeline_spec.pipeline_id, project_root=project_root
        )
        if not _pre_ready:
            _explicit = any(marker in user_message.lower() for marker in _AGENT_SYSTEM_MARKERS)
            if _explicit:
                return _non_executable_route_response(
                    pipeline_spec.pipeline_id, _pre_reason, parent_agent, task_id
                )
            return None
        selection, spec, pipeline_spec, planning_llm_used = _maybe_enhance_initial_plan_with_llm(
            ctx=ctx,
            selection=selection,
            spec=spec,
            pipeline_spec=pipeline_spec,
            routes_payload=routes_payload,
            planner=planner,
            project_root=project_root,
        )
        errors = planner.validate_dynamic_pipeline(pipeline_spec, spec)
        if errors:
            return _planning_failure_response(errors, parent_agent, task_id)
        pipeline_ready, not_ready_reason = check_pipeline_readiness(
            routes_payload, pipeline_spec.pipeline_id, project_root=project_root
        )
        if not pipeline_ready:
            explicit = any(
                marker in user_message.lower() for marker in _AGENT_SYSTEM_MARKERS
            )
            if explicit:
                return _non_executable_route_response(
                    pipeline_spec.pipeline_id, not_ready_reason, parent_agent, task_id
                )
            return None
        result = runtime.run_dynamic_pipeline(
            pipeline_spec=pipeline_spec,
            input_payload=_input_payload_from_message(user_message),
            human_inputs={},
            parallel=True,
        )
        if planning_llm_used and not result.get("planning_llm_calls"):
            planning_llm_calls += 1
    planning_llm_calls += _safe_int(result.get("planning_llm_calls"))
    final_response = _format_final_response(result)
    _auto_sedate_knowledge(result, final_response, parent_agent, task_id)
    return {
        "final_response": final_response,
        "agent_system_result": result,
        "completed": True,
        "agent_system_status": result.get("status"),
        "interrupted": False,
        "api_calls": planning_llm_calls,
        "model": getattr(parent_agent, "model", None),
        "provider": getattr(parent_agent, "provider", None),
        "task_id": task_id,
    }


def _knowledge_toolset_available() -> bool:
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        return "knowledge" in (cfg.get("toolsets") or [])
    except Exception:
        return False


def _get_user_default_product_line_id() -> str:
    try:
        from agent.identity_resolver import resolve_identity, candidate_registry_ids, IdentitySource
        from agent.knowledge_user_registry import KnowledgeUserRegistry
        identity = resolve_identity()
        if identity.source == IdentitySource.UNRESOLVED:
            logger.warning("[knowledge-sedimentation] unresolved identity for platform=%s", identity.platform)
            return ""
        platform = identity.platform if identity.platform not in ("cli", "") else ""
        candidates = candidate_registry_ids(platform, identity.raw_user_id)
        reg = KnowledgeUserRegistry()
        reg.load()
        for uid in candidates:
            ctx = reg.get_user(uid)
            if ctx and ctx.default_product_line_id:
                return ctx.default_product_line_id
        return ""
    except Exception:
        return ""


def _auto_sedate_knowledge(
    result: dict[str, Any],
    final_response: str,
    parent_agent: Any,
    task_id: str | None,
) -> None:
    """Post-pipeline hook: autonomously identify and write reusable business facts.

    Non-blocking — exceptions are caught and logged.  Only runs when:
    - pipeline completed successfully
    - knowledge toolset is configured
    - user has a resolvable default_product_line_id
    - run_id is present (needed for source_uri)
    """
    if result.get("status") != "completed":
        return

    if not _knowledge_toolset_available():
        logger.debug("[knowledge-sedimentation] knowledge toolset not configured — skipping")
        return

    product_line_id = _get_user_default_product_line_id()
    if not product_line_id:
        logger.debug("[knowledge-sedimentation] no default_product_line_id resolved — skipping")
        return

    run_id = result.get("run_id", "")
    source_uri = f"hermes://agent-system/{run_id}" if run_id else ""
    if not source_uri:
        logger.debug("[knowledge-sedimentation] no run_id for source_uri — skipping")
        return

    goal = (
        "你是业务知识提炼专家。请从以下业务分析报告中提取可复用的业务事实。\n\n"
        "规则：\n"
        "1. 只提取有数据支撑、可复用的业务事实（非观点/建议）\n"
        "2. 无值得沉淀的事实时，不写入，直接返回 {\"sedimented\": 0}\n"
        "3. 对每个符合条件的事实调用 knowledge_write，参数：\n"
        f"   product_line_id={product_line_id!r}  source_uri={source_uri!r}\n"
        "   confidence='unverified'（默认；有原文数据支撑的事实）\n"
        "   knowledge_type 从以下选择最合适的值: meeting_conclusion/org_info/product_spec/"
        "project_history/customer_feedback/market_data/compliance/other\n"
        "   finance_flag=false（涉及财务时为 true）\n"
        "   sensitivity_level='internal'  doc_slug=''\n"
        "4. 若 knowledge_write 返回 permission_denied，立即停止，不重试"
    )
    context_data = {
        "pipeline_result_summary": final_response[:3000],
        "run_id": run_id,
        "product_line_id": product_line_id,
        "source_uri": source_uri,
        "sedimentation_mode": True,
    }
    try:
        from tools.delegate_tool import delegate_task
        raw = delegate_task(
            goal=goal,
            context=json.dumps(context_data, ensure_ascii=False, default=str),
            role="leaf",
            parent_agent=parent_agent,
        )
        logger.info("[knowledge-sedimentation] run_id=%s result=%s", run_id, str(raw)[:200])
        try:
            result_data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            if isinstance(result_data, dict) and result_data.get("error") == "permission_denied":
                from agent.pending_capture import write_pending_capture, mark_terminal
                from agent.identity_resolver import resolve_identity
                identity = resolve_identity()
                capture_id = write_pending_capture(
                    title=f"[auto-sedate] {product_line_id}",
                    summary=str(result_data)[:500],
                    candidate_type="knowledge",
                    scope_id=product_line_id,
                    source_uri=source_uri,
                    confidence="unverified",
                    missing_fields=[],
                    failure_reason=result_data.get("reason", "permission_denied"),
                    session_id=run_id,
                    user_id=identity.user_id,
                    platform=identity.platform,
                    suggested_next_action=result_data.get("next_action", ""),
                )
                mark_terminal(capture_id, "pending_created")
                try:
                    from agent import sedimentation_metrics
                    sedimentation_metrics.increment("knowledge_write_failed")
                except Exception:
                    pass
                logger.warning("[knowledge-sedimentation] permission_denied → pending capture written")
                try:
                    from agent.memory_event import create_event
                    from agent.memory_dispatcher import dispatch_event
                    evt = create_event(
                        source_type="tool_result",
                        source_uri=source_uri,
                        actor_user_id=identity.user_id,
                        subject=f"auto_sedate permission_denied: {product_line_id}",
                        risk_flags=["permission_unclear", "tool_failure"],
                        recommended_destination="staging",
                        session_id=run_id,
                        product_line_hint=product_line_id,
                    )
                    dispatch_event(evt)
                except Exception as sed_exc:
                    logger.debug("[knowledge-sedimentation] dispatch non-fatal: %s", sed_exc)
        except Exception as check_exc:
            logger.debug("[knowledge-sedimentation] result check non-fatal: %s", check_exc)
    except Exception as exc:
        logger.warning("[knowledge-sedimentation] non-blocking error: %s", exc)


def _find_agent_system_root(root_dir: str | Path | None) -> Path | None:
    candidates: list[Path] = []
    if root_dir is not None:
        candidates.append(Path(root_dir))
    env_cwd = os.getenv("TERMINAL_CWD")
    if env_cwd:
        candidates.extend([Path(env_cwd), Path(env_cwd) / "agent_system"])
    cwd = Path.cwd()
    candidates.extend([cwd, cwd / "agent_system", Path(__file__).resolve().parent])
    for candidate in candidates:
        if (candidate / "scheduler" / "main_scheduler" / "routes.json").exists():
            return candidate
    return None


def _read_routes(project_root: Path) -> dict[str, Any]:
    routes_path = project_root / "scheduler" / "main_scheduler" / "routes.json"
    return json.loads(routes_path.read_text(encoding="utf-8"))


def _resolve_explicit_pipeline_id(message: str, routes_payload: dict[str, Any]) -> str | None:
    """Resolve only explicit pipeline references, not fuzzy task keywords."""
    explicit = re.search(
        r"(?:pipeline_id|pipeline|flow_id|flow)\s*[:=]\s*([A-Za-z0-9_.-]+)",
        message,
    )
    pipelines = routes_payload.get("pipelines", [])
    pipeline_ids = {
        str(route.get("pipeline_id"))
        for route in pipelines
        if route.get("pipeline_id")
    }
    if explicit and explicit.group(1) in pipeline_ids:
        return explicit.group(1)
    for pipeline_id in sorted(pipeline_ids, key=len, reverse=True):
        if pipeline_id in message:
            return pipeline_id

    return None


def _planning_failure_response(
    errors: list[str],
    parent_agent: Any,
    task_id: str | None,
) -> dict[str, Any]:
    detail = "; ".join(errors)
    return {
        "final_response": f"[agent-system] 规划校验失败，任务未执行。\n{detail}",
        "agent_system_result": {"status": "planning_failed", "errors": errors},
        "completed": False,
        "agent_system_status": "planning_failed",
        "interrupted": False,
        "api_calls": 0,
        "model": getattr(parent_agent, "model", None),
        "provider": getattr(parent_agent, "provider", None),
        "task_id": task_id,
    }


def _non_executable_route_response(
    pipeline_id: str,
    reason: str,
    parent_agent: Any,
    task_id: str | None,
) -> dict[str, Any]:
    return {
        "final_response": (
            f"[agent-system] 流程 {pipeline_id!r} 尚未就绪（stub/draft），任务未执行。\n{reason}"
        ),
        "agent_system_result": {"status": "blocked", "pipeline_id": pipeline_id, "reason": reason},
        "completed": False,
        "agent_system_status": "blocked",
        "interrupted": False,
        "api_calls": 0,
        "model": getattr(parent_agent, "model", None),
        "provider": getattr(parent_agent, "provider", None),
        "task_id": task_id,
    }


def _configured_max_spawn_depth() -> int:
    try:
        from tools.delegate_tool import _get_max_spawn_depth

        return _get_max_spawn_depth()
    except Exception:
        return HermesAgentSystemRuntime.DEFAULT_MAX_SPAWN_DEPTH


def _input_payload_from_message(message: str) -> dict[str, Any]:
    return {
        "source_materials": [message],
        "business_tags": ["cli_auto_trigger", "agent_system"],
        "output_format": "report",
    }


def _planning_llm_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
    except Exception:
        return {"enabled": False}

    agent_system_cfg = cfg.get("agent_system", {}) if isinstance(cfg, dict) else {}
    planning_llm = agent_system_cfg.get("planning_llm", {}) if isinstance(agent_system_cfg, dict) else {}
    models = agent_system_cfg.get("models", {}) if isinstance(agent_system_cfg, dict) else {}
    planning_model = models.get("planning", {}) if isinstance(models, dict) else {}

    if not isinstance(planning_llm, dict):
        planning_llm = {}
    if not isinstance(planning_model, dict):
        planning_model = {}

    enabled = bool(planning_llm.get("enabled"))
    provider = str(planning_llm.get("provider") or planning_model.get("provider") or "").strip()
    model = str(planning_llm.get("model") or planning_model.get("model") or "").strip()
    return {
        "enabled": enabled and bool(provider and model),
        "provider": provider,
        "model": model,
        "max_prompt_tokens": _safe_int(planning_llm.get("max_prompt_tokens")) or 12000,
        "max_output_tokens": _safe_int(planning_llm.get("max_output_tokens")) or 1200,
        "timeout": float(planning_llm.get("timeout") or 120),
    }


def _truncate_text(value: Any, max_chars: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


def _route_candidates(
    routes_payload: dict[str, Any],
    *,
    limit: int = 24,
    project_root: "Path | None" = None,
) -> list[dict[str, Any]]:
    if project_root is not None:
        candidates = cr.ready_route_candidates(
            Path(project_root), routes_payload, entrypoint="gateway"
        )
        return candidates[:limit]
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
    non_ready = {
        str(r.get("pipeline_id") or "")
        for r in routes_payload.get("pipelines", [])
        if r.get("production_ready") is False
    }
    grouped = {pid: entry for pid, entry in grouped.items() if pid not in non_ready}
    return list(grouped.values())[:limit]


def _extract_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        return {}
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _call_planning_llm(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = _planning_llm_config()
    if not config.get("enabled"):
        return {"llm_used": False, "stage": stage, "reason": "planning_llm_disabled"}

    prompt_budget_chars = max(2000, int(config["max_prompt_tokens"]) * 4)
    compact_payload = _truncate_text(payload, prompt_budget_chars)
    system_prompt = (
        "你是 Hermes agent-system 的规划控制器。只做规划判断，不执行任务、不写最终业务报告、"
        "不调用工具。你必须输出严格 JSON。"
    )
    user_prompt = (
        f"阶段: {stage}\n"
        "请基于下方受限上下文输出规划决定。不要假设有完整历史；不要要求执行模型改用 Opus。\n"
        "JSON schema:\n"
        "{\n"
        '  "accept_local_plan": true,\n'
        '  "pipeline_id": "string|null",\n'
        '  "task_type": "status_lookup|artifact_delivery|doc_format|report_revision|dashboard_from_artifact|voc_analysis|generic|null",\n'
        '  "task_goal": "string",\n'
        '  "expected_output": "string",\n'
        '  "requires_voc_insight": false,\n'
        '  "react_decision": "continue|retry|repair|ask_human|block|none",\n'
        '  "next_actions": ["string"],\n'
        '  "risk_flags": ["string"],\n'
        '  "reason": "string"\n'
        "}\n\n"
        f"受限上下文:\n{compact_payload}"
    )
    try:
        from agent.auxiliary_client import call_llm

        response = call_llm(
            provider=config["provider"],
            model=config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=int(config["max_output_tokens"]),
            timeout=float(config["timeout"]),
        )
        content = response.choices[0].message.content
        decision = _extract_json_object(content)
        decision.update(
            {
                "llm_used": True,
                "stage": stage,
                "provider": config["provider"],
                "model": config["model"],
            }
        )
        logger.info(
            "[agent-system] planning_llm stage=%s model=%s provider=%s",
            stage,
            config["model"],
            config["provider"],
        )
        return decision
    except Exception as exc:
        logger.warning("[agent-system] planning_llm stage=%s failed: %s", stage, exc)
        return {
            "llm_used": False,
            "stage": stage,
            "provider": config.get("provider"),
            "model": config.get("model"),
            "error": str(exc),
        }


def _pipeline_spec_for_pipeline_id(
    planner: PlannerEngine,
    routes_payload: dict[str, Any],
    pipeline_id: str,
    ctx: TaskContext,
    selection: ExpertSelection,
    spec: TaskSpec,
    llm_decision: dict[str, Any],
) -> DynamicPipelineSpec | None:
    routes = [r for r in routes_payload.get("pipelines", []) if r.get("pipeline_id") == pipeline_id]
    if not routes:
        return None
    nodes = [planner._route_to_spec_node(route) for route in routes]  # intentional bounded reuse
    if not nodes:
        return None
    return DynamicPipelineSpec(
        pipeline_id=pipeline_id,
        pipeline_name=planner._template_name(pipeline_id),
        generated_by_primary_expert=selection.primary_expert_id,
        planning_source="planning_llm_template_override",
        nodes=nodes,
        final_output_node=nodes[-1].node_id,
        template_candidate=False,
        skipped_voc_insight_reason=spec.rejection_reason_for_voc_insight if not spec.requires_voc_insight else "",
        task_context_summary=ctx.current_user_message[:120],
        expert_selection=asdict(selection),
        task_spec=asdict(spec),
        planning_llm=llm_decision,
    )


def _maybe_enhance_initial_plan_with_llm(
    *,
    ctx: TaskContext,
    selection: ExpertSelection,
    spec: TaskSpec,
    pipeline_spec: DynamicPipelineSpec,
    routes_payload: dict[str, Any],
    planner: PlannerEngine,
    project_root: "Path | None" = None,
) -> tuple[ExpertSelection, TaskSpec, DynamicPipelineSpec, bool]:
    payload = {
        "user_intent": _truncate_text(ctx.current_user_message, 4000),
        "reply_context_summary": _truncate_text(ctx.reply_context, 1500),
        "available_experts": ctx.available_experts,
        "available_skills": ctx.available_skills,
        "route_candidates": _route_candidates(routes_payload, project_root=project_root),
        "local_plan": {
            "expert_selection": asdict(selection),
            "task_spec": asdict(spec),
            "pipeline_spec": asdict(pipeline_spec),
        },
    }
    decision = _call_planning_llm("initial_plan", payload)
    if not decision.get("llm_used"):
        return selection, spec, pipeline_spec, False

    updates: dict[str, Any] = {}
    task_type = str(decision.get("task_type") or "").strip()
    if task_type in _PLANNING_LLM_ALLOWED_TASK_TYPES:
        updates["task_type"] = task_type
    for key in ("task_goal", "expected_output"):
        value = decision.get(key)
        if isinstance(value, str) and value.strip():
            updates[key] = value.strip()[:500]
    if isinstance(decision.get("requires_voc_insight"), bool):
        updates["requires_voc_insight"] = bool(decision["requires_voc_insight"])
    if updates:
        spec = replace(spec, **updates)

    pipeline_id = str(decision.get("pipeline_id") or "").strip()
    llm_pipeline = (
        _pipeline_spec_for_pipeline_id(planner, routes_payload, pipeline_id, ctx, selection, spec, decision)
        if pipeline_id and pipeline_id != pipeline_spec.pipeline_id
        else None
    )
    if llm_pipeline is not None:
        pipeline_spec = llm_pipeline
    else:
        pipeline_spec = replace(
            pipeline_spec,
            planning_source=f"{pipeline_spec.planning_source}+planning_llm",
            expert_selection=asdict(selection),
            task_spec=asdict(spec),
            planning_llm=decision,
        )
    return selection, spec, pipeline_spec, True


def _summarize_node_results_for_planning(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for result in results[:20]:
        output = result.get("output") if isinstance(result, dict) else {}
        summary.append(
            {
                "node_id": result.get("node_id"),
                "status": result.get("status"),
                "final_output": bool(result.get("final_output")),
                "exceptions": result.get("exceptions", [])[:5],
                "audit_checks": result.get("audit_checks", {}),
                "result_summary": _truncate_text((output or {}).get("result_summary", ""), 900)
                if isinstance(output, dict)
                else "",
            }
        )
    return summary


def _make_planning_react_callback(routes_payload: dict[str, Any]):
    def _callback(payload: dict[str, Any]) -> dict[str, Any]:
        stage = str(payload.get("stage") or "post_audit_react")
        limited_payload = {
            "pipeline_id": payload.get("pipeline_id"),
            "status": payload.get("status"),
            "review_summary": payload.get("review_summary", {}),
            "planning_meta": payload.get("planning_meta", {}),
            "node_results_summary": _summarize_node_results_for_planning(payload.get("results", [])),
            "route_candidates": _route_candidates(routes_payload),
        }
        decision = _call_planning_llm(stage, limited_payload)
        if not decision.get("llm_used"):
            return decision
        allowed = {"continue", "retry", "repair", "ask_human", "block", "none"}
        react_decision = str(decision.get("react_decision") or "none").strip()
        if react_decision not in allowed:
            decision["react_decision"] = "none"
        return decision

    return _callback


def _make_human_review_callback(parent_agent: Any):
    clarify_callback = getattr(parent_agent, "clarify_callback", None)
    if clarify_callback is None:
        return None
    approval_ui = AgentSystemApprovalUI(clarify_callback)
    return approval_ui.request


# Node name substrings that indicate audit/review phase (not execution).
_AUDIT_NODE_PATTERNS = frozenset({
    "briefing", "audit", "review", "quality_gate",
    "completion_report", "retrospective", "debrief", "summary_report",
})


def _classify_node_phase(node_id: str) -> str:
    """Return 'audit' for briefing/audit/review/quality_gate nodes, 'execution' otherwise."""
    lower = (node_id or "").lower()
    for pat in _AUDIT_NODE_PATTERNS:
        if pat in lower:
            return "audit"
    return "execution"


def _resolve_all_phase_models() -> dict[str, dict[str, str]]:
    """Read agent_system.models.{planning,execution,audit} from config.

    Falls back to delegation.provider/model for execution and audit when
    agent_system.models is not structured.  Returns a dict keyed by phase name,
    each value a dict with 'provider' and 'model'.
    """
    try:
        from hermes_cli.config import load_config
        full_cfg = load_config()
        asm = full_cfg.get("agent_system", {}).get("models", {})
        delegation = full_cfg.get("delegation", {})
        del_provider = str(delegation.get("provider") or "").strip()
        del_model = str(delegation.get("model") or "").strip()

        def _entry(phase_cfg: object, fallback_provider: str, fallback_model: str) -> dict[str, str]:
            if isinstance(phase_cfg, dict):
                return {
                    "provider": str(phase_cfg.get("provider") or fallback_provider).strip(),
                    "model": str(phase_cfg.get("model") or fallback_model).strip(),
                }
            return {"provider": fallback_provider, "model": fallback_model}

        return {
            "planning": _entry(asm.get("planning"), "", ""),
            "execution": _entry(asm.get("execution"), del_provider, del_model),
            "audit": _entry(asm.get("audit"), del_provider, del_model),
        }
    except Exception:
        return {
            "planning": {"provider": "", "model": ""},
            "execution": {"provider": "", "model": ""},
            "audit": {"provider": "", "model": ""},
        }


def _make_delegate_skill_executor(parent_agent: Any):
    phases = _resolve_all_phase_models()
    parent_model = getattr(parent_agent, "model", "unknown")
    exec_info = phases["execution"]
    audit_info = phases["audit"]
    exec_provider = exec_info["provider"]
    exec_model = exec_info["model"]
    audit_provider = audit_info["provider"]
    audit_model = audit_info["model"]
    planning_llm = _planning_llm_config()
    planning_label = (
        f"{planning_llm['model']} via {planning_llm['provider']} (initial/react)"
        if planning_llm.get("enabled")
        else "local planner"
    )

    # Fail-closed: warn loudly if execution/audit would fall back to Kimi
    for phase_name, p, m in [("execution", exec_provider, exec_model), ("audit", audit_provider, audit_model)]:
        if m == "kimi-for-coding" or p == "kimi-coding":
            logger.error(
                "[agent-system] ROUTING ERROR: %s phase resolved to kimi-for-coding — "
                "this is not the target model. Check agent_system.models.%s and delegation.* "
                "in config.yaml. Nodes will fail rather than silently use Kimi.",
                phase_name, phase_name,
            )

    if exec_provider and exec_model:
        logger.info(
            "[agent-system] model routing: planning=%s, execution=%s via %s, audit=%s via %s",
            planning_label, exec_model, exec_provider, audit_model, audit_provider,
        )
    else:
        logger.warning(
            "[agent-system] delegation.provider/model not configured — "
            "execution nodes will inherit parent model=%s (claude cost). "
            "Set delegation.provider and delegation.model in config.yaml.",
            parent_model,
        )

    def _executor(context: dict[str, Any]) -> dict[str, Any]:
        package = context["task_package"]
        delegate_meta = package.get("delegate_task") or {}
        credential_probe = _online_agent_probe(parent_agent)
        node_id = package.get("node_id", "unknown")
        phase = _classify_node_phase(node_id)
        node_provider = audit_provider if phase == "audit" else exec_provider
        node_model = audit_model if phase == "audit" else exec_model

        # Fail-closed on Kimi: refuse to proceed rather than silently degrade
        if node_model == "kimi-for-coding" or node_provider == "kimi-coding":
            return _delegate_failure(
                context,
                f"[agent-system] ROUTING FAIL-CLOSED: node={node_id} phase={phase} "
                f"resolved to kimi-for-coding (provider={node_provider}). "
                f"Configure agent_system.models.{phase} with openai-codex/gpt-5.5 in config.yaml. "
                f"Kimi is not allowed as a default execution model.",
            )

        if node_provider and node_model:
            logger.info(
                "[agent-system] node=%s phase=%s executing with model=%s provider=%s",
                node_id, phase, node_model, node_provider,
            )
        else:
            logger.warning(
                "[agent-system] node=%s falling back to parent model=%s "
                "(reason: delegation.provider/model not configured in config.yaml)",
                node_id, parent_model,
            )

        goal = (
            f"[Hermes Agent System] 以 {context.get('expert_id') or 'system'} "
            f"身份调用 Skill `{context['skill_id']}`，完成节点 `{package['node_id']}`。"
        )
        delegate_context = {
            "task_package": package,
            "expert_role": context.get("expert_role"),
            "expert_id": context.get("expert_id"),
            "skill_id": context.get("skill_id"),
            "requested_skill_id": context.get("requested_skill_id"),
            "skill": context.get("skill"),
            "input_payload": context.get("input_payload"),
            "prior_results": context.get("prior_results"),
            "execution_rules": {
                "use_real_skill_or_agent": True,
                "production_llm_required": True,
                "return_structured_summary": True,
                "respect_dag_node_scope": True,
                "max_spawn_depth": context.get("max_spawn_depth"),
            },
            "online_agent_probe": credential_probe,
        }
        try:
            from tools.delegate_tool import delegate_task

            raw = delegate_task(
                goal=goal,
                context=json.dumps(delegate_context, ensure_ascii=False, default=str),
                role=delegate_meta.get("role", "leaf"),
                parent_agent=parent_agent,
                override_provider=node_provider or None,
                override_model=node_model or None,
            )
        except Exception as exc:
            return _delegate_failure(context, f"delegate_task 调用失败：{exc}")

        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return _delegate_failure(context, f"delegate_task 返回不可解析：{raw}")

        if payload.get("error"):
            return _delegate_failure(context, str(payload["error"]))

        child_results = payload.get("results") or []
        first = child_results[0] if child_results and isinstance(child_results[0], dict) else {}
        child_status = str(first.get("status") or "failed")
        completed = child_status == "completed"
        summary = str(first.get("summary") or first.get("error") or "")
        api_calls = _safe_int(first.get("api_calls"))
        from agent_system.output_selector import extract_report_path
        main_report_path = extract_report_path(summary)
        return {
            "status": "completed" if completed else "failed",
            "output_quality": 90 if completed else 30,
            "execution_mode": "production_delegate_task",
            "output": {
                "result_summary": summary or f"{context['skill_id']} 已通过 delegate_task 执行",
                "main_report_path": main_report_path,
                "skill_id": context["skill_id"],
                "expert_id": context.get("expert_id"),
                "delegate_status": child_status,
                "delegate_results": child_results,
                "real_skill_execution": True,
                "production_llm_required": True,
                "online_agent_probe": credential_probe,
                "online_llm_api_calls": api_calls,
            },
            "audit_checks": {
                "real_delegate_task_executed": True,
                "production_llm_required": True,
                "online_llm_call_observed": api_calls > 0,
                "online_agent_credential_available": credential_probe["credential_status"] != "missing",
                "delegate_role": delegate_meta.get("role", "leaf"),
                "max_spawn_depth": context.get("max_spawn_depth"),
            },
            "exceptions": [] if completed else [
                {
                    "event": "skill_execution_failed",
                    "trigger": summary or child_status,
                    "handling": "记录失败并进入复盘",
                    "blocking": True,
                    "audit_field": "skill_execution",
                    "review_trigger": True,
                }
            ],
        }

    return _executor


def _delegate_failure(context: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "output_quality": 0,
        "execution_mode": "production_delegate_task_failed",
        "output": {
            "result_summary": message,
            "skill_id": context.get("skill_id"),
            "expert_id": context.get("expert_id"),
            "real_skill_execution": False,
            "production_llm_required": True,
        },
        "exceptions": [
            {
                "event": "skill_execution_failed",
                "trigger": message,
                "handling": "记录失败并进入复盘",
                "blocking": True,
                "audit_field": "skill_execution",
                "review_trigger": True,
            }
        ],
        "audit_checks": {
            "real_delegate_task_executed": False,
            "production_llm_required": True,
            "online_llm_call_observed": False,
        },
    }


def _online_agent_probe(parent_agent: Any) -> dict[str, Any]:
    client_kwargs = getattr(parent_agent, "_client_kwargs", {}) or {}
    has_direct_key = bool(
        getattr(parent_agent, "api_key", None)
        or client_kwargs.get("api_key")
    )
    has_pool = bool(getattr(parent_agent, "_credential_pool", None))
    has_base_url = bool(
        getattr(parent_agent, "base_url", None)
        or client_kwargs.get("base_url")
    )
    if has_direct_key:
        credential_status = "direct_key_available"
    elif has_pool:
        credential_status = "credential_pool_available"
    else:
        credential_status = "missing"
    return {
        "credential_status": credential_status,
        "base_url_configured": has_base_url,
        "provider": getattr(parent_agent, "provider", None),
        "model": getattr(parent_agent, "model", None),
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_run_started_ts(run_id: str) -> float | None:
    """Parse the UTC timestamp from a run_id like 'Run_insight_flow_20260510T123456'."""
    m = re.search(r'(\d{8}T\d{6})$', run_id or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").timestamp()
    except ValueError:
        return None


def _format_final_response(result: dict[str, Any]) -> str:
    """Format the final response - content first, minimal system info only when needed."""
    react_plan = result.get("react_plan") or {}
    if str(react_plan.get("react_decision") or "").strip() == "block":
        reason = str(react_plan.get("reason") or "审计/react 阻断").strip()
        return f"[agent-system] 执行被审计阻断。\n\n原因：{reason}"

    lines = []
    status = result.get("status")

    # Derive run start timestamp to filter out stale output files from previous runs.
    run_started_ts = _parse_run_started_ts(result.get("run_id", ""))

    # Step 1: 收集所有可能的输出内容（包括部分完成的）
    skill_output_dirs: dict[str, Path] = {}
    skill_roots: dict[str, Path] = {}
    failed_nodes = []
    completed_nodes = []

    for item in result.get("results", []):
        node_id = item.get("node_id")
        node_status = item.get("status")
        skills_loaded = item.get("skills_loaded", [])
        is_final = item.get("final_output", False)

        # 记录节点状态
        if node_status == "completed":
            completed_nodes.append(node_id)
        elif node_status in ["failed", "optional_failed"]:
            failed_nodes.append(node_id)

        # 收集输出（包括部分完成的节点）
        if skills_loaded and (is_final or node_status == "completed"):
            for skill_id in skills_loaded:
                if skill_id not in skill_output_dirs:
                    skill_root = _find_skill_root(skill_id, result)
                    if skill_root and skill_root.exists():
                        output_dir = skill_root / "output"
                        if output_dir.exists():
                            skill_output_dirs[skill_id] = output_dir
                            skill_roots[skill_id] = skill_root

    # Step 2: 输出内容
    content_found = False

    # 2a. 优先使用子 Agent 明确返回的 main_report_path（避免 stale 文件 bug）
    for item in result.get("results", []):
        p = (item.get("output") or {}).get("main_report_path")
        if p and Path(p).is_file():
            try:
                content = Path(p).read_text(encoding="utf-8")
                # 检查云文档失败信号并前置提示
                summary_text = (item.get("output") or {}).get("result_summary", "")
                if "云文档" in summary_text and any(
                    w in summary_text for w in ("失败", "无法", "不支持")
                ):
                    lines.append(f"> ⚠️ 云文档创建失败：{summary_text}")
                    lines.append("")
                lines.append(content[:30000])
                lines.append("")
                content_found = True
            except Exception:
                pass
            break

    # 2b. 次选：skill output 目录，用 output_selector 分类（跳过执行记录）
    if not content_found and skill_output_dirs:
        from agent_system.output_selector import select_output_files
        deliverable_files, log_files = select_output_files(skill_output_dirs, skill_roots)
        # Apply run-start timestamp filter when available (stale file guard).
        def _filter_by_ts(files: list[Path]) -> list[Path]:
            if run_started_ts is None:
                return files
            filtered = [f for f in files if f.stat().st_mtime >= run_started_ts - 10]
            return filtered if filtered else files  # fall back to all if filter removes everything

        deliverable_files = _filter_by_ts(deliverable_files)
        log_files = _filter_by_ts(log_files)
        target_files = deliverable_files or log_files
        is_fallback = bool(log_files and not deliverable_files)
        for f in target_files[:1]:
            try:
                content = f.read_text(encoding="utf-8")
                if is_fallback:
                    lines.append("> ⚠️ 未找到用户报告，以下为执行记录（仅供参考）")
                    lines.append("")
                if len(content) > 30000:
                    content = content[:30000] + "\n\n... (内容过长，已截断)"
                lines.append(content)
                lines.append("")
                content_found = True
            except Exception:
                pass

    # Step 3: 根据状态添加必要的提示
    if status == "failed":
        if content_found:
            # 有部分结果，说明哪些节点失败了
            lines.append("---")
            lines.append("")
            lines.append("⚠️ **执行未完全完成**")
            lines.append("")
            if completed_nodes:
                lines.append(f"✅ 已完成: {', '.join(completed_nodes)}")
            if failed_nodes:
                lines.append(f"❌ 失败: {', '.join(failed_nodes)}")
            lines.append("")
            lines.append("**下一步**:")
            lines.append("1. 查看审计日志了解失败原因")
            lines.append("2. 修复问题后重试")
            lines.append("")
            lines.append(f"审计日志: `{result.get('audit_log')}`")
        else:
            # 没有任何结果
            lines.append("❌ **执行失败，未生成输出**")
            lines.append("")
            if failed_nodes:
                lines.append(f"失败节点: {', '.join(failed_nodes)}")
            lines.append("")
            lines.append("**下一步**:")
            lines.append("1. 查看审计日志了解失败原因")
            lines.append("2. 修复问题后重试")
            lines.append("")
            lines.append(f"审计日志: `{result.get('audit_log')}`")

    elif status == "completed" and not content_found:
        # 完成但没有输出
        lines.append("⚠️ **执行完成，但未找到输出内容**")
        lines.append("")
        lines.append("可能原因:")
        lines.append("1. 节点未标记 final_output=True")
        lines.append("2. Skill 未生成输出文件")
        lines.append("")
        lines.append(f"审计日志: `{result.get('audit_log')}`")

    return "\n".join(lines)



def _find_skill_root(skill_id: str, result: dict[str, Any]) -> Path | None:
    """Find the skill root directory based on skill_id and result context."""
    # Try to find from audit_log path
    audit_log = result.get("audit_log", "")
    if audit_log:
        audit_path = Path(audit_log)
        # Navigate from audit/audit.jsonl to skills/{skill_id}
        skill_root = audit_path.parent.parent / "skills" / skill_id
        if skill_root.exists():
            return skill_root

    # Fallback: search in common locations
    common_roots = [
        Path(__file__).parent.parent / "skills" / skill_id,
        Path("/Users/frank/.hermes/hermes-agent-official/agent_system/skills") / skill_id,
    ]

    for root in common_roots:
        if root.exists():
            return root

    return None
