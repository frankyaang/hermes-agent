from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_system.capability_readiness import _invalidate_manifest_cache
from agent_system.hermes_sdk import (
    HermesExpertManager,
    HermesSchedulerManager,
    HermesSkillManager,
)
from agent_system.planner import PlannerEngine
from agent_system.runtime import HermesAgentSystemRuntime


def _write_ready_manifest(root: Path, pipeline_ids: list[str], skill_ids: list[str]) -> None:
    """Write a readiness_manifest.json making all given pipelines and skills ready."""
    manifest_dir = root / "agent_system"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "1.0",
        "routes": [
            {
                "pipeline_id": pid,
                "readiness_state": "ready",
                "production_ready": True,
                "allowed_entrypoints": ["gateway", "feishu", "cli", "test"],
                "required_skills": [],
                "output_contract": "test_output",
                "readiness_reason": "test fixture",
                "owner": "test",
            }
            for pid in pipeline_ids
        ],
        "skills": [
            {
                "skill_id": sid,
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "delegate_task",
                "production_ready": True,
                "output_contract": "test_output",
                "readiness_reason": "test fixture",
                "owner": "test",
            }
            for sid in skill_ids
        ],
    }
    manifest_path = manifest_dir / "readiness_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _invalidate_manifest_cache(root)


def _fixed_now() -> datetime:
    return datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc)


