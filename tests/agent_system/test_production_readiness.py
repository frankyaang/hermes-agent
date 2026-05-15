"""
Tests for production readiness gating of agent_system pipelines.

Verifies:
- check_pipeline_readiness() correctly identifies production_ready=false pipelines
- Implicit trigger (keyword match) of non-ready routes returns None (falls back to chat)
- Explicit trigger (agent_system marker) of non-ready routes returns a block response
- react_decision=block is caught by _format_final_response() before status checks
- _route_candidates() excludes production_ready=false pipelines
- expert binding from planning metadata when supervision.primary_expert is null
- Runtime enforce_skill_readiness mode blocks nodes with empty pipelines
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from unittest.mock import MagicMock, patch

from agent_system.capability_readiness import validate_readiness_manifest, _invalidate_manifest_cache
from agent_system.cli_bridge import (
    _format_final_response,
    _route_candidates,
    check_pipeline_readiness,
    maybe_run_agent_system_from_message,
)
from agent_system.hermes_sdk import (
    HermesExpertManager,
    HermesSchedulerManager,
    HermesSkillManager,
)
from agent_system.planner import (
    DynamicPipelineSpec,
    DynamicPipelineSpecNode,
    ExpertSelection,
)
from agent_system.runtime import HermesAgentSystemRuntime


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class FakeParentAgent:
    model = "test-model"
    provider = "test-provider"
    base_url = "http://example.test/v1"

    def __init__(self) -> None:
        self.clarify_prompts: list = []


def _make_routes_payload_with_non_ready(non_ready_pipeline_id: str) -> dict:
    """Build a minimal routes_payload where one pipeline is production_ready=false."""
    return {
        "scheduler": "main_scheduler",
        "version": 1,
        "pipelines": [
            {
                "pipeline_id": "artifact_status_flow",
                "pipeline_name": "状态查询流程",
                "node": "artifact_resolver",
                "display_name": "产物定位",
                "supervision": {"primary_expert": None, "secondary_experts": []},
            },
            {
                "pipeline_id": non_ready_pipeline_id,
                "pipeline_name": "报告修订流程",
                "node": "artifact_resolver",
                "display_name": "产物定位",
                "production_ready": False,
                "supervision": {"primary_expert": None, "secondary_experts": []},
            },
            {
                "pipeline_id": non_ready_pipeline_id,
                "pipeline_name": "报告修订流程",
                "node": "report_revision",
                "display_name": "报告修订",
                "production_ready": False,
                "final_output": True,
                "supervision": {"primary_expert": None, "secondary_experts": []},
            },
        ],
    }


def _create_project_with_revision(tmp_path: Path) -> Path:
    """Project that includes report_revision_flow marked production_ready=false."""
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    for name, display_name, skill_type in [
        ("artifact_resolver", "产物定位", "analysis"),
        ("artifact_status", "产物状态查询", "status_report"),
        ("report_revision", "报告修订", "report_generation"),
        ("voc_insight", "用户洞察", "analysis"),
        ("briefing", "过程汇报", "status_report"),
    ]:
        skill_manager.create_skill(
            name=name,
            display_name=display_name,
            description=f"{display_name} Skill",
            type=skill_type,
            pipeline=f"{name}_pipeline",
            private_memory=True,
        )

    expert_manager = HermesExpertManager(project_name="agent_system", root_dir=root)
    expert_manager.create_expert(
        name="user_analyst",
        display_name="用户分析专家",
        description="负责用户洞察",
        skills=["voc_insight", "briefing"],
        private_memory=True,
    )

    scheduler = HermesSchedulerManager(project_name="agent_system", root_dir=root)
    scheduler.create_scheduler(
        name="main_scheduler",
        display_name="主调度器",
        description="调度专家和 Skill",
        supervised_modules=["experts", "skills"],
        exception_handling="block_on_required_node",
        decision_logging=True,
    )
    scheduler.initialize_routes(
        scheduler_name="main_scheduler",
        pipelines=[
            {
                "pipeline_id": "artifact_status_flow",
                "pipeline_name": "状态查询流程",
                "step": 1,
                "node": "artifact_resolver",
                "display_name": "产物定位",
                "constraints": {"input_type": "user_message", "output_type": "artifact_path", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
                "final_output": True,
            },
            # report_revision_flow marked production_ready=false
            {
                "pipeline_id": "report_revision_flow",
                "pipeline_name": "报告修订流程",
                "step": 1,
                "node": "artifact_resolver",
                "display_name": "产物定位",
                "production_ready": False,
                "constraints": {"input_type": "user_message", "output_type": "artifact_path", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
            },
            {
                "pipeline_id": "report_revision_flow",
                "pipeline_name": "报告修订流程",
                "step": 2,
                "node": "report_revision",
                "display_name": "报告修订",
                "depends_on": ["artifact_resolver"],
                "production_ready": False,
                "constraints": {"input_type": "existing_report", "output_type": "revised_report", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
                "final_output": True,
            },
        ],
    )
    return root


# ---------------------------------------------------------------------------
# Test 1: check_pipeline_readiness — ready pipeline
# ---------------------------------------------------------------------------

def test_check_pipeline_readiness_ready_pipeline() -> None:
    """A pipeline with no production_ready=false entries returns (True, '')."""
    routes_payload = _make_routes_payload_with_non_ready("report_revision_flow")
    ready, reason = check_pipeline_readiness(routes_payload, "artifact_status_flow")
    assert ready is True
    assert reason == ""


# ---------------------------------------------------------------------------
# Test 2: check_pipeline_readiness — non-ready pipeline
# ---------------------------------------------------------------------------

def test_check_pipeline_readiness_non_ready_pipeline() -> None:
    """A pipeline where any entry has production_ready=false returns (False, reason)."""
    routes_payload = _make_routes_payload_with_non_ready("report_revision_flow")
    ready, reason = check_pipeline_readiness(routes_payload, "report_revision_flow")
    assert ready is False
    assert "report_revision_flow" in reason
    assert reason  # non-empty explanation


# ---------------------------------------------------------------------------
# Test 3: check_pipeline_readiness — missing pipeline
# ---------------------------------------------------------------------------

def test_check_pipeline_readiness_missing_pipeline() -> None:
    """A pipeline not present at all in routes returns (False, reason)."""
    routes_payload = _make_routes_payload_with_non_ready("report_revision_flow")
    ready, reason = check_pipeline_readiness(routes_payload, "nonexistent_flow")
    assert ready is False
    assert "nonexistent_flow" in reason


# ---------------------------------------------------------------------------
# Test 4: Implicit keyword trigger of non-ready route → None
# ---------------------------------------------------------------------------

def test_feishu_revision_keywords_no_ready_route_returns_none(tmp_path: Path) -> None:
    """
    A message with revision keywords ('润色') that resolves to report_revision_flow,
    when report_revision_flow has production_ready=false, must return None so the
    message falls back to normal conversation.

    Implicit trigger = no 'agent_system' marker in message.
    """
    root = _create_project_with_revision(tmp_path)

    result = maybe_run_agent_system_from_message(
        "帮我润色一下这份报告",  # matches _REVISION_KEYWORDS, no agent_system marker
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is None, (
        "Implicit trigger of a non-ready route must return None "
        "(fall back to normal conversation), not enter agent_system"
    )


# ---------------------------------------------------------------------------
# Test 5: Explicit agent_system marker + non-ready route → block response
# ---------------------------------------------------------------------------

def test_explicit_agent_system_non_ready_route_returns_block(tmp_path: Path) -> None:
    """
    A message with the 'agent_system' marker that resolves to a non-ready pipeline
    must return a block/stub response explaining the pipeline is not production-ready,
    rather than silently executing with system expert.
    """
    root = _create_project_with_revision(tmp_path)

    result = maybe_run_agent_system_from_message(
        "agent_system 帮我润色一下这份报告",  # explicit marker + revision keyword
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is not None, "Explicit agent_system trigger must always return a result"
    agent_status = result.get("agent_system_status", "")
    final_response = result.get("final_response", "")
    assert agent_status == "blocked", (
        f"Expected agent_system_status='blocked', got: {agent_status!r}"
    )
    assert (
        "尚未" in final_response
        or "stub" in final_response
        or "not production" in final_response.lower()
        or "production_ready" in final_response.lower()
    ), f"Expected non-ready explanation in final_response, got: {final_response!r}"


# ---------------------------------------------------------------------------
# Test 6: react_decision=block overrides completed+no_output in _format_final_response
# ---------------------------------------------------------------------------

def test_react_plan_block_decision_overrides_final_response() -> None:
    """
    When result contains react_plan.react_decision='block', _format_final_response
    must return the block reason string, NOT the 'completed but no output' fallback.
    """
    result = {
        "status": "completed",
        "results": [],
        "audit_log": "/tmp/audit.jsonl",
        "run_id": "Run_test_20260514T120000",
        "react_plan": {
            "react_decision": "block",
            "reason": "数据质量审计不通过，禁止发布",
            "llm_used": True,
        },
    }

    response = _format_final_response(result)

    assert "数据质量审计不通过" in response, (
        f"Expected block reason in response, got: {response!r}"
    )
    assert "阻断" in response or "block" in response.lower(), (
        f"Expected block signal in response, got: {response!r}"
    )
    # Must NOT show the misleading "completed but no output" message
    assert "执行完成，但未找到输出内容" not in response, (
        f"react_plan=block must override the 'completed but no output' message, got: {response!r}"
    )


# ---------------------------------------------------------------------------
# Test 7: Runtime enforce_skill_readiness=True blocks empty-pipeline nodes
# ---------------------------------------------------------------------------

def test_runtime_non_executable_node_blocked_with_enforce_flag(tmp_path: Path) -> None:
    """
    When HermesAgentSystemRuntime is created with enforce_skill_readiness=True,
    a node whose skill has an empty pipeline (steps=[]) must be blocked (not completed).
    """
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    skill_manager.create_skill(
        name="report_revision",
        display_name="报告修订",
        description="报告修订 Skill",
        type="report_generation",
        pipeline="report_revision_pipeline",
        private_memory=True,
    )

    scheduler = HermesSchedulerManager(project_name="agent_system", root_dir=root)
    scheduler.create_scheduler(
        name="main_scheduler",
        display_name="主调度器",
        description="",
        supervised_modules=["skills"],
        exception_handling="block_on_required_node",
        decision_logging=True,
    )
    scheduler.initialize_routes(
        scheduler_name="main_scheduler",
        pipelines=[
            {
                "pipeline_id": "report_revision_flow",
                "pipeline_name": "报告修订流程",
                "step": 1,
                "node": "report_revision",
                "display_name": "报告修订",
                "constraints": {"input_type": "existing_report", "output_type": "revised_report", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
                "final_output": True,
            }
        ],
    )

    runtime = HermesAgentSystemRuntime(
        root_dir=root,
        enforce_skill_readiness=True,  # NEW parameter
    )

    result = runtime.run_pipeline(
        pipeline_id="report_revision_flow",
        input_payload={"source_materials": ["test"]},
    )

    node_statuses = [r["status"] for r in result["results"]]
    assert any(s in ("blocked", "failed") for s in node_statuses), (
        f"Expected blocked/failed node with enforce_skill_readiness=True, got: {node_statuses}"
    )


# ---------------------------------------------------------------------------
# Test 8: _route_candidates excludes production_ready=false pipelines
# ---------------------------------------------------------------------------

def test_planning_llm_candidates_exclude_non_ready_pipelines() -> None:
    """
    _route_candidates() must NOT include pipelines that have any entry
    with production_ready=false. The planning LLM must never see non-ready routes.
    """
    routes_payload = _make_routes_payload_with_non_ready("report_revision_flow")
    candidates = _route_candidates(routes_payload)
    candidate_ids = {c["pipeline_id"] for c in candidates}

    assert "report_revision_flow" not in candidate_ids, (
        f"Non-ready pipeline must not appear in planning LLM candidates: {candidate_ids}"
    )
    assert "artifact_status_flow" in candidate_ids, (
        f"Ready pipeline must still appear in candidates: {candidate_ids}"
    )


# ---------------------------------------------------------------------------
# Test 9: Expert binding from planning metadata when supervision.primary_expert is null
# ---------------------------------------------------------------------------

def test_expert_binding_from_planning_metadata_when_supervision_null(tmp_path: Path) -> None:
    """
    When pipeline_spec.expert_selection.primary_expert_id is set but the final_output
    node has supervision.primary_expert=null, the runtime must bind the planning expert
    to that node rather than silently using system execution.
    """
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    skill_manager.create_skill(
        name="ops_dashboard",
        display_name="运营看板",
        description="运营看板 Skill",
        type="report_generation",
        pipeline="ops_dashboard_pipeline",
        private_memory=True,
    )
    expert_manager = HermesExpertManager(project_name="agent_system", root_dir=root)
    expert_manager.create_expert(
        name="ops_expert",
        display_name="运营专家",
        description="运营专家",
        skills=["ops_dashboard"],
        private_memory=True,
    )

    scheduler = HermesSchedulerManager(project_name="agent_system", root_dir=root)
    scheduler.create_scheduler(
        name="main_scheduler",
        display_name="主调度器",
        description="",
        supervised_modules=["experts", "skills"],
        exception_handling="block_on_required_node",
        decision_logging=True,
    )
    scheduler.initialize_routes(
        scheduler_name="main_scheduler",
        pipelines=[
            {
                "pipeline_id": "test_flow",
                "pipeline_name": "测试流程",
                "step": 1,
                "node": "ops_dashboard",
                "display_name": "运营看板",
                "constraints": {"input_type": "data", "output_type": "dashboard", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
                "final_output": True,
            }
        ],
    )

    selection = ExpertSelection(
        primary_expert_id="ops_expert",
        primary_expert_source="registered",
        reason="planning chose ops_expert",
        confidence=0.9,
    )
    spec_node = DynamicPipelineSpecNode(
        node_id="ops_dashboard",
        display_name="运营看板",
        skill_id="ops_dashboard",
        primary_expert=None,   # supervision.primary_expert was null in routes
        final_output=True,
    )
    pipeline_spec = DynamicPipelineSpec(
        pipeline_id="test_flow",
        pipeline_name="测试流程",
        generated_by_primary_expert="ops_expert",
        planning_source="template_reuse",
        nodes=[spec_node],
        final_output_node="ops_dashboard",
        expert_selection=asdict(selection),
    )

    # Write manifest so ops_dashboard skill passes readiness check
    manifest_dir = root / "agent_system"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    _manifest = {
        "version": "1.0",
        "routes": [
            {
                "pipeline_id": "test_flow",
                "readiness_state": "ready",
                "production_ready": True,
                "allowed_entrypoints": ["gateway", "test"],
                "required_skills": [],
                "output_contract": "test_output",
                "readiness_reason": "test fixture",
                "owner": "test",
            }
        ],
        "skills": [
            {
                "skill_id": "ops_dashboard",
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "system",
                "production_ready": True,
                "output_contract": "test_output",
                "readiness_reason": "test fixture",
                "owner": "test",
            }
        ],
    }
    (manifest_dir / "readiness_manifest.json").write_text(json.dumps(_manifest), encoding="utf-8")
    _invalidate_manifest_cache(root)

    executed_experts: list[str | None] = []

    def capturing_executor(context: dict) -> dict:
        executed_experts.append(context.get("expert_id"))
        return {"status": "completed", "output": {"result_summary": "done"}}

    runtime = HermesAgentSystemRuntime(
        root_dir=root,
        skill_executor=capturing_executor,
    )

    result = runtime.run_dynamic_pipeline(
        pipeline_spec=pipeline_spec,
        input_payload={"source_materials": ["test"]},
    )

    assert result["status"] == "completed"
    # After the fix: expert should be "ops_expert" from planning metadata, not None
    assert executed_experts[0] == "ops_expert", (
        f"Expected ops_expert from planning metadata, got: {executed_experts[0]!r}. "
        "Runtime must bind planning-selected expert when supervision.primary_expert is null."
    )


# ---------------------------------------------------------------------------
# Test 10: Expert not registered → explicit failure (not silent fallback)
# ---------------------------------------------------------------------------

def test_expert_binding_fails_explicitly_when_expert_not_registered(tmp_path: Path) -> None:
    """
    When planning selects an expert that does not exist in the experts directory,
    and that expert was bound because supervision.primary_expert was null (expert_binding_required),
    the final_output node must produce a failed result rather than silently using system.
    """
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    skill_manager.create_skill(
        name="ops_dashboard",
        display_name="运营看板",
        description="Skill",
        type="report_generation",
        pipeline="ops_dashboard_pipeline",
        private_memory=True,
    )

    scheduler = HermesSchedulerManager(project_name="agent_system", root_dir=root)
    scheduler.create_scheduler(
        name="main_scheduler",
        display_name="主调度器",
        description="",
        supervised_modules=["skills"],
        exception_handling="block_on_required_node",
        decision_logging=True,
    )
    scheduler.initialize_routes(
        scheduler_name="main_scheduler",
        pipelines=[
            {
                "pipeline_id": "test_flow",
                "pipeline_name": "测试流程",
                "step": 1,
                "node": "ops_dashboard",
                "display_name": "运营看板",
                "constraints": {"input_type": "data", "output_type": "dashboard", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
                "final_output": True,
            }
        ],
    )

    selection = ExpertSelection(
        primary_expert_id="nonexistent_expert",
        primary_expert_source="registered",
        reason="planning chose nonexistent expert",
        confidence=0.9,
    )
    spec_node = DynamicPipelineSpecNode(
        node_id="ops_dashboard",
        display_name="运营看板",
        skill_id="ops_dashboard",
        primary_expert=None,  # null in supervision → triggers expert_binding_required
        final_output=True,
    )
    pipeline_spec = DynamicPipelineSpec(
        pipeline_id="test_flow",
        pipeline_name="测试流程",
        generated_by_primary_expert="nonexistent_expert",
        planning_source="template_reuse",
        nodes=[spec_node],
        final_output_node="ops_dashboard",
        expert_selection=asdict(selection),
    )

    # Write manifest so ops_dashboard skill passes readiness check
    manifest_dir_10 = root / "agent_system"
    manifest_dir_10.mkdir(parents=True, exist_ok=True)
    _manifest_10 = {
        "version": "1.0",
        "routes": [
            {
                "pipeline_id": "test_flow",
                "readiness_state": "ready",
                "production_ready": True,
                "allowed_entrypoints": ["gateway", "test"],
                "required_skills": [],
                "output_contract": "test_output",
                "readiness_reason": "test fixture",
                "owner": "test",
            }
        ],
        "skills": [
            {
                "skill_id": "ops_dashboard",
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "system",
                "production_ready": True,
                "output_contract": "test_output",
                "readiness_reason": "test fixture",
                "owner": "test",
            }
        ],
    }
    (manifest_dir_10 / "readiness_manifest.json").write_text(json.dumps(_manifest_10), encoding="utf-8")
    _invalidate_manifest_cache(root)

    executed_experts: list[str | None] = []

    def capturing_executor(context: dict) -> dict:
        executed_experts.append(context.get("expert_id"))
        return {"status": "completed", "output": {"result_summary": "done"}}

    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=capturing_executor)

    result = runtime.run_dynamic_pipeline(
        pipeline_spec=pipeline_spec,
        input_payload={"source_materials": ["test"]},
    )

    # With the fix: expert_binding_required + expert not found → node fails explicitly
    # Without the fix: silently uses system and "completes"
    node_statuses = [r["status"] for r in result["results"]]
    assert any(s == "failed" for s in node_statuses), (
        f"Expected failed node when bound expert not registered, got: {node_statuses}. "
        "Runtime must fail explicitly when expert_binding_required expert is missing."
    )


# ---------------------------------------------------------------------------
# Test 11: validate_readiness_manifest 对缺失 manifest 记录报错
# ---------------------------------------------------------------------------

def test_validate_readiness_manifest_reports_missing_pipeline(tmp_path: Path) -> None:
    """
    validate_readiness_manifest must return a non-empty error list when
    routes_payload contains a pipeline not registered in readiness_manifest.json.
    """
    import json as _json

    # Create a minimal manifest that does NOT include unknown_new_flow
    manifest_dir = tmp_path / "agent_system"
    manifest_dir.mkdir(parents=True)
    manifest = {
        "version": "1.0",
        "routes": [
            {
                "pipeline_id": "artifact_status_flow",
                "readiness_state": "unknown",
                "production_ready": False,
                "allowed_entrypoints": [],
                "required_skills": [],
                "output_contract": "",
                "readiness_reason": "",
                "owner": "",
            }
        ],
        "skills": [],
    }
    (manifest_dir / "readiness_manifest.json").write_text(
        _json.dumps(manifest), encoding="utf-8"
    )

    routes_payload = {
        "pipelines": [
            {"pipeline_id": "artifact_status_flow"},
            {"pipeline_id": "unknown_new_flow"},
        ]
    }

    errors = validate_readiness_manifest(tmp_path, routes_payload)

    assert errors, "Expected non-empty error list for pipeline missing from manifest"
    assert any("unknown_new_flow" in e for e in errors), (
        f"Expected error mentioning 'unknown_new_flow', got: {errors}"
    )


# ---------------------------------------------------------------------------
# Test 12: 张嫄养马回归测试
# ---------------------------------------------------------------------------

def test_zhangyuan_yangma_message_does_not_call_planning_llm(tmp_path: Path) -> None:
    """
    A message about reviewing document content ("这一部分里面的维度你是否有同步考虑上一代产品问题...")
    must NOT enter report_revision_flow, must NOT call Opus, and must return None or
    agent_system_status='blocked'.

    report_revision_flow has production_ready=false → must be excluded from candidates,
    so the planner LLM should never be invoked for this message.
    """
    root = _create_project_with_revision(tmp_path)

    planning_llm_called = []

    original_enhance = None
    try:
        import agent_system.cli_bridge as _cb
        original_enhance = getattr(_cb, "_maybe_enhance_initial_plan_with_llm", None)
    except Exception:
        pass

    def _fake_enhance(*args, **kwargs):
        planning_llm_called.append(True)
        if original_enhance is not None:
            return original_enhance(*args, **kwargs)
        return None

    message = (
        "这一部分里面的维度你是否有同步考虑上一代产品问题？"
        "这在飞书文档内的用户洞察部分有提及，检查是否已经包含"
    )

    with patch(
        "agent_system.cli_bridge._maybe_enhance_initial_plan_with_llm",
        side_effect=_fake_enhance,
    ):
        result = maybe_run_agent_system_from_message(
            message,
            parent_agent=FakeParentAgent(),
            root_dir=root,
        )

    assert not planning_llm_called, (
        "planning LLM must not be called for a message that matches no ready route"
    )
    assert result is None or (
        isinstance(result, dict) and result.get("agent_system_status") == "blocked"
    ), (
        f"Expected None or blocked result for non-ready route message, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# Test 13: internal_skill_call 不重新触发 planner
# ---------------------------------------------------------------------------

def test_internal_skill_call_does_not_trigger_planner(tmp_path: Path) -> None:
    """
    A message with /internal_skill_call prefix must not instantiate PlannerEngine.
    The internal skill call path bypasses the planning LLM entirely.
    """
    root = _create_project_with_revision(tmp_path)

    planner_instantiated = []

    original_planner_cls = None
    try:
        import agent_system.planner as _planner_mod
        original_planner_cls = getattr(_planner_mod, "PlannerEngine", None)
    except Exception:
        pass

    class SpyPlannerEngine:
        def __init__(self, *args, **kwargs):
            planner_instantiated.append(True)
            if original_planner_cls is not None:
                self._inner = original_planner_cls(*args, **kwargs)

        def __getattr__(self, name):
            if original_planner_cls is not None and hasattr(self, "_inner"):
                return getattr(self._inner, name)
            raise AttributeError(name)

    message = "/internal_skill_call skill_id=voc_insight input={}"

    with patch("agent_system.planner.PlannerEngine", SpyPlannerEngine):
        result = maybe_run_agent_system_from_message(
            message,
            parent_agent=FakeParentAgent(),
            root_dir=root,
        )

    assert not planner_instantiated, (
        f"PlannerEngine must not be instantiated for /internal_skill_call messages, "
        f"but it was called {len(planner_instantiated)} time(s)"
    )


# ---------------------------------------------------------------------------
# Test 14: gateway/cli_bridge 生产路径创建 runtime 时 enforce_skill_readiness 为 True
# ---------------------------------------------------------------------------

def test_production_entrypoint_creates_runtime_with_enforce_skill_readiness(
    tmp_path: Path,
) -> None:
    """
    When maybe_run_agent_system_from_message triggers a pipeline execution,
    HermesAgentSystemRuntime must be instantiated with enforce_skill_readiness=True.
    """
    import json as _json

    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    skill_manager.create_skill(
        name="artifact_resolver",
        display_name="产物定位",
        description="产物定位 Skill",
        type="analysis",
        pipeline="artifact_resolver_pipeline",
        private_memory=True,
    )
    skill_manager.create_skill(
        name="artifact_status",
        display_name="产物状态查询",
        description="产物状态查询 Skill",
        type="status_report",
        pipeline="artifact_status_pipeline",
        private_memory=True,
    )

    scheduler = HermesSchedulerManager(project_name="agent_system", root_dir=root)
    scheduler.create_scheduler(
        name="main_scheduler",
        display_name="主调度器",
        description="调度专家和 Skill",
        supervised_modules=["skills"],
        exception_handling="block_on_required_node",
        decision_logging=True,
    )
    scheduler.initialize_routes(
        scheduler_name="main_scheduler",
        pipelines=[
            {
                "pipeline_id": "artifact_status_flow",
                "pipeline_name": "状态查询流程",
                "step": 1,
                "node": "artifact_resolver",
                "display_name": "产物定位",
                "constraints": {
                    "input_type": "user_message",
                    "output_type": "artifact_path",
                    "max_runtime": 120,
                },
                "supervision": {
                    "scheduler_monitor": True,
                    "expert_required": False,
                    "primary_expert": None,
                    "secondary_experts": [],
                },
                "user_gate": False,
                "final_output": True,
                "production_ready": True,
            },
        ],
    )

    # Write a manifest that marks artifact_status_flow as ready
    manifest = {
        "version": "1.0",
        "routes": [
            {
                "pipeline_id": "artifact_status_flow",
                "readiness_state": "ready",
                "production_ready": True,
                "allowed_entrypoints": ["gateway", "feishu", "cli"],
                "required_skills": ["artifact_resolver"],
                "output_contract": "artifact_path_report",
                "readiness_reason": "ready for test",
                "owner": "test",
            }
        ],
        "skills": [
            {
                "skill_id": "artifact_resolver",
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "system",
                "production_ready": True,
                "output_contract": "artifact_path",
                "readiness_reason": "ready for test",
                "owner": "test",
            },
            {
                "skill_id": "artifact_status",
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "system",
                "production_ready": True,
                "output_contract": "status_report",
                "readiness_reason": "ready for test",
                "owner": "test",
            },
        ],
    }
    (root / "agent_system" / "readiness_manifest.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (root / "agent_system" / "readiness_manifest.json").write_text(
        _json.dumps(manifest), encoding="utf-8"
    )

    runtime_init_kwargs: list[dict] = []
    OriginalRuntime = HermesAgentSystemRuntime

    class SpyRuntime(OriginalRuntime):
        def __init__(self, *args, **kwargs):
            runtime_init_kwargs.append(dict(kwargs))
            super().__init__(*args, **kwargs)

    with patch("agent_system.cli_bridge.HermesAgentSystemRuntime", SpyRuntime):
        maybe_run_agent_system_from_message(
            "agent_system 查询产物状态",
            parent_agent=FakeParentAgent(),
            root_dir=root,
        )

    if runtime_init_kwargs:
        enforce_values = [kw.get("enforce_skill_readiness") for kw in runtime_init_kwargs]
        assert any(v is True for v in enforce_values), (
            f"Expected at least one HermesAgentSystemRuntime instantiation with "
            f"enforce_skill_readiness=True, got kwargs: {runtime_init_kwargs}"
        )
