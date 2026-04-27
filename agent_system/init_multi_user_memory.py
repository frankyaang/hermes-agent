import datetime
import math
from threading import Lock

from hermes_sdk import HermesMemoryManager


memory_manager = HermesMemoryManager(project_name="agent_system")
memory_lock = Lock()


DECAY_PARAMS = {
    "planning": 0.01,
    "operation": 0.015,
    "delivery": 0.02,
    "commercial": 0.03,
}
MAX_VERSIONS = 5


def apply_time_decay(memory_entry: dict, decay_lambda: float = 0.01) -> dict:
    time_diff = (
        datetime.datetime.now()
        - datetime.datetime.fromisoformat(memory_entry["timestamp"])
    ).days
    memory_entry["weight"] = math.exp(-decay_lambda * max(time_diff, 0))
    return memory_entry


def embed(text: str) -> dict[str, float]:
    vector: dict[str, float] = {}
    for character in text.lower():
        if character.isspace():
            continue
        vector[character] = vector.get(character, 0.0) + 1.0
    return vector


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0

    keys = set(left) | set(right)
    dot_product = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def save_memory_version(user_id: str, memory_entry: dict) -> None:
    memory_entry["version"] = memory_entry.get("version", 0) + 1
    memory_manager.add_memory(user_id=user_id, **memory_entry)
    memory_manager.log_memory_operation(
        user_id=user_id,
        memory_id=memory_entry["memory_id"],
        action_type="update",
        metadata={"version": memory_entry["version"]},
    )

    archived_paths = memory_manager.archive_memory_versions(
        user_id=user_id,
        memory_id=memory_entry["memory_id"],
        keep_latest=MAX_VERSIONS,
    )
    for archived_path in archived_paths:
        memory_manager.log_memory_operation(
            user_id=user_id,
            memory_id=memory_entry["memory_id"],
            action_type="archive",
            metadata={"path": str(archived_path)},
        )


def recall_memory(
    user_id: str,
    context_vector: dict[str, float],
    top_n: int = 5,
    similarity_threshold: float = 0.75,
    decay_lambda: float = DECAY_PARAMS["planning"],
) -> list[dict]:
    memories = memory_manager.list_user_memory(user_id)
    results: list[tuple[dict, float]] = []

    for memory in memories:
        similarity = cosine_similarity(context_vector, embed(memory["content"]))
        decayed_memory = apply_time_decay(memory, decay_lambda=decay_lambda)
        score = similarity * decayed_memory["weight"]
        if score >= similarity_threshold:
            decayed_memory["recall_score"] = score
            results.append((decayed_memory, score))

    results.sort(key=lambda item: item[1], reverse=True)
    recalled = [item[0] for item in results[:top_n]]
    for memory in recalled:
        memory_manager.log_memory_operation(
            user_id=user_id,
            memory_id=memory["memory_id"],
            action_type="recall",
            metadata={"score": memory["recall_score"]},
        )
    return recalled


def check_user_permission(requesting_user_id: str, target_user_id: str) -> bool:
    return requesting_user_id == target_user_id


def safe_add_memory(user_id: str, memory_entry: dict) -> None:
    with memory_lock:
        memory_manager.add_memory(user_id=user_id, **memory_entry)
        memory_manager.log_memory_operation(
            user_id=user_id,
            memory_id=memory_entry["memory_id"],
            action_type="add",
        )


def generate_humane_report(
    user_id: str,
    key_nodes_context: list[str],
) -> list[dict]:
    reports: list[dict] = []
    for context in key_nodes_context:
        recalled = recall_memory(user_id, embed(context), similarity_threshold=0.1)
        reports.append(
            {
                "context": context,
                "recalled_memories": recalled,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )
    return reports


def log_memory_operation(user_id: str, memory_id: str, action_type: str) -> dict:
    log_path = memory_manager.log_memory_operation(
        user_id=user_id,
        memory_id=memory_id,
        action_type=action_type,
    )
    return {
        "user_id": user_id,
        "memory_id": memory_id,
        "action": action_type,
        "path": str(log_path),
    }


def initialize_users() -> None:
    users = [
        {"user_id": "user_A", "display_name": "用户A"},
        {"user_id": "user_B", "display_name": "用户B"},
    ]

    for user in users:
        memory_manager.create_user(
            user_id=user["user_id"],
            display_name=user["display_name"],
        )
        memory_manager.initialize_private_memory(user["user_id"])
        memory_manager.update_user_preferences(
            user_id=user["user_id"],
            preferences={
                "preferred_skills": ["voc_insight", "ops_dashboard", "briefing"],
                "output_style": "detailed",
                "report_format": "dashboard",
            },
        )

        memory_entry = {
            "memory_id": f"{user['user_id']}_mem_001",
            "content": f"示例对话内容，用于{user['display_name']}测试",
            "timestamp": datetime.datetime.now().isoformat(),
            "module": "planning",
        }
        safe_add_memory(user_id=user["user_id"], memory_entry=memory_entry)
        save_memory_version(user["user_id"], memory_entry)


def main() -> None:
    initialize_users()

    report = generate_humane_report(
        "user_A",
        ["示例对话内容和VOC分析偏好，用于生成过程汇报"],
    )
    print("briefing_preview")
    print(report)

    permission = check_user_permission("user_A", "user_B")
    print(f"user_A_can_access_user_B={permission}")

    memory_manager.list_users()
    memory_manager.list_user_memory("user_A")
    memory_manager.get_user_preferences(user_id="user_A")


if __name__ == "__main__":
    main()
