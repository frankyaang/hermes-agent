import json
from types import SimpleNamespace

from agent_system import builder_dispatcher as dispatcher
from agent_system.experts.builder_expert.builder import (
    BUILDER_INTENTS,
    build_context_prefill,
    handle,
    recognize_intent,
)


def _agent(**overrides):
    values = {
        "platform": None,
        "_gateway_session_key": None,
        "_user_id": None,
        "_chat_id": None,
        "_thread_id": None,
        "session_id": None,
        "conversation_history": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _write_state(tmp_path, state):
    path = tmp_path / "skill_creation_test.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_state(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _intake_state(**intake_overrides):
    intake = {"_current_question": "Q1"}
    intake.update(intake_overrides)
    return {
        "stage": "INTAKE",
        "state_identity": "test",
        "intake": intake,
        "architect_proposal": None,
        "drafts": {},
        "validation": {},
        "dry_run": {},
        "trial_run": {},
        "history": [],
    }


def test_recognize_intent_returns_documented_labels():
    samples = [
        "业务目标是什么意思？",
        "你建议怎么填？",
        "帮我确认一下你的理解",
        "修改业务目标",
        "回到上一步改一下",
        "当前填了什么？",
        "继续",
        "业务目标是降低售后投诉",
    ]

    for sample in samples:
        assert recognize_intent(sample) in BUILDER_INTENTS

    revise = recognize_intent("业务目标改成提升质检准确率", current_field="scenario")
    assert revise == "revise_previous"
    assert revise.target == "business_goal"
    assert revise.target_type == "field"

    go_back = recognize_intent(
        "回到上一步改一下",
        current_stage="INTAKE",
        current_field="input_type",
        previous_field="scenario",
    )
    assert go_back == "go_back"
    assert go_back.target == "scenario"
    assert go_back.target_type == "field"


def test_intake_definition_question_does_not_advance_or_write(tmp_path):
    state_path = _write_state(tmp_path, _intake_state(_current_question="Q1"))
    before = state_path.read_text(encoding="utf-8")

    response = handle("业务目标是什么意思？", state_path, _agent())

    assert "解释：业务目标" in response
    assert "不会记录为答案" in response
    assert state_path.read_text(encoding="utf-8") == before


def test_intake_advice_question_does_not_advance_or_write(tmp_path):
    state_path = _write_state(tmp_path, _intake_state(_current_question="Q2"))
    before = state_path.read_text(encoding="utf-8")

    response = handle("你建议怎么填？", state_path, _agent())

    assert "建议：典型使用场景" in response
    assert "原因" in response
    assert "确认是否采用" in response
    assert state_path.read_text(encoding="utf-8") == before


def test_go_back_previous_step_allows_overwrite_without_corrupting_fields(tmp_path):
    state_path = _write_state(
        tmp_path,
        _intake_state(
            _current_question="Q3",
            _user_intent="free_form",
            business_goal="降低售后投诉",
            scenario="每周一早上自动巡检",
        ),
    )

    response = handle("回到上一步改一下", state_path, _agent())
    state = _read_state(state_path)

    assert "已回到典型使用场景" in response
    assert "每周一早上自动巡检" in response
    assert state["stage"] == "INTAKE"
    assert state["intake"]["_current_question"] == "Q2"
    assert state["_pending_revision"]["field"] == "scenario"

    response = handle("用户在群里输入关键词时触发", state_path, _agent())
    state = _read_state(state_path)

    assert "已更新典型使用场景" in response
    assert state["intake"]["business_goal"] == "降低售后投诉"
    assert state["intake"]["scenario"] == "用户在群里输入关键词时触发"
    assert state["intake"]["_current_question"] == "Q3"
    assert "_pending_revision" not in state


def test_show_current_returns_summary_without_advance(tmp_path):
    state_path = _write_state(
        tmp_path,
        _intake_state(
            _current_question="Q3",
            _user_intent="data_analysis",
            business_goal="降低售后投诉",
            scenario="每周一早上自动巡检",
        ),
    )
    before = state_path.read_text(encoding="utf-8")

    response = handle("目前已经填了什么？", state_path, _agent())

    assert "当前已填写内容" in response
    assert "降低售后投诉" in response
    assert "每周一早上自动巡检" in response
    assert state_path.read_text(encoding="utf-8") == before


def test_deep_builder_entry_prefills_from_conversation_and_asks_missing_only(tmp_path):
    agent = _agent(
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "能力名称：售后质检雷达\n"
                    "业务目标：降低工单漏判\n"
                    "使用场景：每周一早上巡检\n"
                    "输入材料：售后工单\n"
                    "输出产物：异常清单"
                ),
            }
        ]
    )

    result = dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent, project_root=tmp_path
    )
    response = result["final_response"]
    state_path = dispatcher._state_file_path_for_agent(tmp_path, agent)
    state = _read_state(state_path)

    assert "我先从刚才对话里预填了一版养马卡" in response
    assert "已识别" in response
    assert "还缺" in response
    assert "执行流程" in response
    assert "请一步一步描述" in response
    assert "你想解决什么问题" not in response
    assert state["prefill"]["business_goal"] == {
        "value": "降低工单漏判",
        "source": "conversation_history",
        "confidence": "high",
    }
    assert state["intake"]["business_goal"] == "降低工单漏判"
    assert state["intake"]["scenario"] == "每周一早上巡检"
    assert state["intake"]["input_type"] == "售后工单"
    assert state["intake"]["output_type"] == "异常清单"
    assert state["intake"]["_current_question"] == "Q5"

    next_result = dispatcher.maybe_handle_builder_mode(
        "先读取工单，再识别异常，最后输出清单",
        parent_agent=agent,
        project_root=tmp_path,
    )
    next_state = _read_state(state_path)

    assert "必填项已收齐" in next_result["final_response"]
    assert next_state["intake"]["pipeline_description"] == "先读取工单，再识别异常，最后输出清单"
    assert next_state["intake"]["_current_question"] == "OPTIONAL"


