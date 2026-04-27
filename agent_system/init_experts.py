from hermes_sdk import HermesExpertManager


expert_manager = HermesExpertManager(project_name="agent_system")


user_analyst = expert_manager.create_expert(
    name="user_analyst",
    display_name="用户分析专家",
    description="负责用户洞察、VOC分析、竞品反馈和质量风险判断",
    skills=[
        "voc_insight",
        "superpowers",
        "briefing",
    ],
    private_memory=True,
)


ops_expert = expert_manager.create_expert(
    name="ops_expert",
    display_name="运营专家",
    description="负责产品运营报告、Dashboard结构和运营动作建议",
    skills=[
        "ops_dashboard",
        "superpowers",
        "briefing",
    ],
    private_memory=True,
)


render_expert = expert_manager.create_expert(
    name="render_expert",
    display_name="渲染专家",
    description="负责HTML/PDF呈现质量，确保渲染层不改写业务内容",
    skills=[
        "dashboard_html",
        "briefing",
    ],
    private_memory=True,
)


audit_expert = expert_manager.create_expert(
    name="audit_expert",
    display_name="核查专家",
    description="负责交付前质量检查、字段完整性和审计追踪",
    skills=[
        "audit",
        "superpowers",
    ],
    private_memory=True,
)


for expert in [user_analyst, ops_expert, render_expert, audit_expert]:
    expert_manager.initialize_private_memory(expert.name)

expert_manager.create_pipeline(
    expert_name=user_analyst.name,
    pipeline_nodes=[
        {
            "step": 1,
            "node": "voc_insight",
            "user_gate": True,
            "primary_expert": "user_analyst",
            "secondary_experts": ["ops_expert"],
            "input_type": "VOC、评论、竞品和质量反馈",
            "output_type": "用户洞察结论",
            "max_runtime": 300,
        }
    ],
)

expert_manager.create_pipeline(
    expert_name=ops_expert.name,
    pipeline_nodes=[
        {
            "step": 2,
            "node": "ops_dashboard",
            "user_gate": True,
            "primary_expert": "ops_expert",
            "secondary_experts": ["user_analyst"],
            "input_type": "用户洞察结论",
            "output_type": "产品运营报告与Dashboard结构",
            "max_runtime": 180,
        }
    ],
)

expert_manager.create_pipeline(
    expert_name=render_expert.name,
    pipeline_nodes=[
        {
            "step": 3,
            "node": "dashboard_html",
            "user_gate": False,
            "primary_expert": "render_expert",
            "secondary_experts": [],
            "input_type": "产品运营报告与Dashboard结构",
            "output_type": "HTML/PDF",
            "max_runtime": 60,
        }
    ],
)

expert_manager.create_pipeline(
    expert_name=audit_expert.name,
    pipeline_nodes=[
        {
            "step": 4,
            "node": "audit",
            "user_gate": True,
            "primary_expert": "audit_expert",
            "secondary_experts": ["ops_expert"],
            "input_type": "运营看板输出与渲染结果",
            "output_type": "核查结论",
            "max_runtime": 120,
        }
    ],
)


if __name__ == "__main__":
    expert_manager.list_experts()
