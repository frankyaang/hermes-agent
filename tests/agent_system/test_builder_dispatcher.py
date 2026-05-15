import json
from types import SimpleNamespace

from agent_system import builder_dispatcher as dispatcher


def _agent(**overrides):
    values = {
        "platform": "feishu",
        "_gateway_session_key": None,
        "_user_id": None,
        "_chat_id": None,
        "_thread_id": None,
        "session_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _state_files(project_root):
    return sorted((project_root / "temp").glob("skill_creation_*.json"))


def test_gateway_session_key_creates_isolated_state_files(tmp_path):
    agent_a = _agent(
        _gateway_session_key="feishu:chat-a:user-a",
        _user_id="user-a",
        _chat_id="chat-a",
    )
    agent_b = _agent(
        _gateway_session_key="feishu:chat-b:user-b",
        _user_id="user-b",
        _chat_id="chat-b",
    )

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent_a, project_root=tmp_path
    )
    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent_b, project_root=tmp_path
    )

    files = _state_files(tmp_path)
    assert len(files) == 2
    assert files[0].name != files[1].name
    assert all("default_default" not in path.name for path in files)

    states = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    assert {state["state_identity_source"] for state in states} == {
        "gateway_session_key"
    }


def test_other_session_is_not_intercepted_when_one_session_is_active(tmp_path):
    active_agent = _agent(
        _gateway_session_key="feishu:active:user-a",
        _user_id="user-a",
        _chat_id="chat-a",
    )
    other_agent = _agent(
        _gateway_session_key="feishu:other:user-b",
        _user_id="user-b",
        _chat_id="chat-b",
    )

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=active_agent, project_root=tmp_path
    )

    result = dispatcher.maybe_handle_builder_mode(
        "帮我总结一下这段话", parent_agent=other_agent, project_root=tmp_path
    )

    assert result is None


def test_same_session_continues_builder_state_machine(tmp_path, monkeypatch):
    active_agent = _agent(
        _gateway_session_key="feishu:active:user-a",
        _user_id="user-a",
        _chat_id="chat-a",
    )

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=active_agent, project_root=tmp_path
    )

    def fake_dispatch(state_path, user_message, parent_agent):
        return dispatcher._final_response(f"continued:{user_message}:{state_path.name}")

    monkeypatch.setattr(dispatcher, "_dispatch_to_state_machine", fake_dispatch)

    result = dispatcher.maybe_handle_builder_mode(
        "我要创建一个周报评审技能",
        parent_agent=active_agent,
        project_root=tmp_path,
    )

    assert result is not None
    assert "continued:我要创建一个周报评审技能" in result["final_response"]


def test_feishu_reply_quote_exit_hint_does_not_exit_mode(tmp_path, monkeypatch):
    active_agent = _agent(
        _gateway_session_key="feishu:active:user-a",
        _user_id="user-a",
        _chat_id="chat-a",
    )
    state_path = dispatcher._state_file_path_for_agent(tmp_path, active_agent)

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=active_agent, project_root=tmp_path
    )

    def fake_dispatch(state_path, user_message, parent_agent):
        return dispatcher._final_response(f"continued:{user_message}:{state_path.name}")

    monkeypatch.setattr(dispatcher, "_dispatch_to_state_machine", fake_dispatch)

    feishu_reply = (
        '[Replying to: "🐎 深度养马模式已启动\n'
        "本模式用于让 Hermes 沉淀新能力。随时可说【退出深度养马模式】结束。\n"
        '回复数字（1-6）或直接描述。"]\n\n'
        "[何春] 我需要做一个完整的定量调研项目"
    )

    result = dispatcher.maybe_handle_builder_mode(
        feishu_reply,
        parent_agent=active_agent,
        project_root=tmp_path,
    )

    assert result is not None
    assert state_path.exists()
    assert "已退出深度养马模式" not in result["final_response"]
    assert "continued:[何春] 我需要做一个完整的定量调研项目" in result["final_response"]


def test_exit_phrase_inside_long_text_does_not_exit_mode(tmp_path, monkeypatch):
    active_agent = _agent(
        _gateway_session_key="feishu:active:user-a",
        _user_id="user-a",
        _chat_id="chat-a",
    )
    state_path = dispatcher._state_file_path_for_agent(tmp_path, active_agent)

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=active_agent, project_root=tmp_path
    )

    def fake_dispatch(state_path, user_message, parent_agent):
        return dispatcher._final_response(f"continued:{user_message}:{state_path.name}")

    monkeypatch.setattr(dispatcher, "_dispatch_to_state_machine", fake_dispatch)

    result = dispatcher.maybe_handle_builder_mode(
        "我看到提示里说可以退出深度养马模式，但我现在要继续完善需求",
        parent_agent=active_agent,
        project_root=tmp_path,
    )

    assert result is not None
    assert state_path.exists()
    assert "已退出深度养马模式" not in result["final_response"]
    assert "continued:我看到提示里说可以退出深度养马模式" in result["final_response"]


def test_exit_only_removes_current_session_state(tmp_path):
    agent_a = _agent(
        _gateway_session_key="feishu:chat-a:user-a",
        _user_id="user-a",
        _chat_id="chat-a",
    )
    agent_b = _agent(
        _gateway_session_key="feishu:chat-b:user-b",
        _user_id="user-b",
        _chat_id="chat-b",
    )
    path_a = dispatcher._state_file_path_for_agent(tmp_path, agent_a)
    path_b = dispatcher._state_file_path_for_agent(tmp_path, agent_b)

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent_a, project_root=tmp_path
    )
    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent_b, project_root=tmp_path
    )

    dispatcher.maybe_handle_builder_mode(
        "退出深度养马模式", parent_agent=agent_a, project_root=tmp_path
    )

    assert not path_a.exists()
    assert path_b.exists()


def test_exit_command_allows_leading_speaker_prefix(tmp_path):
    agent = _agent(
        _gateway_session_key="feishu:chat-a:user-a",
        _user_id="user-a",
        _chat_id="chat-a",
    )
    path = dispatcher._state_file_path_for_agent(tmp_path, agent)

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent, project_root=tmp_path
    )

    dispatcher.maybe_handle_builder_mode(
        "[何春] 退出深度养马模式", parent_agent=agent, project_root=tmp_path
    )

    assert not path.exists()


def test_private_agent_ids_are_used_before_default(tmp_path):
    agent = _agent(
        _user_id="user-private",
        _chat_id="chat-private",
        _thread_id="thread-private",
    )

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent, project_root=tmp_path
    )

    files = _state_files(tmp_path)
    assert len(files) == 1
    assert "default_default" not in files[0].name
    assert "chat-private" in files[0].name
    assert "thread-private" in files[0].name
    assert "user-private" in files[0].name


def test_anonymous_agent_never_produces_default_default_filename(tmp_path):
    """An agent with NO session identifiers must not produce default_default.json.

    The worst-case fallback produces skill_creation_default.json (one "default"),
    not skill_creation_default_default.json (which would happen if channel_id
    were incorrectly appended to the state identity).
    """
    anon_agent = _agent(
        platform=None,
        _gateway_session_key=None,
        _user_id=None,
        _chat_id=None,
        _thread_id=None,
        session_id=None,
    )

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=anon_agent, project_root=tmp_path
    )

    files = _state_files(tmp_path)
    assert len(files) == 1
    assert "default_default" not in files[0].name