def _create_base_project(tmp_path: Path, routes: list[dict]) -> Path:
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    skill_manager.create_skill(
        name="voc_insight",
        display_name="用户洞察",
        description="分析 VOC 和竞品反馈",
        type="analysis",
        pipeline="voc_insight_pipeline",
        private_memory=True,
    )
    skill_manager.create_skill(
        name="ops_dashboard",
        display_name="运营看板",
        description="生成运营看板结构",
        type="report_generation",
        pipeline="ops_dashboard_pipeline",
        private_memory=True,
    )
    skill_manager.create_skill(
        name="briefing",
        display_name="过程汇报",
        description="生成过程汇报",
        type="status_report",
        pipeline="briefing_pipeline",
        private_memory=True,
    )
    skill_manager.create_skill(
        name="superpowers",
        display_name="智能增强",
        description="辅助复杂判断",
        type="analysis_assist",
        pipeline="superpowers_pipeline",
        private_memory=True,
    )

    expert_manager = HermesExpertManager(project_name="agent_system", root_dir=root)
    expert_manager.create_expert(
        name="user_analyst",
        display_name="用户分析专家",
        description="负责用户洞察",
        skills=["voc_insight", "superpowers", "briefing"],
        private_memory=True,
    )
    expert_manager.create_expert(
        name="ops_expert",
        display_name="运营专家",
        description="负责运营看板",
        skills=["ops_dashboard", "superpowers", "briefing"],
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
    scheduler.initialize_routes(scheduler_name="main_scheduler", pipelines=routes)
    # Derive pipeline_ids and skill_ids from routes for manifest
    pipeline_ids = list({str(r.get("pipeline_id") or "") for r in routes if r.get("pipeline_id")})
    skill_ids = ["voc_insight", "ops_dashboard", "briefing", "superpowers"]
    _write_ready_manifest(root, pipeline_ids=pipeline_ids, skill_ids=skill_ids)
    return root


def _dashboard_routes() -> list[dict]:
    return [
        {
            "pipeline_id": "dashboard_flow",
            "pipeline_name": "看板流程",
            "step": 1,
            "node": "voc_insight",
            "display_name": "用户洞察",
            "constraints": {
                "input_type": "VOC、评论、竞品和质量反馈",
                "output_type": "用户洞察结论",
                "max_runtime": 300,
            },
            "supervision": {
                "scheduler_monitor": True,
                "expert_required": True,
                "primary_expert": "user_analyst",
                "secondary_experts": ["ops_expert"],
            },
            "user_gate": True,
        },
        {
            "pipeline_id": "dashboard_flow",
            "pipeline_name": "看板流程",
            "step": 2,
            "node": "ops_dashboard",
            "display_name": "运营看板",
            "depends_on": ["voc_insight"],
            "constraints": {
                "input_type": "用户洞察结论",
                "output_type": "产品运营报告与 Dashboard 结构",
                "max_runtime": 180,
            },
            "supervision": {
                "scheduler_monitor": True,
                "expert_required": True,
                "primary_expert": "ops_expert",
                "secondary_experts": ["user_analyst"],
            },
            "user_gate": True,
            "final_output": True,
        },
    ]


def _skill_executor(context: dict) -> dict:
    skill_id = context["skill_id"]
    output = {
        "result_summary": f"{context.get('expert_id') or 'system'}:{skill_id}",
        "skill_id": skill_id,
    }
    if context["requested_skill_id"] == "voc_insight":
        output["top15_count"] = 15
    return {
        "status": "completed",
        "output_quality": 90,
        "output": output,
        "audit_checks": {"custom_executor": True},
    }


def test_runtime_executes_dag_writes_audit_review_and_skill_weights(tmp_path: Path) -> None:
    root = _create_base_project(tmp_path, _dashboard_routes())
    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=_skill_executor, now_fn=_fixed_now)

    result = runtime.run_pipeline(
        pipeline_id="dashboard_flow",
        input_payload={"source_materials": ["VOC 表"]},
        human_inputs={"voc_insight": "人工确认洞察可用", "ops_dashboard": "人工确认交付"},
    )

    assert result["status"] == "completed"
    assert result["execution_groups"] == [["voc_insight"], ["ops_dashboard"]]
    assert [node["status"] for node in result["results"]] == ["completed", "completed"]
    assert result["results"][0]["human_review_required"] == "是"
    assert result["results"][0]["human_review_ui_available"] is False
    assert result["results"][0]["human_input_summary"] == "人工确认洞察可用"
    assert result["results"][0]["skill_execution_modes"] == ["custom_skill_executor"]
    assert result["results"][0]["primary_expert_skill_calls"][0]["skill_id"] == "voc_insight"
    assert result["results"][0]["secondary_expert_skill_calls"][0]["skill_id"] == "ops_dashboard"
    assert result["results"][0]["dynamic_overrides"][0]["replacement_skill_id"] == "ops_dashboard"

    audit_lines = (root / "audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 2
    assert json.loads(audit_lines[0])["human_review_required"] == "是"
    review_summary = json.loads((root / "audit" / "review_summary.json").read_text(encoding="utf-8"))
    assert "human_intervention" in review_summary["review_triggers"]
    assert review_summary["skill_weights_updated"] is True
    assert review_summary["experience_isolation"]["rule"] == "允许按规则读取上层经验；写入只限自身层级，不跨层覆盖。"
    assert {update["layer"] for update in review_summary["experience_updates"]} == {
        "system",
        "expert",
        "skill",
    }
    weights = json.loads((root / "skill_weights.json").read_text(encoding="utf-8"))
    assert "voc_insight" in weights["skills"]
    assert weights["skills"]["voc_insight"]["weight"] == 100
    system_memory = (root / "memory" / "system_mem" / "MEMORY.md").read_text(encoding="utf-8")
    expert_memory = (root / "experts" / "user_analyst" / "expert_mem" / "MEMORY.md").read_text(
        encoding="utf-8"
    )
    skill_memory = (root / "skills" / "voc_insight" / "skill_mem" / "MEMORY.md").read_text(
        encoding="utf-8"
    )
    assert result["run_id"] in system_memory
    assert result["run_id"] in expert_memory
    assert result["run_id"] in skill_memory
    assert "系统级经验" in system_memory
    assert "专家级经验" in expert_memory
    assert "Skill级经验" in skill_memory
    assert "Skill级经验" not in expert_memory
    assert "专家级经验" not in skill_memory
    experience_index = (root / "audit" / "experience_updates.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(experience_index) == len(review_summary["experience_updates"])
    assert json.loads(experience_index[0])["write_scope"] == "system_only"


def test_runtime_calls_post_audit_react_planner(tmp_path: Path) -> None:
    root = _create_base_project(tmp_path, _dashboard_routes())
    react_calls: list[dict] = []

    def fake_react(payload: dict) -> dict:
        react_calls.append(payload)
        return {
            "llm_used": True,
            "stage": payload["stage"],
            "react_decision": "continue",
            "next_actions": ["继续交付已完成结果"],
            "reason": "审计后无阻塞风险",
        }

    runtime = HermesAgentSystemRuntime(
        root_dir=root,
        skill_executor=_skill_executor,
        planning_react_callback=fake_react,
        now_fn=_fixed_now,
    )

    result = runtime.run_pipeline(
        pipeline_id="dashboard_flow",
        input_payload={"source_materials": ["VOC 表"]},
        human_inputs={"voc_insight": "人工确认洞察可用", "ops_dashboard": "人工确认交付"},
    )

    assert react_calls
    assert react_calls[0]["stage"] == "post_audit_react"
    assert react_calls[0]["pipeline_id"] == "dashboard_flow"
    assert react_calls[0]["status"] == "completed"
    assert result["planning_llm_calls"] == 1
    assert result["review_summary"]["react_plan"]["react_decision"] == "continue"


def test_user_gate_blocks_downstream_without_human_input(tmp_path: Path) -> None:
    root = _create_base_project(tmp_path, _dashboard_routes())
    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=_skill_executor, now_fn=_fixed_now)

    result = runtime.run_pipeline(
        pipeline_id="dashboard_flow",
        input_payload={"source_materials": ["VOC 表"]},
    )

    assert result["status"] == "blocked"
    assert result["results"][0]["status"] == "blocked"
    assert result["results"][0]["human_review_required"] == "是"
    assert result["results"][0]["human_review_ui_available"] is False
    assert result["results"][1]["status"] == "blocked_dependency"
    assert result["results"][1]["exceptions"][0]["event"] == "dependency_blocked"


def test_user_gate_uses_human_review_callback(tmp_path: Path) -> None:
    root = _create_base_project(tmp_path, _dashboard_routes())
    prompts: list[dict] = []

    def human_review_callback(request: dict) -> str:
        prompts.append(request)
        return f"人工批准 {request['node_id']}"

    runtime = HermesAgentSystemRuntime(
        root_dir=root,
        skill_executor=_skill_executor,
        human_review_callback=human_review_callback,
        now_fn=_fixed_now,
    )

    result = runtime.run_pipeline(
        pipeline_id="dashboard_flow",
        input_payload={"source_materials": ["VOC 表"]},
    )

    assert result["status"] == "completed"
    assert [prompt["node_id"] for prompt in prompts] == ["voc_insight", "ops_dashboard"]
    assert result["results"][0]["human_review_ui_available"] is True
    assert result["results"][0]["human_review_decision"] == "approved"
    assert result["results"][0]["human_review_blocking"] is False
    assert result["results"][0]["human_review_channel"] == "agent_system_approval_ui"
    assert result["results"][0]["human_input_summary"] == "人工批准 voc_insight"
    assert result["results"][1]["human_input_summary"] == "人工批准 ops_dashboard"
    assert result["review_summary"]["human_input_summary"] == [
        "人工批准 voc_insight",
        "人工批准 ops_dashboard",
    ]
    assert result["review_summary"]["human_review_decisions"][0]["decision"] == "approved"


def test_user_gate_rejection_blocks_downstream(tmp_path: Path) -> None:
    root = _create_base_project(tmp_path, _dashboard_routes())

    def human_review_callback(request: dict) -> str:
        return "阻塞并补充资料"

    runtime = HermesAgentSystemRuntime(
        root_dir=root,
        skill_executor=_skill_executor,
        human_review_callback=human_review_callback,
        now_fn=_fixed_now,
    )

    result = runtime.run_pipeline(
        pipeline_id="dashboard_flow",
        input_payload={"source_materials": ["VOC 表"]},
    )

    assert result["status"] == "blocked"
    assert result["results"][0]["status"] == "blocked"
    assert result["results"][0]["human_review_decision"] == "blocked"
    assert result["results"][0]["human_review_blocking"] is True
    assert result["results"][1]["status"] == "blocked_dependency"
    assert result["review_summary"]["human_review_decisions"][0]["blocking"] is True


def test_optional_node_failure_does_not_block_main_flow(tmp_path: Path) -> None:
    routes = [
        {
            "pipeline_id": "optional_flow",
            "pipeline_name": "可选流程",
            "step": 1,
            "node": "briefing",
            "display_name": "过程汇报",
            "constraints": {
                "input_type": "用户洞察结论",
                "output_type": "过程汇报",
                "max_runtime": 90,
            },
            "supervision": {
                "scheduler_monitor": True,
                "expert_required": False,
                "primary_expert": None,
                "secondary_experts": [],
            },
            "optional": True,
            "user_gate": False,
        },
        {
            "pipeline_id": "optional_flow",
            "pipeline_name": "可选流程",
            "step": 2,
            "node": "ops_dashboard",
            "display_name": "运营看板",
            "depends_on": ["briefing"],
            "constraints": {
                "input_type": "过程汇报",
                "output_type": "产品运营报告与 Dashboard 结构",
                "max_runtime": 180,
            },
            "supervision": {
                "scheduler_monitor": True,
                "expert_required": True,
                "primary_expert": "ops_expert",
                "secondary_experts": [],
            },
            "user_gate": False,
            "final_output": True,
        },
    ]
    root = _create_base_project(tmp_path, routes)

    def executor(context: dict) -> dict:
        if context["skill_id"] == "briefing":
            raise RuntimeError("briefing failed")
        return _skill_executor(context)

    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=executor, now_fn=_fixed_now)

    result = runtime.run_pipeline(pipeline_id="optional_flow")

    assert result["status"] == "completed"
    assert result["results"][0]["status"] == "optional_failed"
    assert result["results"][1]["status"] == "completed"
    assert result["results"][1]["depends_on"] == ["briefing"]


