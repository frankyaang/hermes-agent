from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from agent_system.builder_dispatcher import maybe_handle_builder_mode
from agent_system.human_approval import AgentSystemApprovalUI
from agent_system.runtime import HermesAgentSystemRuntime

logger = logging.getLogger(__name__)


_AGENT_SYSTEM_MARKERS = (
    "/agent_system",
    "agent_system",
    "hermes agent system",
    "hermes-agent-system",
)

# 简单对话关键词 - 这些只做直接回复，不走 agent-system
_SIMPLE_CONVERSATION_MARKERS = (
    "你好", "您好", "hi", "hello", "嗨",
    "谢谢", "感谢", "谢啦",
    "再见", "拜拜", "下次见",
    "好的", "收到", "明白", "知道了",
    "可以", "行", "没问题",
    "嗯", "哦", "哈", "哇",
    "?", "？",
    "早安", "晚安", "午安",
    "辛苦了", "加油",
    # 单字/极短回复
    "好", "嗯", "啊", "呃",
)

# 隐式触发词 - 包含这些关键词时自动触发 agent_system
_IMPLICIT_TRIGGERS = (
    # 分析类
    "分析", "洞察", "调研", "研究",
    "用户洞察", "竞品分析", "质量反馈",
    # 看板类
    "看板", "仪表盘", "运营报告", "Dashboard",
    "数据看板", "报告生成",
    # 网页/HTML类
    "网页", "HTML", "可视化", "图表",
)

# 隐式触发管道映射
_IMPLICIT_PIPELINE_MAP = {
    "看板": "dashboard_flow",
    "仪表盘": "dashboard_flow",
    "运营报告": "dashboard_flow",
    "Dashboard": "dashboard_flow",
    "数据看板": "dashboard_flow",
    "报告生成": "dashboard_flow",
    "网页": "html_flow",
    "HTML": "html_flow",
    "可视化": "html_flow",
    "图表": "html_flow",
    "分析": "insight_flow",
    "洞察": "insight_flow",
    "调研": "insight_flow",
    "研究": "insight_flow",
    "用户洞察": "insight_flow",
    "竞品分析": "insight_flow",
    "质量反馈": "insight_flow",
}


def _is_simple_conversation(message: str) -> bool:
    """
    判断是否为简单对话（可直接回复，不走 agent-system）。

    简单对话定义：
    - 仅包含问候语、感谢语、告别语
    - 极短回复（少于 5 个字符）
    - 无具体任务请求
    """
    stripped = message.strip()

    # 纯标点符号
    if not stripped or all(c in ' \t\n\r.,。?!？!！' for c in stripped):
        return True

    lowered = stripped.lower()

    # 简单对话标记检查
    for marker in _SIMPLE_CONVERSATION_MARKERS:
        marker_lower = marker.lower()
        if lowered == marker_lower:
            return True
        # 问候语后面跟了内容 → 不是简单对话
        if lowered.startswith(marker_lower):
            remaining = stripped[len(marker):].strip()
            if remaining:
                # 问候语后面有内容，不是简单对话
                return False

    # 极短回复（少于 5 个字符且无明确意图）
    if len(stripped) < 5 and not any(c.isalpha() or c.isdigit() for c in stripped):
        return True

    return False


def _requests_agent_system(message: str) -> bool:
    """决定是否触发 agent-system。

    默认路径走 agent-system（包括规划、记忆学习、偏好进化）。
    只有简单对话可以直接回复。
    """
    # 简单对话 → 直接回复，不走 agent-system
    if _is_simple_conversation(message):
        return False

    # 显式标记检查（优先级最高）
    lowered = message.lower()
    if any(marker in lowered for marker in _AGENT_SYSTEM_MARKERS):
        return True

    # 默认：所有有意义的任务都走 agent-system
    # 这包括规划、分析、查询、执行等各种交互
    return True


def maybe_run_agent_system_from_message(
    user_message: str,
    *,
    parent_agent: Any,
    task_id: str | None = None,
    root_dir: str | Path | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict[str, Any] | None:
    """Run an agent_system pipeline when a CLI turn explicitly requests it.

    This is intentionally narrow: ordinary chat only enters the runtime when
    the user message contains an agent_system marker and resolves to a concrete
    pipeline from routes.json.
    """

    if not isinstance(user_message, str):
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

    if not _requests_agent_system(user_message):
        return None

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
        progress_callback=progress_callback,
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

    # 隐式触发：基于关键词自动映射到管道
    # 按长度排序，优先匹配更长的词
    for trigger in sorted(_IMPLICIT_PIPELINE_MAP.keys(), key=len, reverse=True):
        if trigger in message:
            mapped_pipeline = _IMPLICIT_PIPELINE_MAP[trigger]
            # 验证映射的管道是否在 routes 中存在
            if mapped_pipeline in pipeline_ids:
                return mapped_pipeline

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
    parent_provider = getattr(parent_agent, "provider", "unknown")
    exec_info = phases["execution"]
    audit_info = phases["audit"]
    exec_provider = exec_info["provider"]
    exec_model = exec_info["model"]
    audit_provider = audit_info["provider"]
    audit_model = audit_info["model"]

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
            "[agent-system] model routing: planning=%s via %s, execution=%s via %s, audit=%s via %s",
            parent_model, parent_provider, exec_model, exec_provider, audit_model, audit_provider,
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
