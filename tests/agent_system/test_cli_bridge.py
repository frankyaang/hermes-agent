from __future__ import annotations

import json
from pathlib import Path

from agent_system.human_approval import APPROVAL_CHOICES
from agent_system.cli_bridge import maybe_run_agent_system_from_message
from agent_system.hermes_sdk import (
    HermesExpertManager,
    HermesSchedulerManager,
    HermesSkillManager,
)
from agent_system.planner import PlannerEngine


class FakeParentAgent:
    model = "test-model"
    provider = "test-provider"
    base_url = "http://example.test/v1"

    def __init__(self) -> None:
        self.clarify_prompts: list[tuple[str, list[str] | None]] = []

    def clarify_callback(self, question, choices):
        self.clarify_prompts.append((question, choices))
        return "人工确认继续"


def _create_project(tmp_path: Path) -> Path:
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    for name, display_name in [
        ("voc_insight", "用户洞察"),
        ("ops_dashboard", "运营看板"),
        ("superpowers", "智能增强"),
    ]:
        skill_manager.create_skill(
            name=name,
            display_name=display_name,
            description=f"{display_name} Skill",
            type="analysis",
            pipeline=f"{name}_pipeline",
            private_memory=True,
        )

    expert_manager = HermesExpertManager(project_name="agent_system", root_dir=root)
    expert_manager.create_expert(
        name="user_analyst",
        display_name="用户分析专家",
        description="负责用户洞察",
        skills=["voc_insight", "superpowers"],
        private_memory=True,
    )
    expert_manager.create_expert(
        name="ops_expert",
        display_name="运营专家",
        description="负责运营看板",
        skills=["ops_dashboard", "superpowers"],
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
        ],
    )
    return root