def test_exception_mapping_enters_audit_and_review(tmp_path: Path) -> None:
    routes = _dashboard_routes()[:1]
    routes[0]["user_gate"] = False
    root = _create_base_project(tmp_path, routes)

    def executor(context: dict) -> dict:
        return {
            "status": "completed",
            "output_quality": 70,
            "output": {
                "result_summary": "Top15 不足",
                "top15_count": 12,
            },
        }

    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=executor, now_fn=_fixed_now)

    result = runtime.run_pipeline(
        pipeline_id="dashboard_flow",
        input_payload={"source_materials": ["VOC 表"]},
    )

    assert result["status"] == "completed"
    assert result["results"][0]["exceptions"][0]["event"] == "top15_missing"
    assert result["results"][0]["audit_checks"]["top15_complete"] is False
    assert "exception_event" in result["review_summary"]["review_triggers"]


def test_runtime_exposes_configured_max_spawn_depth_in_task_packages(tmp_path: Path) -> None:
    root = _create_base_project(tmp_path, _dashboard_routes())
    runtime = HermesAgentSystemRuntime(root_dir=root, max_spawn_depth=2, now_fn=_fixed_now)

    flow = runtime.build_delegate_flow(
        pipeline_id="dashboard_flow",
        input_payload={"source_materials": ["VOC 表"]},
    )

    assert flow["max_spawn_depth"] == 2
    assert {package["max_spawn_depth"] for package in flow["delegate_tasks"]} == {2}
    assert {package["delegate_task"]["role"] for package in flow["delegate_tasks"]} == {
        "orchestrator"
    }


