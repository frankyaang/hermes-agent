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