def test_prefilled_field_can_be_overwritten_when_user_negates_it(tmp_path):
    agent = _agent(
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "能力名称：售后质检雷达\n"
                    "业务目标：降低工单漏判\n"
                    "使用场景：每周一早上巡检\n"
                    "输入材料：售后工单\n"
                    "输出产物：异常清单"
                ),
            }
        ]
    )
    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent, project_root=tmp_path
    )
    state_path = dispatcher._state_file_path_for_agent(tmp_path, agent)

    result = dispatcher.maybe_handle_builder_mode(
        "业务目标不是降低工单漏判，业务目标改成提升质检准确率",
        parent_agent=agent,
        project_root=tmp_path,
    )
    state = _read_state(state_path)

    assert "已更新业务目标" in result["final_response"]
    assert state["intake"]["business_goal"] == "提升质检准确率"
    assert state["prefill"]["business_goal"]["value"] == "提升质检准确率"
    assert state["prefill"]["business_goal"]["source"] == "user_override"
    assert state["intake"]["scenario"] == "每周一早上巡检"


def test_entry_without_context_uses_empty_intake_copy(tmp_path):
    agent = _agent()

    result = dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent, project_root=tmp_path
    )
    state = _read_state(dispatcher._state_file_path_for_agent(tmp_path, agent))

    assert "我们一起把这匹马养出来" in result["final_response"]
    assert state["intake"] == {"_current_question": "INTENT_CHOICE"}
    assert state["prefill"] == {}


def test_inline_revise_named_field_keeps_current_pointer_and_other_fields(tmp_path):
    state_path = _write_state(
        tmp_path,
        _intake_state(
            _current_question="Q4",
            _user_intent="free_form",
            business_goal="降低售后投诉",
            scenario="每周一早上自动巡检",
            input_type="售后工单",
        ),
    )

    response = handle("业务目标改成提升质检准确率", state_path, _agent())
    state = _read_state(state_path)

    assert "已更新业务目标" in response
    assert "原内容：降低售后投诉" in response
    assert state["intake"]["business_goal"] == "提升质检准确率"
    assert state["intake"]["input_type"] == "售后工单"
    assert state["intake"]["_current_question"] == "Q4"