# ── Dynamic pipeline tests ────────────────────────────────────────────────


def _create_full_project(tmp_path: Path) -> Path:
    """Project with both VOC and non-VOC skills registered."""
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    for name, display, stype in [
        ("voc_insight", "用户洞察", "analysis"),
        ("ops_dashboard", "运营看板", "report_generation"),
        ("artifact_resolver", "产物定位", "analysis"),
        ("artifact_status", "产物状态查询", "status_report"),
        ("artifact_delivery", "产物交付", "status_report"),
        ("doc_publish", "文档发布", "ui_render"),
        ("report_revision", "报告修订", "report_generation"),
        ("briefing", "过程汇报", "status_report"),
    ]:
        skill_manager.create_skill(
            name=name, display_name=display, description=f"{display} Skill",
            type=stype, pipeline=f"{name}_pipeline", private_memory=True,
        )

    expert_manager = HermesExpertManager(project_name="agent_system", root_dir=root)
    expert_manager.create_expert(
        name="user_analyst", display_name="用户分析专家", description="负责用户洞察",
        skills=["voc_insight", "briefing"], private_memory=True,
    )
    expert_manager.create_expert(
        name="ops_expert", display_name="运营专家", description="负责运营看板",
        skills=["ops_dashboard", "briefing"], private_memory=True,
    )

    scheduler = HermesSchedulerManager(project_name="agent_system", root_dir=root)
    scheduler.create_scheduler(
        name="main_scheduler", display_name="主调度器", description="调度专家和 Skill",
        supervised_modules=["experts", "skills"], exception_handling="block_on_required_node",
        decision_logging=True,
    )
    scheduler.initialize_routes(
        scheduler_name="main_scheduler",
        pipelines=[
            {
                "pipeline_id": "insight_flow", "pipeline_name": "洞察流程", "step": 1,
                "node": "voc_insight", "display_name": "用户洞察",
                "constraints": {"input_type": "VOC", "output_type": "洞察结论", "max_runtime": 300},
                "supervision": {"scheduler_monitor": True, "expert_required": True,
                                "primary_expert": "user_analyst", "secondary_experts": []},
                "user_gate": False, "final_output": True,
            },
            {
                "pipeline_id": "artifact_status_flow", "pipeline_name": "状态查询流程", "step": 1,
                "node": "artifact_resolver", "display_name": "产物定位",
                "constraints": {"input_type": "user_message", "output_type": "artifact_path", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False,
                                "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
            },
            {
                "pipeline_id": "artifact_status_flow", "pipeline_name": "状态查询流程", "step": 2,
                "node": "artifact_status", "display_name": "产物状态查询",
                "depends_on": ["artifact_resolver"],
                "constraints": {"input_type": "artifact_path", "output_type": "status_report", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False,
                                "primary_expert": None, "secondary_experts": []},
                "user_gate": False, "final_output": True,
            },
            {
                "pipeline_id": "dashboard_from_artifact_flow", "pipeline_name": "已有报告生成看板流程", "step": 1,
                "node": "artifact_resolver", "display_name": "产物定位",
                "constraints": {"input_type": "user_message", "output_type": "artifact_path", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False,
                                "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
            },
            {
                "pipeline_id": "dashboard_from_artifact_flow", "pipeline_name": "已有报告生成看板流程", "step": 2,
                "node": "ops_dashboard", "display_name": "运营看板",
                "depends_on": ["artifact_resolver"],
                "constraints": {"input_type": "已有报告", "output_type": "dashboard", "max_runtime": 180},
                "supervision": {"scheduler_monitor": True, "expert_required": True,
                                "primary_expert": "ops_expert", "secondary_experts": []},
                "user_gate": False, "final_output": True,
            },
        ],
    )
    _write_ready_manifest(
        root,
        pipeline_ids=["insight_flow", "artifact_status_flow", "dashboard_from_artifact_flow"],
        skill_ids=[
            "voc_insight", "ops_dashboard", "artifact_resolver", "artifact_status",
            "artifact_delivery", "doc_publish", "report_revision", "briefing",
        ],
    )
    return root


def test_run_dynamic_pipeline_voc_analysis(tmp_path: Path) -> None:
    root = _create_full_project(tmp_path)
    routes = json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())
    planner = PlannerEngine(root, routes)

    ctx = planner.build_task_context("基于这份 VOC 调研数据分析用户画像")
    selection = planner.select_primary_expert(ctx)
    spec = planner.plan_task(ctx, selection)
    pipeline_spec = planner.generate_pipeline(ctx, selection, spec)
    errors = planner.validate_dynamic_pipeline(pipeline_spec, spec)

    assert errors == []
    assert spec.requires_voc_insight is True
    node_ids = [n.node_id for n in pipeline_spec.nodes]
    assert "voc_insight" in node_ids

    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=_skill_executor, now_fn=_fixed_now)
    result = runtime.run_dynamic_pipeline(
        pipeline_spec=pipeline_spec,
        input_payload={"source_materials": ["VOC 调研数据"]},
    )

    assert result["status"] == "completed"
    assert result["task_spec"]["requires_voc_insight"] is True
    assert result["planning_source"] == "template_reuse"
    assert result["skipped_voc_insight_reason"] == ""


