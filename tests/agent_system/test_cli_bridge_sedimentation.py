"""Tests for cli_bridge sedimentation fixes — identity, enums, pending on failure."""
from __future__ import annotations
import json
from gateway.session_context import set_session_vars, clear_session_vars


def _make_registry(tmp_path, user_id, product_line_ids):
    import yaml
    reg_dir = tmp_path / "knowledge"
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / "users.yaml").write_text(yaml.safe_dump({"users": [{
        "user_id": user_id,
        "product_line_ids": product_line_ids,
        "default_product_line_id": product_line_ids[0] if product_line_ids else "",
        "finance_product_line_ids": [],
        "role": "business_user",
        "is_admin": False,
    }]}), encoding="utf-8")


def test_get_product_line_uses_feishu_session(tmp_path, monkeypatch):
    _make_registry(tmp_path, "feishu:ou_test", ["deebot"])
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    tokens = set_session_vars(platform="feishu", user_id="ou_test", chat_id="oc_chat")
    try:
        from agent_system import cli_bridge
        import importlib
        importlib.reload(cli_bridge)
        result = cli_bridge._get_user_default_product_line_id()
    finally:
        clear_session_vars(tokens)
    assert result == "deebot"


def test_get_product_line_empty_for_unknown_feishu_user(tmp_path, monkeypatch):
    _make_registry(tmp_path, "feishu:ou_known", ["deebot"])
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    tokens = set_session_vars(platform="feishu", user_id="ou_nobody", chat_id="oc_chat")
    try:
        from agent_system import cli_bridge
        import importlib
        importlib.reload(cli_bridge)
        result = cli_bridge._get_user_default_product_line_id()
    finally:
        clear_session_vars(tokens)
    assert result == ""


def test_auto_sedate_uses_valid_confidence_enum(monkeypatch):
    captured = []

    def fake_delegate(goal, context, role, parent_agent):
        captured.append(goal)
        return json.dumps({"sedimented": 0})

    monkeypatch.setattr("agent_system.cli_bridge._knowledge_toolset_available", lambda: True)
    monkeypatch.setattr("agent_system.cli_bridge._get_user_default_product_line_id", lambda: "deebot")
    monkeypatch.setattr("tools.delegate_tool.delegate_task", fake_delegate)

    from agent_system.cli_bridge import _auto_sedate_knowledge
    _auto_sedate_knowledge(
        result={"status": "completed", "run_id": "run-1"},
        final_response="Business result", parent_agent=None, task_id="t1",
    )

    assert len(captured) == 1
    goal = captured[0]
    assert "confidence='high'" not in goal
    assert "confidence='medium'" not in goal
    assert "unverified" in goal or "draft" in goal


def test_auto_sedate_no_business_fact_knowledge_type(monkeypatch):
    captured = []

    def fake_delegate(goal, context, role, parent_agent):
        captured.append(goal)
        return json.dumps({"sedimented": 0})

    monkeypatch.setattr("agent_system.cli_bridge._knowledge_toolset_available", lambda: True)
    monkeypatch.setattr("agent_system.cli_bridge._get_user_default_product_line_id", lambda: "deebot")
    monkeypatch.setattr("tools.delegate_tool.delegate_task", fake_delegate)

    from agent_system.cli_bridge import _auto_sedate_knowledge
    _auto_sedate_knowledge(
        result={"status": "completed", "run_id": "run-2"},
        final_response="Business result", parent_agent=None, task_id="t2",
    )

    assert "knowledge_type='business_fact'" not in captured[0]
    assert "business_fact" not in captured[0]


def test_auto_sedate_permission_denied_marks_pending_terminal_state(tmp_path, monkeypatch):
    def fake_delegate(goal, context, role, parent_agent):
        return json.dumps({
            "error": "permission_denied",
            "reason": "product_line_not_authorized",
            "next_action": "Add deebot permission",
        })

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr("agent_system.cli_bridge._knowledge_toolset_available", lambda: True)
    monkeypatch.setattr("agent_system.cli_bridge._get_user_default_product_line_id", lambda: "deebot")
    monkeypatch.setattr("tools.delegate_tool.delegate_task", fake_delegate)

    from agent_system.cli_bridge import _auto_sedate_knowledge
    _auto_sedate_knowledge(
        result={"status": "completed", "run_id": "run-pending"},
        final_response="Business result", parent_agent=None, task_id="t3",
    )

    record = json.loads((tmp_path / "knowledge" / "pending_captures.jsonl").read_text())
    assert record["terminal_state"] == "pending_created"
    assert record["status"] == "pending"
