from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_system.hermes_sdk import (
    HermesExpertManager,
    HermesSchedulerManager,
    HermesSkillManager,
)
from agent_system.runtime import HermesAgentSystemRuntime


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