def test_run_dynamic_pipeline_dashboard_from_artifact(tmp_path: Path) -> None:
    import tempfile, os
    root = _create_full_project(tmp_path)

    # Create a real file so existing_artifacts is populated
    fake_report = tmp_path / "existing_report.md"
    fake_report.write_text("# 洞察报告\n痛点：XXX", encoding="utf-8")

    routes = json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())
    planner = PlannerEngine(root, routes)

    ctx = planner.build_task_context(
        f"基于已有报告生成看板 {fake_report}",
    )
    ctx.existing_artifacts.append(str(fake_report))
    selection = planner.select_primary_expert(ctx)
    spec = planner.plan_task(ctx, selection)
    pipeline_spec = planner.generate_pipeline(ctx, selection, spec)
    errors = planner.validate_dynamic_pipeline(pipeline_spec, spec)

    assert errors == []
    assert spec.requires_voc_insight is False
    node_ids = [n.node_id for n in pipeline_spec.nodes]
    assert "voc_insight" not in node_ids
    assert "ops_dashboard" in node_ids
    assert pipeline_spec.pipeline_id == "dashboard_from_artifact_flow"

    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=_skill_executor, now_fn=_fixed_now)
    result = runtime.run_dynamic_pipeline(
        pipeline_spec=pipeline_spec,
        input_payload={"source_materials": [str(fake_report)]},
        human_inputs={"ops_dashboard": "确认"},
    )

    assert result["status"] == "completed"
    assert result["skipped_voc_insight_reason"] != ""
    audit_events = [
        json.loads(line)
        for line in (root / "audit" / "audit.jsonl").read_text().splitlines()
    ]
    assert all(e.get("skipped_voc_insight_reason") != "" for e in audit_events)


