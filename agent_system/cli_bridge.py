from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from agent_system.human_approval import AgentSystemApprovalUI
from agent_system.planner import PlannerEngine
from agent_system.runtime import HermesAgentSystemRuntime

logger = logging.getLogger(__name__)


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
    agent_system.models is not structured.
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


_FEISHU_REPLY_RE = re.compile(r'^\[Replying to:\s*"(.+?)"\]\s*\n?', re.DOTALL)


def _parse_feishu_reply_context(message: str) -> tuple[str, str]:
    """Split '[Replying to: "..."]' Feishu prefix out of message.

    Returns (current_user_message, reply_context).  When no prefix is present
    both values are returned as-is / empty string.
    """
    m = _FEISHU_REPLY_RE.match(message)
    if not m:
        return message, ""
    return message[m.end():].lstrip(), m.group(1)


_AGENT_SYSTEM_MARKERS = (
    "/agent_system",
    "agent_system",
    "hermes agent system",
    "hermes-agent-system",
)


def maybe_run_agent_system_from_message(
    user_message: str,
    *,
    parent_agent: Any,
    task_id: str | None = None,
    root_dir: str | Path | None = None,
    reply_context: str = "",
) -> dict[str, Any] | None:
    """Run an agent_system pipeline when a CLI turn explicitly requests it.

    Explicit pipeline_id= in message → backward-compatible static route.
    Otherwise → PlannerEngine selects primary expert, builds TaskSpec and
    DynamicPipelineSpec, validates VOC guard, then runs the dynamic pipeline.
    """

    if not isinstance(user_message, str) or not _requests_agent_system(user_message):
        return None

    # Strip Feishu [Replying to: "..."] prefix so it doesn't pollute intent detection.
    if not reply_context:
        user_message, reply_context = _parse_feishu_reply_context(user_message)

    project_root = _find_agent_system_root(root_dir)
    if project_root is None:
        return None

    routes_payload = _read_routes(project_root)
    max_spawn_depth = _configured_max_spawn_depth()
    runtime = HermesAgentSystemRuntime(
        root_dir=project_root,
        skill_executor=_make_delegate_skill_executor(parent_agent),
        human_review_callback=_make_human_review_callback(parent_agent),
        max_spawn_depth=max_spawn_depth,
    )

    explicit_pipeline_id = _resolve_explicit_pipeline_id(user_message, routes_payload)
    if explicit_pipeline_id:
        result = runtime.run_pipeline(
            pipeline_id=explicit_pipeline_id,
            input_payload=_input_payload_from_message(user_message),
            human_inputs={},
            parallel=True,
        )
    else:
        planner = PlannerEngine(project_root, routes_payload)
        ctx = planner.build_task_context(user_message, reply_context=reply_context)
        selection = planner.select_primary_expert(ctx)
        spec = planner.plan_task(ctx, selection)
        pipeline_spec = planner.generate_pipeline(ctx, selection, spec)
        errors = planner.validate_dynamic_pipeline(pipeline_spec, spec)
        if errors:
            return _planning_failure_response(errors, parent_agent, task_id)
        result = runtime.run_dynamic_pipeline(
            pipeline_spec=pipeline_spec,
            input_payload=_input_payload_from_message(user_message),
            human_inputs={},
            parallel=True,
        )

    final_response = _format_final_response(result)
    _auto_sedate_knowledge(result, final_response, parent_agent, task_id)
    return {
        "final_response": final_response,
        "agent_system_result": result,
        "completed": True,
        "agent_system_status": result.get("status"),
        "interrupted": False,
        "api_calls": 0,
        "model": getattr(parent_agent, "model", None),
        "provider": getattr(parent_agent, "provider", None),
        "task_id": task_id,
    }


def _requests_agent_system(message: str) -> bool:
    from agent_system.planner import matches_any_task_keyword
    lowered = message.lower()
    if any(marker in lowered for marker in _AGENT_SYSTEM_MARKERS):
        return True
    # Strip Feishu reply prefix before keyword check so quoted context
    # (e.g. "[Replying to: \"用户洞察...\"]") doesn't falsely trigger.
    cleaned, _ = _parse_feishu_reply_context(message)
    return matches_any_task_keyword(cleaned)


def _knowledge_toolset_available() -> bool:
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        return "knowledge" in (cfg.get("toolsets") or [])
    except Exception:
        return False