def test_bridge_ignores_ordinary_chat(tmp_path: Path) -> None:
    root = _create_project(tmp_path)

    result = maybe_run_agent_system_from_message(
        "请正常聊天，不要运行流程",
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is None


def test_bridge_runs_pipeline_with_delegate_task_and_human_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _create_project(tmp_path)
    parent = FakeParentAgent()
    delegate_calls: list[dict] = []

    def fake_delegate_task(goal=None, context=None, role=None, parent_agent=None, **kwargs):
        delegate_calls.append(
            {
                "goal": goal,
                "context": json.loads(context),
                "role": role,
                "parent_agent": parent_agent,
            }
        )
        return json.dumps(
            {
                "results": [
                        {
                            "status": "completed",
                            "summary": f"真实 Agent 已执行 {role}",
                            "api_calls": 1,
                        }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("tools.delegate_tool.delegate_task", fake_delegate_task)
    monkeypatch.setattr("agent_system.cli_bridge._configured_max_spawn_depth", lambda: 2)

    result = maybe_run_agent_system_from_message(
        "请运行 agent_system pipeline_id=dashboard_flow，资料：VOC 表",
        parent_agent=parent,
        task_id="task-1",
        root_dir=root,
    )

    assert result is not None
    assert result["completed"] is True
    assert result["agent_system_status"] == "completed"
    assert result["agent_system_result"]["max_spawn_depth"] == 2
    assert len(parent.clarify_prompts) == 2
    assert parent.clarify_prompts[0][1] == APPROVAL_CHOICES
    assert delegate_calls
    assert {call["role"] for call in delegate_calls} == {"orchestrator"}
    assert all(call["parent_agent"] is parent for call in delegate_calls)
    assert delegate_calls[0]["context"]["execution_rules"]["use_real_skill_or_agent"] is True
    assert delegate_calls[0]["context"]["execution_rules"]["production_llm_required"] is True
    assert delegate_calls[0]["context"]["online_agent_probe"]["credential_status"] == "missing"

    audit_path = root / "audit" / "audit.jsonl"
    weights_path = root / "skill_weights.json"
    assert audit_path.exists()
    assert weights_path.exists()
    audit_events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert audit_events[0]["human_input_summary"] == "人工确认继续"
    assert audit_events[0]["human_review_decision"] == "approved"
    assert audit_events[0]["human_review_channel"] == "agent_system_approval_ui"
    assert audit_events[0]["human_review_ui_available"] is True
    assert audit_events[0]["real_skill_execution"] is True
    assert audit_events[0]["skill_execution_modes"] == ["production_delegate_task"]
    weights = json.loads(weights_path.read_text(encoding="utf-8"))
    assert weights["skills"]


def test_bridge_human_rejection_blocks_downstream(tmp_path: Path, monkeypatch) -> None:
    class BlockingParent(FakeParentAgent):
        def clarify_callback(self, question, choices):
            self.clarify_prompts.append((question, choices))
            return "阻塞并补充资料"

    root = _create_project(tmp_path)
    parent = BlockingParent()

    def fake_delegate_task(goal=None, context=None, role=None, parent_agent=None, **kwargs):
        return json.dumps(
            {
                "results": [
                    {
                        "status": "completed",
                        "summary": "真实 Agent 已执行",
                        "api_calls": 1,
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("tools.delegate_tool.delegate_task", fake_delegate_task)

    result = maybe_run_agent_system_from_message(
        "请运行 agent_system pipeline_id=dashboard_flow，资料：VOC 表",
        parent_agent=parent,
        root_dir=root,
    )

    assert result is not None
    assert result["agent_system_status"] == "blocked"
    node_results = result["agent_system_result"]["results"]
    assert node_results[0]["status"] == "blocked"
    assert node_results[0]["human_review_decision"] == "blocked"
    assert node_results[1]["status"] == "blocked_dependency"


def _create_project_with_non_voc_skills(tmp_path: Path) -> Path:
    """Fixture that includes artifact_resolver/status/delivery/doc_publish/report_revision skills."""
    root = tmp_path / "agent_system"
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    for name, display_name, skill_type in [
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
    expert_manager.create_expert(
        name="ops_expert",
        display_name="运营专家",
        description="负责运营看板",
        skills=["ops_dashboard", "briefing"],
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
            },
            {
                "pipeline_id": "artifact_status_flow",
                "pipeline_name": "状态查询流程",
                "step": 2,
                "node": "artifact_status",
                "display_name": "产物状态查询",
                "depends_on": ["artifact_resolver"],
                "constraints": {"input_type": "artifact_path", "output_type": "status_report", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
                "final_output": True,
            },
            {
                "pipeline_id": "artifact_delivery_flow",
                "pipeline_name": "产物交付流程",
                "step": 1,
                "node": "artifact_resolver",
                "display_name": "产物定位",
                "constraints": {"input_type": "user_message", "output_type": "artifact_path", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
            },
            {
                "pipeline_id": "artifact_delivery_flow",
                "pipeline_name": "产物交付流程",
                "step": 2,
                "node": "artifact_delivery",
                "display_name": "产物交付",
                "depends_on": ["artifact_resolver"],
                "constraints": {"input_type": "artifact_path", "output_type": "artifact_content", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
                "final_output": True,
            },
            {
                "pipeline_id": "doc_publish_flow",
                "pipeline_name": "文档发布流程",
                "step": 1,
                "node": "artifact_resolver",
                "display_name": "产物定位",
                "constraints": {"input_type": "user_message", "output_type": "artifact_path", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
            },
            {
                "pipeline_id": "doc_publish_flow",
                "pipeline_name": "文档发布流程",
                "step": 2,
                "node": "doc_publish",
                "display_name": "文档发布",
                "depends_on": ["artifact_resolver"],
                "constraints": {"input_type": "Markdown", "output_type": "feishu_doc", "max_runtime": 120},
                "supervision": {"scheduler_monitor": True, "expert_required": False, "primary_expert": None, "secondary_experts": []},
                "user_gate": False,
                "final_output": True,
            },
            {
                "pipeline_id": "insight_flow",
                "pipeline_name": "洞察流程",
                "step": 1,
                "node": "voc_insight",
                "display_name": "用户洞察",
                "constraints": {"input_type": "VOC", "output_type": "洞察结论", "max_runtime": 300},
                "supervision": {"scheduler_monitor": True, "expert_required": True, "primary_expert": "user_analyst", "secondary_experts": []},
                "user_gate": True,
                "final_output": True,
            },
        ],
    )
    return root


# ── Planner unit tests (no delegate_task needed) ──────────────────────────

def test_planner_format_conversion_skips_voc_insight(tmp_path: Path) -> None:
    root = _create_project_with_non_voc_skills(tmp_path)
    import json as _json
    routes = _json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())
    planner = PlannerEngine(root, routes)

    user_message = "agent_system 请把这份文档转化为飞书云文档格式"
    reply_context = "上次生成的用户洞察分析报告已完成，包含竞品反馈和痛点总结。"

    ctx = planner.build_task_context(user_message, reply_context=reply_context)
    selection = planner.select_primary_expert(ctx)
    spec = planner.plan_task(ctx, selection)
    pipeline = planner.generate_pipeline(ctx, selection, spec)
    errors = planner.validate_dynamic_pipeline(pipeline, spec)

    assert spec.requires_voc_insight is False
    assert spec.task_type == "doc_format"
    assert selection.primary_expert_id == "doc_format_expert"
    assert selection.primary_expert_source == "ephemeral"
    assert errors == []
    node_skill_ids = [n.skill_id for n in pipeline.nodes]
    assert "voc_insight" not in node_skill_ids


def test_planner_status_query_uses_status_expert(tmp_path: Path) -> None:
    root = _create_project_with_non_voc_skills(tmp_path)
    import json as _json
    routes = _json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())
    planner = PlannerEngine(root, routes)

    ctx = planner.build_task_context("agent_system 这个生成好了吗")
    selection = planner.select_primary_expert(ctx)
    spec = planner.plan_task(ctx, selection)
    pipeline = planner.generate_pipeline(ctx, selection, spec)
    errors = planner.validate_dynamic_pipeline(pipeline, spec)

    assert selection.primary_expert_id == "artifact_status_expert"
    assert spec.requires_voc_insight is False
    assert spec.requires_status_lookup is True
    assert errors == []
    assert "voc_insight" not in [n.skill_id for n in pipeline.nodes]
    assert pipeline.pipeline_id == "artifact_status_flow"


def test_planner_delivery_task_uses_delivery_expert(tmp_path: Path) -> None:
    root = _create_project_with_non_voc_skills(tmp_path)
    import json as _json
    routes = _json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())
    planner = PlannerEngine(root, routes)

    ctx = planner.build_task_context("agent_system 帮我把执行结果发出来")
    selection = planner.select_primary_expert(ctx)
    spec = planner.plan_task(ctx, selection)
    pipeline = planner.generate_pipeline(ctx, selection, spec)
    errors = planner.validate_dynamic_pipeline(pipeline, spec)

    assert selection.primary_expert_id == "artifact_delivery_expert"
    assert spec.task_type == "artifact_delivery"
    assert spec.requires_voc_insight is False
    assert errors == []
    node_ids = [n.node_id for n in pipeline.nodes]
    assert "artifact_resolver" in node_ids
    assert "artifact_delivery" in node_ids
    assert "voc_insight" not in node_ids


def test_planner_validate_rejects_voc_insight_in_non_voc_pipeline(tmp_path: Path) -> None:
    """validate_dynamic_pipeline must reject pipelines that contain voc_insight
    when requires_voc_insight=False."""
    from agent_system.planner import (
        DynamicPipelineSpec,
        DynamicPipelineSpecNode,
        ExpertSelection,
        TaskSpec,
    )
    root = _create_project_with_non_voc_skills(tmp_path)
    import json as _json
    routes = _json.loads((root / "scheduler" / "main_scheduler" / "routes.json").read_text())
    planner = PlannerEngine(root, routes)

    bad_pipeline = DynamicPipelineSpec(
        pipeline_id="bad",
        pipeline_name="bad",
        generated_by_primary_expert="doc_format_expert",
        planning_source="dynamic_generated",
        nodes=[
            DynamicPipelineSpecNode(node_id="voc_insight", display_name="用户洞察", skill_id="voc_insight", final_output=True),
        ],
        final_output_node="voc_insight",
    )
    bad_spec = TaskSpec(
        task_goal="格式转换",
        task_type="doc_format",
        input_kind="existing_report",
        output_kind="formatted_document",
        requires_voc_insight=False,
        requires_existing_artifact=True,
        requires_publish=True,
        requires_status_lookup=False,
        rejection_reason_for_voc_insight="任务为格式转换",
    )
    errors = planner.validate_dynamic_pipeline(bad_pipeline, bad_spec)
    assert len(errors) == 1
    assert "voc_insight" in errors[0]


def _fake_dynamic_run(root: Path):
    """Return a monkeypatch-compatible run_dynamic_pipeline that captures pipeline_spec."""
    captured: list = []

    def _impl(self, *, pipeline_spec, **kwargs):
        captured.append(pipeline_spec)
        return {
            "run_id": "Run_test",
            "pipeline_id": pipeline_spec.pipeline_id,
            "status": "completed",
            "results": [],
            "review_summary": {},
            "execution_groups": [],
            "audit_log": str(root / "audit" / "audit.jsonl"),
        }

    return _impl, captured


def test_format_conversion_no_agent_system_prefix(tmp_path: Path, monkeypatch) -> None:
    """'把这份文档转化为飞书云文档格式' (no 'agent_system' prefix) must enter the system
    and route to doc_publish_flow, never to voc_insight."""
    root = _create_project_with_non_voc_skills(tmp_path)
    impl, captured = _fake_dynamic_run(root)
    monkeypatch.setattr("agent_system.runtime.HermesAgentSystemRuntime.run_dynamic_pipeline", impl)

    result = maybe_run_agent_system_from_message(
        "把这份文档转化为飞书云文档格式",
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is not None, "message with task keyword should enter agent_system without explicit prefix"
    assert result["completed"] is True
    assert len(captured) == 1
    node_skill_ids = [n.skill_id for n in captured[0].nodes]
    assert "voc_insight" not in node_skill_ids
    assert "doc_publish" in node_skill_ids


def test_status_query_no_prefix(tmp_path: Path, monkeypatch) -> None:
    """'这个生成好了吗' (no prefix) must route to artifact_status_flow, not voc_insight."""
    root = _create_project_with_non_voc_skills(tmp_path)
    impl, captured = _fake_dynamic_run(root)
    monkeypatch.setattr("agent_system.runtime.HermesAgentSystemRuntime.run_dynamic_pipeline", impl)

    result = maybe_run_agent_system_from_message(
        "这个生成好了吗",
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is not None
    spec = captured[0]
    assert spec.pipeline_id == "artifact_status_flow"
    assert "voc_insight" not in [n.skill_id for n in spec.nodes]
    assert "artifact_status" in [n.node_id for n in spec.nodes]


def test_feishu_reply_voc_quote_format_task(tmp_path: Path, monkeypatch) -> None:
    """Feishu [Replying to: "用户洞察..."] prefix must be stripped before intent detection.
    The VOC content in the reply quote must NOT trigger voc_insight routing."""
    root = _create_project_with_non_voc_skills(tmp_path)
    impl, captured = _fake_dynamic_run(root)
    monkeypatch.setattr("agent_system.runtime.HermesAgentSystemRuntime.run_dynamic_pipeline", impl)

    feishu_msg = '[Replying to: "用户洞察：Q1复购率下降，痛点集中在..."]\n把这份文档转化为飞书云文档格式'
    result = maybe_run_agent_system_from_message(
        feishu_msg,
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )

    assert result is not None
    spec = captured[0]
    # task_context_summary = ctx.current_user_message[:120]; must not contain the Feishu prefix
    assert "用户洞察" not in spec.task_context_summary
    assert "飞书云文档" in spec.task_context_summary
    # VOC context in reply must not trigger voc_insight routing
    assert spec.task_spec.get("requires_voc_insight") is False
    assert "voc_insight" not in [n.skill_id for n in spec.nodes]


def test_feishu_vague_message_no_entry(tmp_path: Path) -> None:
    """A vague message after a Feishu prefix ('处理一下') matches no task keywords
    and must not enter agent_system."""
    root = _create_project_with_non_voc_skills(tmp_path)
    feishu_msg = '[Replying to: "用户洞察：Q1复购率下降"]\n把这份文档处理一下'
    result = maybe_run_agent_system_from_message(
        feishu_msg,
        parent_agent=FakeParentAgent(),
        root_dir=root,
    )
    assert result is None, "vague message after Feishu prefix should not enter agent_system"


def test_run_conversation_invokes_agent_system_bridge(monkeypatch) -> None:
    from run_agent import AIAgent

    calls: list[dict] = []

    def fake_bridge(user_message, *, parent_agent, task_id=None, root_dir=None):
        assert parent_agent._execution_thread_id is not None
        calls.append(
            {
                "user_message": user_message,
                "parent_agent": parent_agent,
                "task_id": task_id,
                "root_dir": root_dir,
            }
        )
        return {
            "final_response": "桥接流程已执行",
            "agent_system_status": "completed",
            "agent_system_result": {"run_id": "Run_test"},
        }

    monkeypatch.setattr(
        "agent_system.cli_bridge.maybe_run_agent_system_from_message",
        fake_bridge,
    )
    agent = AIAgent(
        model="test-model",
        api_key="test-key",
        base_url="http://example.test/v1",
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        enabled_toolsets=[],
    )

    result = agent.run_conversation("请运行 agent_system pipeline_id=dashboard_flow")

    assert result["final_response"] == "桥接流程已执行"
    assert result["completed"] is True
    assert result["api_calls"] == 0
    assert result["agent_system_status"] == "completed"
    assert calls[0]["parent_agent"] is agent