def test_explicit_pipeline_id_backward_compat(tmp_path: Path) -> None:
    """Explicit pipeline_id= in message must bypass the planner and use the old path."""
    root = _create_full_project(tmp_path)
    routes = json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())

    from agent_system.cli_bridge import _resolve_explicit_pipeline_id
    pipeline_id = _resolve_explicit_pipeline_id(
        "请运行 agent_system pipeline_id=insight_flow", routes
    )
    assert pipeline_id == "insight_flow"

    pipeline_id_none = _resolve_explicit_pipeline_id(
        "agent_system 请把这份文档转化为飞书云文档格式", routes
    )
    assert pipeline_id_none is None


def test_voc_task_no_prefix(tmp_path: Path) -> None:
    """'基于这份 VOC 调研数据分析用户画像' (no agent_system prefix) must route to
    voc_insight via PlannerEngine and execute successfully through run_dynamic_pipeline."""
    root = _create_full_project(tmp_path)
    routes = json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())
    planner = PlannerEngine(root, routes)

    ctx = planner.build_task_context("基于这份 VOC 调研数据分析用户画像")
    selection = planner.select_primary_expert(ctx)
    spec = planner.plan_task(ctx, selection)
    pipeline_spec = planner.generate_pipeline(ctx, selection, spec)
    errors = planner.validate_dynamic_pipeline(pipeline_spec, spec)

    assert errors == []
    assert spec.requires_voc_insight is True
    assert "voc_insight" in [n.node_id for n in pipeline_spec.nodes]

    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=_skill_executor, now_fn=_fixed_now)
    result = runtime.run_dynamic_pipeline(
        pipeline_spec=pipeline_spec,
        input_payload={"source_materials": ["VOC 调研数据"]},
    )

    assert result["status"] == "completed"
    assert result["task_spec"]["requires_voc_insight"] is True
    executed_nodes = [r["node_id"] for r in result["results"]]
    assert "voc_insight" in executed_nodes


