from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agent_system.human_approval import AgentSystemApprovalUI
from agent_system.runtime import HermesAgentSystemRuntime


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
) -> dict[str, Any] | None:
    """Run an agent_system pipeline when a CLI turn explicitly requests it.

    This is intentionally narrow: ordinary chat only enters the runtime when
    the user message contains an agent_system marker and resolves to a concrete
    pipeline from routes.json.
    """

    if not isinstance(user_message, str) or not _requests_agent_system(user_message):
        return None

    project_root = _find_agent_system_root(root_dir)
    if project_root is None:
        return None

    routes_payload = _read_routes(project_root)
    pipeline_id = _resolve_pipeline_id(user_message, routes_payload)
    if not pipeline_id:
        return None

    max_spawn_depth = _configured_max_spawn_depth()
    runtime = HermesAgentSystemRuntime(
        root_dir=project_root,
        skill_executor=_make_delegate_skill_executor(parent_agent),
        human_review_callback=_make_human_review_callback(parent_agent),
        max_spawn_depth=max_spawn_depth,
    )
    result = runtime.run_pipeline(
        pipeline_id=pipeline_id,
        input_payload=_input_payload_from_message(user_message),
        human_inputs={},
        parallel=True,
    )
    final_response = _format_final_response(result)
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
    lowered = message.lower()
    return any(marker in lowered for marker in _AGENT_SYSTEM_MARKERS)


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


def _resolve_pipeline_id(message: str, routes_payload: dict[str, Any]) -> str | None:
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
    pipeline_names = {
        str(route.get("pipeline_name")): str(route.get("pipeline_id"))
        for route in pipelines
        if route.get("pipeline_id") and route.get("pipeline_name")
    }
    if explicit and explicit.group(1) in pipeline_ids:
        return explicit.group(1)
    for pipeline_id in sorted(pipeline_ids, key=len, reverse=True):
        if pipeline_id in message:
            return pipeline_id
    for pipeline_name, pipeline_id in pipeline_names.items():
        if pipeline_name and pipeline_name in message:
            return pipeline_id
    return None


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
    def _executor(context: dict[str, Any]) -> dict[str, Any]:
        package = context["task_package"]
        delegate_meta = package.get("delegate_task") or {}
        credential_probe = _online_agent_probe(parent_agent)
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
