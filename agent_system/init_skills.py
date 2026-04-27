from hermes_sdk import HermesSkillManager


skill_manager = HermesSkillManager(project_name="agent_system")


voc_insight_skill = skill_manager.create_skill(
    name="voc_insight",
    display_name="用户洞察",
    description="分析VOC、评论、竞品和质量反馈，输出用户洞察结论",
    type="analysis",
    pipeline="voc_insight_pipeline",
    private_memory=True,
)


ops_dashboard_skill = skill_manager.create_skill(
    name="ops_dashboard",
    display_name="运营看板",
    description="生成产品运营报告、Dashboard信息架构、关键指标表格和行动建议",
    type="report_generation",
    pipeline="ops_dashboard_pipeline",
    private_memory=True,
)


dashboard_html_skill = skill_manager.create_skill(
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


briefing_skill = skill_manager.create_skill(
    name="briefing",
    display_name="过程汇报",
    description="关键节点完成后生成自然语言过程汇报，服务所有主流程节点",
    type="status_report",
    pipeline="briefing_pipeline",
    private_memory=True,
)


audit_skill = skill_manager.create_skill(
    name="audit",
    display_name="核查",
    description="检查结论一致性、字段完整性、流程状态和审计日志",
    type="audit",
    pipeline="audit_pipeline",
    private_memory=True,
)


if __name__ == "__main__":
    skill_manager.list_skills()
