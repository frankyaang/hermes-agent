from hermes_sdk import HermesMemoryManager


memory_manager = HermesMemoryManager(project_name="agent_system")


user_example = memory_manager.create_user(
    user_id="user_A_example",
    display_name="用户A（示例）",
    description="示例用户，用于测试对话记忆和偏好",
)


memory_manager.initialize_private_memory(user_id="user_A_example")


memory_manager.update_user_preferences(
    user_id="user_A_example",
    preferences={
        "preferred_skills": [
            "voc_insight",
            "ops_dashboard",
            "briefing",
        ],
        "output_style": "detailed",
        "report_format": "dashboard",
    },
)


memory_manager.add_memory(
    user_id="user_A_example",
    memory_id="example_mem_001",
    content="示例对话内容，占位用于测试对话召回和匹配",
    timestamp="2026-04-23T22:00:00",
)


if __name__ == "__main__":
    memory_manager.list_users()
    memory_manager.list_user_memory(user_id="user_A_example")
    memory_manager.get_user_preferences(user_id="user_A_example")
