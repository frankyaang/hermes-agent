from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_system.capability_readiness import _invalidate_manifest_cache
from agent_system.hermes_sdk import HermesExpertManager, HermesSchedulerManager, HermesSkillManager
from agent_system.output_contracts import normalize_business_delegate_output
from agent_system.runtime import HermesAgentSystemRuntime


def _fixed_now() -> datetime:
    return datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)


def _write_business_manifest(root: Path) -> None:
    skills = ["voc_insight", "ops_dashboard", "dashboard_html", "audit", "briefing"]
    manifest = {
        "version": "1.1",
        "routes": [
            {
                "pipeline_id": "insight_flow",
                "readiness_state": "ready",
                "production_ready": True,
                "executor_type": "delegate_task",
                "allowed_entrypoints": ["gateway", "feishu", "cli", "test"],
                "required_skills": ["voc_insight", "briefing"],
                "output_contract": "business output contract",
                "readiness_reason": "test fixture",
                "owner": "test",
                "evidence": {"tests": "test fixture"},
            },
            {
                "pipeline_id": "dashboard_flow",
                "readiness_state": "ready",
                "production_ready": True,
                "executor_type": "delegate_task",
                "allowed_entrypoints": ["gateway", "feishu", "cli", "test"],
                "required_skills": ["voc_insight", "ops_dashboard", "briefing"],
                "output_contract": "business output contract",
                "readiness_reason": "test fixture",
                "owner": "test",
                "evidence": {"tests": "test fixture"},
            },
            {
                "pipeline_id": "html_flow",
                "readiness_state": "ready",
                "production_ready": True,
                "executor_type": "delegate_task",
                "allowed_entrypoints": ["gateway", "feishu", "cli", "test"],
                "required_skills": ["voc_insight", "ops_dashboard", "dashboard_html", "audit"],
                "output_contract": "business output contract",
                "readiness_reason": "test fixture",
                "owner": "test",
                "evidence": {"tests": "test fixture"},
            },
            {
                "pipeline_id": "dashboard_from_artifact_flow",
                "readiness_state": "ready",
                "production_ready": True,
                "executor_type": "system+delegate_task",
                "allowed_entrypoints": ["gateway", "feishu", "cli", "test"],
                "required_skills": ["artifact_resolver", "ops_dashboard"],
                "output_contract": "artifact path resolved by system executor then dashboard package from delegate_task",
                "readiness_reason": "test fixture",
                "owner": "test",
                "evidence": {"tests": "test fixture"},
            },
        ],
        "skills": [
            {
                "skill_id": sid,
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "delegate_task",
                "production_ready": True,
                "output_contract": "artifact_path, main_report_path, result_summary, quality_flags",
                "readiness_reason": "test fixture",
                "owner": "test",
                "evidence": {"tests": "test fixture"},
            }
            for sid in skills
        ]
        + [
            {
                "skill_id": "artifact_resolver",
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "system",
                "production_ready": True,
                "output_contract": "artifact_path",
                "readiness_reason": "test fixture",
                "owner": "test",
                "evidence": {"tests": "test fixture"},
            }
        ],
    }
    (root / "readiness_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _invalidate_manifest_cache(root)


def _create_business_project(tmp_path: Path) -> Path:
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    for name, display_name, skill_type in [
        ("voc_insight", "用户洞察", "analysis"),
        ("ops_dashboard", "运营看板", "report_generation"),
        ("dashboard_html", "看板渲染", "render"),
        ("audit", "核查", "audit"),
        ("briefing", "过程汇报", "status_report"),
        ("artifact_resolver", "产物定位", "analysis"),
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
        skills=["voc_insight"],
        private_memory=True,
    )
    expert_manager.create_expert(
        name="ops_expert",
        display_name="运营专家",
        description="负责运营看板",
        skills=["ops_dashboard"],
        private_memory=True,
    )
    expert_manager.create_expert(
        name="render_expert",
        display_name="渲染专家",
        description="负责 HTML 渲染",
        skills=["dashboard_html"],
        private_memory=True,
    )
    expert_manager.create_expert(
        name="audit_expert",
        display_name="审计专家",
        description="负责 QA 核查",
        skills=["audit"],
        private_memory=True,
    )

    scheduler = HermesSchedulerManager(project_name="agent_system", root_dir=root)
    scheduler.create_scheduler(
        name="main_scheduler",
        display_name="主调度器",
        description="调度业务生成流程",
        supervised_modules=["experts", "skills"],
        exception_handling="block_on_required_node",
        decision_logging=True,
    )
    scheduler.initialize_routes(
        scheduler_name="main_scheduler",
        pipelines=[
            _route("insight_flow", 1, "voc_insight", "用户洞察", "VOC、评论、竞品和质量反馈", "用户洞察结论", "user_analyst"),
            _route("insight_flow", "key_node_completion", "briefing", "过程汇报", "用户洞察结论", "过程汇报", None, depends_on=["voc_insight"], optional=True, final_output=True),
            _route("dashboard_flow", 1, "voc_insight", "用户洞察", "VOC、评论、竞品和质量反馈", "用户洞察结论", "user_analyst"),
            _route("dashboard_flow", 2, "ops_dashboard", "运营看板", "用户洞察结论", "产品运营报告与Dashboard结构", "ops_expert", depends_on=["voc_insight"], final_output=True),
            _route("dashboard_flow", "key_node_completion", "briefing", "过程汇报", "产品运营报告与Dashboard结构", "过程汇报", None, depends_on=["ops_dashboard"], optional=True),
            _route("html_flow", 1, "voc_insight", "用户洞察", "VOC、评论、竞品和质量反馈", "用户洞察结论", "user_analyst"),
            _route("html_flow", 2, "ops_dashboard", "运营看板", "用户洞察结论", "产品运营报告与Dashboard结构", "ops_expert", depends_on=["voc_insight"]),
            _route("html_flow", 3, "dashboard_html", "看板渲染", "产品运营报告与Dashboard结构", "HTML/PDF", "render_expert", depends_on=["ops_dashboard"], final_output=True),
            _route("html_flow", "quality_gate", "audit", "核查", "运营看板输出与渲染结果", "核查结论", "audit_expert", depends_on=["dashboard_html"], optional=True),
            _route("dashboard_from_artifact_flow", 1, "artifact_resolver", "产物定位", "用户消息/报告路径", "已有报告内容", None),
            _route("dashboard_from_artifact_flow", 2, "ops_dashboard", "运营看板", "已有报告/洞察结论", "产品运营报告与Dashboard结构", "ops_expert", depends_on=["artifact_resolver"], final_output=True, user_gate=True),
        ],
    )
    _write_business_manifest(root)
    return root


def _route(
    pipeline_id: str,
    step: int | str,
    node: str,
    display_name: str,
    input_type: str,
    output_type: str,
    primary_expert: str | None,
    *,
    depends_on: list[str] | None = None,
    optional: bool = False,
    final_output: bool = False,
    user_gate: bool = False,
) -> dict:
    route = {
        "pipeline_id": pipeline_id,
        "pipeline_name": pipeline_id,
        "step": step,
        "node": node,
        "display_name": display_name,
        "constraints": {"input_type": input_type, "output_type": output_type, "max_runtime": 120},
        "supervision": {
            "scheduler_monitor": True,
            "expert_required": primary_expert is not None,
            "primary_expert": primary_expert,
            "secondary_experts": [],
        },
        "user_gate": user_gate,
    }
    if depends_on:
        route["depends_on"] = depends_on
    if optional:
        route["optional"] = True
    if final_output:
        route["final_output"] = True
    return route


def test_delegate_executor_normalizes_business_output_contract(monkeypatch, tmp_path: Path):
    from agent_system.cli_bridge import _make_delegate_skill_executor

    report = tmp_path / "delegate_report.md"
    report.write_text("ok", encoding="utf-8")

    def fake_delegate_task(**kwargs):
        return json.dumps(
            {
                "results": [
                    {
                        "status": "completed",
                        "summary": f"完成报告：{report}",
                        "api_calls": 1,
                    }
                ]
            }
        )

    monkeypatch.setattr("tools.delegate_tool.delegate_task", fake_delegate_task)
    monkeypatch.setattr(
        "agent_system.cli_bridge._resolve_all_phase_models",
        lambda: {
            "planning": {"provider": "xiamiapi", "model": "claude-opus-4-7"},
            "execution": {"provider": "openai-codex", "model": "gpt-5.5"},
            "audit": {"provider": "openai-codex", "model": "gpt-5.5"},
        },
    )
    monkeypatch.setattr(
        "agent_system.cli_bridge._online_agent_probe",
        lambda parent: {"credential_status": "available"},
    )

    parent = SimpleNamespace(model="claude-opus-4-7", _active_children_lock=threading.Lock())
    executor = _make_delegate_skill_executor(parent)
    result = executor(
        {
            "task_package": {"node_id": "voc_insight", "delegate_task": {"role": "leaf"}},
            "skill_id": "voc_insight",
            "expert_id": "user_analyst",
            "expert_role": "primary",
            "input_payload": {"source_materials": ["VOC"]},
            "prior_results": {},
            "skill": {},
            "max_spawn_depth": 1,
        }
    )

    output = result["output"]
    assert result["status"] == "completed"
    assert output["artifact_path"] == str(report)
    assert output["main_report_path"] == str(report)
    assert output["result_summary"]
    assert "delegate_completed" in output["quality_flags"]
    assert "online_llm_observed" in output["quality_flags"]


def test_business_routes_e2e_generate_artifacts_audit_review_and_skill_memory(tmp_path: Path):
    root = _create_business_project(tmp_path)
    artifact_root = root / "smoke_artifacts"

    def contract_executor(context: dict) -> dict:
        skill_id = context["skill_id"]
        artifact = artifact_root / f"{skill_id}.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f"# {skill_id}\n\nok\n", encoding="utf-8")
        output = normalize_business_delegate_output(
            skill_id=skill_id,
            output={"result_summary": f"{skill_id} completed", "main_report_path": str(artifact)},
            completed=True,
            main_report_path=str(artifact),
            child_status="completed",
            api_calls=1,
            credential_status="available",
        )
        return {
            "status": "completed",
            "output_quality": 92,
            "execution_mode": "production_delegate_task",
            "output": output,
            "audit_checks": {"real_delegate_task_executed": True},
            "exceptions": [],
        }

    runtime = HermesAgentSystemRuntime(
        root_dir=root,
        skill_executor=contract_executor,
        now_fn=_fixed_now,
    )

    source_report = root / "input_report.md"
    source_report.write_text("# Existing Report\n\nVOC baseline\n", encoding="utf-8")

    for pipeline_id in ("insight_flow", "dashboard_flow", "html_flow", "dashboard_from_artifact_flow"):
        result = runtime.run_pipeline(
            pipeline_id=pipeline_id,
            input_payload={
                "source_materials": ["VOC 样本", str(source_report)],
                "task": pipeline_id,
            },
            human_inputs={"ops_dashboard": "人工确认使用该报告生成看板"},
            parallel=False,
        )
        assert result["status"] == "completed"
        assert Path(result["audit_log"]).exists()
        assert result["review_summary"]["pipeline_id"] == pipeline_id
        assert (root / "audit" / "review_summary.json").exists()
        for node_result in result["results"]:
            output = node_result["output"]
            assert output["artifact_path"]
            assert output["main_report_path"]
            assert output["result_summary"]
            if node_result["node_id"] == "artifact_resolver":
                assert output["artifact_path"] == str(source_report)
            else:
                assert output["quality_flags"]

    assert (root / "skills" / "voc_insight" / "skill_mem" / "MEMORY.md").exists()
    assert (root / "skills" / "ops_dashboard" / "skill_mem" / "MEMORY.md").exists()
    assert (root / "skills" / "dashboard_html" / "skill_mem" / "MEMORY.md").exists()
