from hermes_sdk import HermesSchedulerManager


scheduler_manager = HermesSchedulerManager(project_name="agent_system")


main_scheduler = scheduler_manager.create_scheduler(
    name="main_scheduler",
    display_name="主调度器",
    description="负责洞察流程、看板流程和网页流程的任务分配、监督、异常处理和决策日志",
    supervised_modules=["experts", "skills"],
    exception_handling="default_strategy",
    decision_logging=True,
)


routes = [
    {
        "pipeline_id": "insight_flow",
        "pipeline_name": "洞察流程",
        "priority": "normal",
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
        "pipeline_id": "insight_flow",
        "pipeline_name": "洞察流程",
        "priority": "normal",
        "step": "key_node_completion",
        "node": "briefing",
        "display_name": "过程汇报",
        "trigger": ["voc_insight"],
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
        "user_gate": False,
        "optional": True,
    },
    {
        "pipeline_id": "dashboard_flow",
        "pipeline_name": "看板流程",
        "priority": "high",
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
        "priority": "high",
        "step": 2,
        "node": "ops_dashboard",
        "display_name": "运营看板",
        "depends_on": ["voc_insight"],
        "constraints": {
            "input_type": "用户洞察结论",
            "output_type": "产品运营报告与Dashboard结构",
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
    {
        "pipeline_id": "dashboard_flow",
        "pipeline_name": "看板流程",
        "priority": "high",
        "step": "key_node_completion",
        "node": "briefing",
        "display_name": "过程汇报",
        "trigger": ["ops_dashboard"],
        "constraints": {
            "input_type": "产品运营报告与Dashboard结构",
            "output_type": "过程汇报",
            "max_runtime": 90,
        },
        "supervision": {
            "scheduler_monitor": True,
            "expert_required": False,
            "primary_expert": None,
            "secondary_experts": [],
        },
        "user_gate": False,
        "optional": True,
    },
    {
        "pipeline_id": "html_flow",
        "pipeline_name": "网页流程",
        "priority": "high",
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
        "pipeline_id": "html_flow",
        "pipeline_name": "网页流程",
        "priority": "high",
        "step": 2,
        "node": "ops_dashboard",
        "display_name": "运营看板",
        "depends_on": ["voc_insight"],
        "constraints": {
            "input_type": "用户洞察结论",
            "output_type": "产品运营报告与Dashboard结构",
            "max_runtime": 180,
        },
        "supervision": {
            "scheduler_monitor": True,
            "expert_required": True,
            "primary_expert": "ops_expert",
            "secondary_experts": ["user_analyst"],
        },
        "user_gate": True,
    },
    {
        "pipeline_id": "html_flow",
        "pipeline_name": "网页流程",
        "priority": "high",
        "step": 3,
        "node": "dashboard_html",
        "display_name": "看板渲染",
        "depends_on": ["ops_dashboard"],
        "constraints": {
            "input_type": "产品运营报告与Dashboard结构",
            "output_type": "HTML/PDF",
            "max_runtime": 60,
        },
        "supervision": {
            "scheduler_monitor": True,
            "expert_required": True,
            "primary_expert": "render_expert",
            "secondary_experts": [],
        },
        "user_gate": False,
        "final_output": True,
    },
    {
        "pipeline_id": "html_flow",
        "pipeline_name": "网页流程",
        "priority": "high",
        "step": "quality_gate",
        "node": "audit",
        "display_name": "核查",
        "depends_on": ["dashboard_html"],
        "constraints": {
            "input_type": "运营看板输出与渲染结果",
            "output_type": "核查结论",
            "max_runtime": 120,
        },
        "supervision": {
            "scheduler_monitor": True,
            "expert_required": True,
            "primary_expert": "audit_expert",
            "secondary_experts": ["ops_expert"],
        },
        "user_gate": True,
        "optional": True,
    },
]


scheduler_manager.initialize_routes(
    scheduler_name=main_scheduler.name,
    pipelines=routes,
)


if __name__ == "__main__":
    scheduler_manager.list_schedulers()
    scheduler_manager.list_routes(scheduler_name=main_scheduler.name)