def _get_user_default_product_line_id() -> str:
    try:
        import getpass
        profile = os.getenv("HERMES_PROFILE", "default")
        user_id = f"cli:{getpass.getuser()}:{profile}"
        from agent.knowledge_user_registry import KnowledgeUserRegistry
        reg = KnowledgeUserRegistry()
        reg.load()
        ctx = reg.get_user(user_id)
        return ctx.default_product_line_id if ctx else ""
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
        "   confidence='high'（数据直接支撑）或 'medium'（推断结论）\n"
        "   knowledge_type='business_fact'  finance_flag=false（涉及财务时为 true）\n"
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
    """Return a pipeline_id only when the message contains an explicit reference.

    Accepts `pipeline_id=foo`, `pipeline=foo`, or the bare pipeline_id token
    appearing literally in the message.  Does NOT do keyword/name fuzzy matching
    so that ordinary business requests are not accidentally routed here.
    """
    explicit = re.search(
        r"(?:pipeline_id|pipeline|flow_id|flow)\s*[:=]\s*([A-Za-z0-9_.-]+)",
        message,
    )
    pipeline_ids = {
        str(route.get("pipeline_id"))
        for route in routes_payload.get("pipelines", [])
        if route.get("pipeline_id")
    }
    if explicit and explicit.group(1) in pipeline_ids:
        return explicit.group(1)
    for pid in sorted(pipeline_ids, key=len, reverse=True):
        if pid in message:
            return pid
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


def _make_human_review_callback(parent_agent: Any):
    clarify_callback = getattr(parent_agent, "clarify_callback", None)
    if clarify_callback is None:
        return None
    approval_ui = AgentSystemApprovalUI(clarify_callback)
    return approval_ui.request


def _make_delegate_skill_executor(parent_agent: Any):
    phases = _resolve_all_phase_models()
    parent_model = getattr(parent_agent, "model", "unknown")
    parent_provider = getattr(parent_agent, "provider", "unknown")
    exec_info = phases["execution"]
    audit_info = phases["audit"]
    exec_provider = exec_info["provider"]
    exec_model = exec_info["model"]
    audit_provider = audit_info["provider"]
    audit_model = audit_info["model"]

    for phase_name, p, m in [("execution", exec_provider, exec_model), ("audit", audit_provider, audit_model)]:
        if m == "kimi-for-coding" or p == "kimi-coding":
            logger.error(
                "[agent-system] ROUTING ERROR: %s phase resolved to kimi-for-coding — "
                "configure agent_system.models.%s with openai-codex/gpt-5.5.",
                phase_name, phase_name,
            )

    if exec_provider and exec_model:
        logger.info(
            "[agent-system] model routing: planning=%s via %s, execution=%s via %s, audit=%s via %s",
            parent_model, parent_provider, exec_model, exec_provider, audit_model, audit_provider,
        )
    else:
        logger.warning(
            "[agent-system] delegation.provider/model not configured — "
            "execution nodes will inherit parent model=%s. "
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

        if node_model == "kimi-for-coding" or node_provider == "kimi-coding":
            return _delegate_failure(
                context,
                f"[agent-system] ROUTING FAIL-CLOSED: node={node_id} phase={phase} "
                f"resolved to kimi-for-coding. Configure agent_system.models.{phase} "
                f"with openai-codex/gpt-5.5 in config.yaml.",
            )

        if node_provider and node_model:
            logger.info(
                "[agent-system] node=%s phase=%s executing with model=%s provider=%s",
                node_id, phase, node_model, node_provider,
            )
        else:
            logger.warning(
                "[agent-system] node=%s falling back to parent model=%s "
                "(reason: delegation.provider/model not configured)",
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
        return {
            "status": "completed" if completed else "failed",
            "output_quality": 90 if completed else 30,
            "execution_mode": "production_delegate_task",
            "output": {
                "result_summary": summary or f"{context['skill_id']} 已通过 delegate_task 执行",
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


def _format_final_response(result: dict[str, Any]) -> str:
    lines = [
        f"Hermes Agent System 已自动执行 `{result['pipeline_id']}`。",
        f"运行 ID：`{result['run_id']}`",
        f"整体状态：`{result['status']}`",
        "",
        "节点状态：",
    ]
    for item in result.get("results", []):
        lines.append(
            f"- `{item.get('node_id')}`：{item.get('status')}，"
            f"Skill={', '.join(item.get('skills_loaded', [])) or '无'}"
        )
    lines.extend(
        [
            "",
            f"审计日志：`{result.get('audit_log')}`",
            f"复盘摘要：`{result.get('review_summary', {}).get('run_id', result.get('run_id'))}`",
            f"Skill 权重：`{Path(result.get('audit_log', '')).parent.parent / 'skill_weights.json'}`",
        ]
    )
    if result.get("status") != "completed":
        lines.append("当前存在阻塞或失败节点，请查看审计日志中的异常和待补项。")
    return "\n".join(lines)
