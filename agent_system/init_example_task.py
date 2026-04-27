# Agent系统示例任务初始化模板
# Codex + Hermes环境可直接运行

import datetime

from hermes_sdk import (
    HermesAuditManager,
    HermesExpertManager,
    HermesMemoryManager,
    HermesSkillManager,
)


def main() -> None:
    # -----------------------------
    # 初始化Skill管理器
    # -----------------------------
    skill_manager = HermesSkillManager(project_name="agent_system")

    voc_insight = skill_manager.create_skill(
        name="voc_insight",
        display_name="用户洞察",
        description="分析VOC、评论、竞品和质量反馈，输出用户洞察结论",
        type="analysis",
        pipeline="voc_insight_pipeline",
        private_memory=True,
    )

    ops_dashboard = skill_manager.create_skill(
        name="ops_dashboard",
        display_name="运营看板",
        description="生成产品运营报告、Dashboard信息架构、关键指标表格和行动建议",
        type="report_generation",
        pipeline="ops_dashboard_pipeline",
        private_memory=True,
    )

    dashboard_html = skill_manager.create_skill(
        name="dashboard_html",
        display_name="看板渲染",
        description="消费运营看板结构化输出并渲染HTML/PDF，不改写业务内容",
        type="ui_render",
        pipeline="dashboard_html_pipeline",
        private_memory=True,
    )

    superpowers = skill_manager.create_skill(
        name="superpowers",
        display_name="思考辅助",
        description="辅助专家进行任务理解、方案判断、冲突复核和质量检查",
        type="analysis_assist",
        pipeline="superpowers_pipeline",
        private_memory=True,
    )

    briefing = skill_manager.create_skill(
        name="briefing",
        display_name="过程汇报",
        description="关键节点完成后生成自然语言过程汇报，服务所有主流程节点",
        type="status_report",
        pipeline="briefing_pipeline",
        private_memory=True,
    )

    audit = skill_manager.create_skill(
        name="audit",
        display_name="核查",
        description="检查结论一致性、字段完整性、流程状态和审计日志",
        type="audit",
        pipeline="audit_pipeline",
        private_memory=True,
    )

    # -----------------------------
    # 初始化专家管理器
    # -----------------------------
    expert_manager = HermesExpertManager(project_name="agent_system")

    user_analyst = expert_manager.create_expert(
        name="user_analyst",
        display_name="用户分析专家",
        description="负责用户洞察、VOC分析、竞品反馈和质量风险判断",
        skills=[voc_insight.name, superpowers.name, briefing.name],
        private_memory=True,
    )

    ops_expert = expert_manager.create_expert(
        name="ops_expert",
        display_name="运营专家",
        description="负责产品运营报告、Dashboard结构和运营动作建议",
        skills=[ops_dashboard.name, superpowers.name, briefing.name],
        private_memory=True,
    )

    render_expert = expert_manager.create_expert(
        name="render_expert",
        display_name="渲染专家",
        description="负责HTML/PDF呈现质量，确保渲染层不改写业务内容",
        skills=[dashboard_html.name, briefing.name],
        private_memory=True,
    )

    audit_expert = expert_manager.create_expert(
        name="audit_expert",
        display_name="核查专家",
        description="负责交付前质量检查、字段完整性和审计追踪",
        skills=[audit.name, superpowers.name],
        private_memory=True,
    )

    for expert in [user_analyst, ops_expert, render_expert, audit_expert]:
        expert_manager.initialize_private_memory(expert.name)

    # 初始化专家Pipeline节点
    expert_manager.create_pipeline(
        expert_name=user_analyst.name,
        pipeline_nodes=[
            {
                "step": 1,
                "node": voc_insight.name,
                "user_gate": True,
                "primary_expert": user_analyst.name,
                "secondary_experts": [ops_expert.name],
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
                "node": ops_dashboard.name,
                "user_gate": True,
                "primary_expert": ops_expert.name,
                "secondary_experts": [user_analyst.name],
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
                "node": dashboard_html.name,
                "user_gate": False,
                "primary_expert": render_expert.name,
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
                "node": audit.name,
                "user_gate": True,
                "primary_expert": audit_expert.name,
                "secondary_experts": [ops_expert.name],
                "input_type": "运营看板输出与渲染结果",
                "output_type": "核查结论",
                "max_runtime": 120,
            }
        ],
    )

    # -----------------------------
    # 初始化用户/个体差异化模块
    # -----------------------------
    memory_manager = HermesMemoryManager(project_name="agent_system")

    user_A = memory_manager.create_user(
        user_id="user_A_example",
        display_name="用户A（示例）",
        description="示例用户，用于测试对话记忆和偏好",
    )

    memory_manager.initialize_private_memory(user_A.user_id)

    memory_manager.update_user_preferences(
        user_id=user_A.user_id,
        preferences={
            "preferred_skills": [
                voc_insight.name,
                ops_dashboard.name,
                briefing.name,
            ],
            "output_style": "detailed",
            "report_format": "dashboard",
        },
    )

    memory_manager.add_memory(
        user_id=user_A.user_id,
        memory_id="example_mem_001",
        content="示例对话内容，占位用于测试产品运营Dashboard链路召回和匹配",
        timestamp=datetime.datetime.now().isoformat(),
    )

    # -----------------------------
    # 初始化核查模块
    # -----------------------------
    audit_manager = HermesAuditManager(project_name="agent_system")

    example_log = {
        "generation_id": "TASK_20260423_dashboard",
        "module": ops_dashboard.name,
        "display_name": "运营看板",
        "step": "dashboard_generation",
        "status": "success",
        "input": {"data_type": "用户洞察结论", "content": "示例输入内容"},
        "output": {
            "data_type": "产品运营报告与Dashboard结构",
            "content": "示例输出结果",
        },
        "expert_feedback": {
            "primary": ops_expert.name,
            "secondary": [user_analyst.name],
        },
        "user_gate": True,
        "scheduler_monitor": True,
        "errors": [],
    }

    audit_manager.save_log(example_log)

    # -----------------------------
    # 验证
    # -----------------------------
    skill_manager.list_skills()
    expert_manager.list_experts()
    memory_manager.list_users()
    memory_manager.list_user_memory(user_A.user_id)
    audit_manager.list_logs()


if __name__ == "__main__":
    main()