def test_delivery_no_prefix(tmp_path: Path) -> None:
    """'帮我把执行结果发出来' (no prefix) must route to artifact_delivery via
    ephemeral expert, with no voc_insight anywhere in the pipeline."""
    root = _create_full_project(tmp_path)
    routes = json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())
    planner = PlannerEngine(root, routes)

    ctx = planner.build_task_context("帮我把执行结果发出来")
    selection = planner.select_primary_expert(ctx)
    spec = planner.plan_task(ctx, selection)
    pipeline_spec = planner.generate_pipeline(ctx, selection, spec)
    errors = planner.validate_dynamic_pipeline(pipeline_spec, spec)

    assert errors == []
    assert selection.primary_expert_id == "artifact_delivery_expert"
    assert selection.primary_expert_source == "ephemeral"
    assert spec.requires_voc_insight is False
    node_ids = [n.node_id for n in pipeline_spec.nodes]
    assert "voc_insight" not in node_ids
    assert "artifact_delivery" in node_ids

    runtime = HermesAgentSystemRuntime(root_dir=root, skill_executor=_skill_executor, now_fn=_fixed_now)
    result = runtime.run_dynamic_pipeline(
        pipeline_spec=pipeline_spec,
        input_payload={"source_materials": ["执行结果路径"]},
    )

    assert result["status"] == "completed"
    assert result["task_spec"]["requires_voc_insight"] is False
    executed_nodes = [r["node_id"] for r in result["results"]]
    assert "artifact_delivery" in executed_nodes
    assert "voc_insight" not in executed_nodes


def _single_node_routes() -> list[dict]:
    return [
        {
            "pipeline_id": "insight_flow",
            "pipeline_name": "洞察流程",
            "step": 1,
            "node": "voc_insight",
            "display_name": "用户洞察",
            "constraints": {
                "input_type": "VOC",
                "output_type": "洞察结论",
                "max_runtime": 300,
            },
            "supervision": {
                "expert_required": True,
                "primary_expert": "user_analyst",
                "secondary_experts": [],
            },
        },
    ]


def test_heartbeat_progress_emitted_for_slow_sequential_node(tmp_path: Path) -> None:
    import time as _time

    root = _create_base_project(tmp_path, _single_node_routes())
    progress_events: list[tuple[str, str]] = []

    def _slow_executor(context: dict) -> dict:
        _time.sleep(0.35)
        return {"status": "completed", "output": {"skill_id": context.get("skill_id", "?")}}

    def _progress_cb(event_type: str, msg: str) -> None:
        progress_events.append((event_type, msg))

    runtime = HermesAgentSystemRuntime(
        root_dir=root,
        skill_executor=_slow_executor,
        now_fn=_fixed_now,
        progress_callback=_progress_cb,
        _heartbeat_interval=0.1,
        _heartbeat_min_elapsed=0.05,
    )
    result = runtime.run_pipeline(
        pipeline_id="insight_flow",
        input_payload={"source_materials": ["test_voc"]},
        parallel=False,
    )
    assert result["status"] == "completed"
    heartbeats = [(t, m) for t, m in progress_events if "仍在执行" in m]
    assert len(heartbeats) >= 1, f"期望至少 1 个心跳，实际 progress_events={progress_events}"
    assert heartbeats[0][0] == "__execution_log__"
    assert "⏳" in heartbeats[0][1]


def test_task_plan_emitted_before_node_execution(tmp_path: Path) -> None:
    root = _create_base_project(tmp_path, _dashboard_routes())
    events: list[tuple[str, str]] = []

    def _progress_cb(event_type: str, msg: str) -> None:
        events.append((event_type, msg))

    runtime = HermesAgentSystemRuntime(
        root_dir=root,
        skill_executor=_skill_executor,
        now_fn=_fixed_now,
        progress_callback=_progress_cb,
    )
    runtime.run_pipeline(
        pipeline_id="dashboard_flow",
        input_payload={"source_materials": ["VOC 表"]},
        human_inputs={"voc_insight": "确认", "ops_dashboard": "确认"},
        parallel=False,
    )
    plan_events = [(t, m) for t, m in events if t == "__task_plan__"]
    assert len(plan_events) >= 1, f"期望至少 1 个任务规划事件，实际 events={events[:5]}"
    first_plan = plan_events[0][1]
    assert "🧭 任务规划" in first_plan
    assert "主专家" in first_plan
    assert "工具层技能" in first_plan
    assert "执行路径" in first_plan
