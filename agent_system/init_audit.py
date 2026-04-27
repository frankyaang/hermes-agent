import datetime

from hermes_sdk import HermesAuditManager


audit_manager = HermesAuditManager(project_name="agent_system")


def generate_example_id(prefix: str = "TASK") -> str:
    timestamp = datetime.datetime(2026, 4, 23, 22, 0, 0).strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{timestamp}_example"


example_log_entry = {
    "generation_id": generate_example_id(),
    "module": "ops_dashboard",
    "display_name": "运营看板",
    "step": "dashboard_generation",
    "status": "success",
    "input": {"data_type": "用户洞察结论", "content": "示例输入内容"},
    "output": {
        "data_type": "产品运营报告与Dashboard结构",
        "content": "示例输出结果",
    },
    "expert_feedback": {
        "primary": "ops_expert",
        "secondary": ["user_analyst"],
    },
    "user_gate": True,
    "scheduler_monitor": True,
    "errors": [],
}


audit_manager.save_log(example_log_entry)


if __name__ == "__main__":
    audit_manager.list_logs()
    audit_manager.get_log(example_log_entry["generation_id"])