def test_go_back_named_field_moves_pointer_to_that_field(tmp_path):
    state_path = _write_state(
        tmp_path,
        _intake_state(
            _current_question="Q4",
            _user_intent="free_form",
            business_goal="降低售后投诉",
            scenario="每周一早上自动巡检",
            input_type="售后工单",
        ),
    )

    response = handle("回到业务目标", state_path, _agent())
    state = _read_state(state_path)

    assert "已回到业务目标" in response
    assert "降低售后投诉" in response
    assert state["stage"] == "INTAKE"
    assert state["intake"]["_current_question"] == "Q1"
    assert state["_pending_revision"]["field"] == "business_goal"


def test_definition_can_target_prefill_extra_without_state_write(tmp_path):
    state = _intake_state(_current_question="Q5")
    state["prefill"] = {
        "judgment_criteria": {
            "value": "必须包含异常原因和负责人",
            "source": "conversation_history",
            "confidence": "high",
        }
    }
    state_path = _write_state(tmp_path, state)
    before = state_path.read_text(encoding="utf-8")

    response = handle("判断标准是什么意思？", state_path, _agent())

    assert "解释：判断标准" in response
    assert "怎样算结果可用" in response
    assert state_path.read_text(encoding="utf-8") == before


def test_context_prefill_reads_session_db_when_public_history_is_empty():
    class FakeSessionDB:
        def get_messages_as_conversation(self, session_id, include_ancestors=True):
            assert session_id == "session-1"
            assert include_ancestors is True
            return [
                {
                    "role": "user",
                    "content": (
                        "能力名称：交付风险雷达\n"
                        "业务目标：提前识别项目延期风险\n"
                        "执行流程：先读取周报，再识别延期信号，最后输出风险清单"
                    ),
                }
            ]

    prefill = build_context_prefill(
        _agent(session_id="session-1", conversation_history=[], _session_db=FakeSessionDB())
    )

    assert prefill["capability_candidate_name"]["value"] == "交付风险雷达"
    assert prefill["business_goal"]["value"] == "提前识别项目延期风险"
    assert prefill["execution_flow"]["source"] == "conversation_history"
    assert prefill["execution_flow"]["confidence"] == "high"


def test_context_prefill_returns_empty_without_usable_context():
    assert build_context_prefill(_agent()) == {}


def test_continue_after_existing_answer_skips_to_next_missing_field(tmp_path):
    state_path = _write_state(
        tmp_path,
        _intake_state(
            _current_question="Q1",
            _user_intent="free_form",
            business_goal="降低售后投诉",
        ),
    )

    response = handle("继续", state_path, _agent())
    state = _read_state(state_path)

    assert "业务目标已保留为：降低售后投诉" in response
    assert "这个能力什么时候被调用" in response
    assert state["intake"]["business_goal"] == "降低售后投诉"
    assert state["intake"]["_current_question"] == "Q2"


def test_confirm_understanding_not_misidentified_as_revise():
    """'不是很确认'类表达应识别为 confirm_understanding，不能是 revise_previous。"""
    cases = [
        "我不是很确认我的理解和你是不是一致",
        "我不确定我的理解和你是不是一致",
        "我这样理解对吗",
        "你是不是这个意思",
        "我们对齐一下理解",
    ]
    for text in cases:
        result = recognize_intent(text)
        assert result == "confirm_understanding", (
            f"{text!r} → {result!r}，期望 confirm_understanding"
        )


def test_explain_plus_confirm_not_revise():
    """'你能解释一下...我不是很确认...' 不能是 revise_previous。"""
    text = "你能解释一下这个吗？我不是很确认我的理解和你是不是一致"
    result = recognize_intent(text)
    assert result in ("confirm_understanding", "ask_definition"), (
        f"期望 confirm_understanding 或 ask_definition，实际得到 {result!r}"
    )
    assert result != "revise_previous"


def test_revise_with_explicit_rewrite_verb_still_works():
    """包含'改成'等明确改写动作词的表达仍应识别为 revise_previous。"""
    cases = [
        ("业务目标不是降低工单漏判，业务目标改成提升质检准确率", "revise_previous"),
        ("刚才那个目标不对，改成提升质检准确率", "revise_previous"),
        ("输入材料改为历史题库和调研主题", "revise_previous"),
    ]
    for text, expected in cases:
        result = recognize_intent(text)
        assert result == expected, f"{text!r} → {result!r}，期望 {expected}"


def test_natural_language_prefill_survey_project(tmp_path):
    """完整定量调研自然语言描述能抽取关键字段。"""
    survey_text = (
        "我需要一个能完整的定量调研项目；完整的意思是从有主题到分析结束；"
        "分析完成后的路径有两条：\n1、结束\n2、基于调研相关主题，交叉分析和洞察；\n"
        "【本次先完成第一条路径，单问卷的分析】\n"
        "我已经拥有一个1年前题库，需要根据每年产品的不同，变化和扩展题库，并生成问卷，"
        "同时能够基于问卷做系统的分析，分析结果要用于：产品规划、技术规划、考卷扩充、卖点识别等等；\n"
        "最终希望得到的结果是：\n"
        "进行调研需求收集——基于调研需求和目标，自动匹配当前题库——扩展或调整题库"
        "——选择合适的用户投放——分析问卷结果——形成报告"
    )
    agent = _agent(conversation_history=[{"role": "user", "content": survey_text}])

    result = dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent, project_root=tmp_path
    )
    response = result["final_response"]
    state_path = dispatcher._state_file_path_for_agent(tmp_path, agent)
    state = _read_state(state_path)

    prefill = state.get("prefill", {})
    intake = state.get("intake", {})

    assert "我先从刚才对话里预填了一版养马卡" in response, "首轮应提示预填内容"
    assert "还缺" in response, "应提示缺失字段"

    assert "business_goal" in prefill, "应能抽取 business_goal"
    assert "定量调研" in prefill["business_goal"]["value"]

    assert "execution_flow" in prefill or intake.get("pipeline_description"), (
        "应能抽取执行流程"
    )

    assert "open_questions" in prefill, "应能从【】中抽取待澄清问题"
    assert "单问卷" in prefill["open_questions"]["value"]

    # 已预填字段不应在首轮回复里再被追问
    assert "你想解决什么问题" not in response, "business_goal 已预填，不应再问"


def test_prefilled_survey_field_can_be_overwritten(tmp_path):
    """自然语言预填后，用户仍可用'业务目标改成...'覆盖业务目标。"""
    survey_text = (
        "我需要一个能完整的定量调研项目；完整的意思是从有主题到分析结束；"
        "我已经拥有一个1年前题库，分析结果要用于：产品规划、技术规划；\n"
        "最终希望得到的结果是：\n"
        "进行调研需求收集——扩展题库——分析问卷结果——形成报告"
    )
    agent = _agent(conversation_history=[{"role": "user", "content": survey_text}])

    dispatcher.maybe_handle_builder_mode(
        "启动深度养马模式", parent_agent=agent, project_root=tmp_path
    )
    state_path = dispatcher._state_file_path_for_agent(tmp_path, agent)

    result = dispatcher.maybe_handle_builder_mode(
        "业务目标不是做项目，业务目标改成提升问卷回收率",
        parent_agent=agent,
        project_root=tmp_path,
    )
    state = _read_state(state_path)

    assert "已更新业务目标" in result["final_response"]
    assert state["intake"]["business_goal"] == "提升问卷回收率"
    assert state["prefill"]["business_goal"]["source"] == "user_override"


def test_q5_reasked_flag_cleared_on_revise(tmp_path):
    """修改 pipeline_description 后，_q5_reasked flag 应被清除。"""
    state = _intake_state(
        _current_question="Q5",
        _user_intent="free_form",
        business_goal="降低售后投诉",
        scenario="每周一早上自动巡检",
        input_type="售后工单",
        output_type="异常清单",
        _q5_reasked=True,
    )
    state_path = _write_state(tmp_path, state)

    response = handle("执行流程改成先读取工单，然后处理，最后生成清单", state_path, _agent())
    updated = _read_state(state_path)

    assert "已更新执行流程" in response
    assert "_q5_reasked" not in updated.get("intake", {})


def test_q5_reasked_flag_cleared_on_pending_revision(tmp_path):
    """pending_revision 方式修改 pipeline_description 后，_q5_reasked 也应被清除。"""
    state = _intake_state(
        _current_question="Q5",
        _user_intent="free_form",
        business_goal="降低售后投诉",
        scenario="每周一早上自动巡检",
        input_type="售后工单",
        output_type="异常清单",
        pipeline_description="初版流程",
        _q5_reasked=True,
    )
    state["_pending_revision"] = {"field": "pipeline_description", "source": "go_back"}
    state_path = _write_state(tmp_path, state)

    handle("先读工单，再检测，最后写报告", state_path, _agent())
    updated = _read_state(state_path)

    assert "_q5_reasked" not in updated.get("intake", {})


def test_confirm_understanding_shows_prefill_note_for_medium_confidence(tmp_path):
    """当字段来自 natural_language / conversation_history 预填时，应提示来自对话预填。"""
    # _current_question="Q1" → current field = business_goal，与 prefill 字段一致
    state = _intake_state(_current_question="Q1", _user_intent="free_form")
    state["intake"]["business_goal"] = "完整定量调研"
    state["prefill"] = {
        "business_goal": {
            "value": "完整定量调研",
            "source": "natural_language",
            "confidence": "medium",
        }
    }
    state_path = _write_state(tmp_path, state)

    response = handle("你是不是这个意思", state_path, _agent())

    assert "对话预填" in response
    assert "完整定量调研" in response
    assert "本轮不会推进阶段" in response


def test_confirm_understanding_no_prefill_note_for_user_override(tmp_path):
    """来自 user_override 的字段不应出现'对话预填'提示。"""
    state = _intake_state(_current_question="Q1", _user_intent="free_form")
    state["intake"]["business_goal"] = "提升质检准确率"
    state["prefill"] = {
        "business_goal": {
            "value": "提升质检准确率",
            "source": "user_override",
            "confidence": "high",
        }
    }
    state_path = _write_state(tmp_path, state)

    response = handle("你是不是这个意思", state_path, _agent())

    assert "对话预填" not in response
    assert "提升质检准确率" in response


def test_natural_language_prefill_numbered_list_execution_flow():
    """编号列表格式（1、步骤A\n2、步骤B）应能抽取 execution_flow。"""
    from agent_system.experts.builder_expert.builder import _extract_natural_language_prefill

    text = (
        "我需要一个数据分析系统，处理流程如下：\n"
        "1、收集用户反馈数据\n"
        "2、清洗和分类数据\n"
        "3、生成分析报告\n"
        "4、推送给相关人员"
    )
    result = _extract_natural_language_prefill(text)

    assert "execution_flow" in result
    flow = result["execution_flow"]["value"]
    assert "收集用户反馈数据" in flow
    assert "生成分析报告" in flow
    assert " → " in flow


def test_natural_language_prefill_arrow_takes_priority_over_numbered_list():
    """当箭头格式和编号列表同时存在时，箭头格式优先。"""
    from agent_system.experts.builder_expert.builder import _extract_natural_language_prefill

    text = (
        "流程：读取数据——清洗数据——输出报告\n"
        "1、步骤A\n"
        "2、步骤B\n"
    )
    result = _extract_natural_language_prefill(text)

    assert "execution_flow" in result
    flow = result["execution_flow"]["value"]
    assert "读取数据" in flow
    assert " → " in flow
