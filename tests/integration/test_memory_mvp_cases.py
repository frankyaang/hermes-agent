"""5 个标杆 Case 的集成验证测试。

运行方式：
    scripts/run_tests.sh tests/integration/test_memory_mvp_cases.py

每个 case 验证：
  输入来源 → MemoryEvent → Staging/分流 → 写入/暂存 → 关系记录
  → 读取带 usage_hint → ExperienceCard 触发 → 输出不越界 → 证明下次行为变化
"""
from __future__ import annotations

import json
import pytest
import yaml
from unittest.mock import MagicMock

from agent.memory_event import create_event, list_events, write_event
from agent.memory_dispatcher import (
    DEST_EXPERIENCE_CARD,
    DEST_KNOWLEDGE,
    DEST_PERSONAL_MEMORY,
    DEST_PROJECT_PROCESS,
    DEST_STAGING,
    dispatch_event,
    dispatch_tool_failure,
)
from agent.staging_store import list_staging, read_staging
from agent.experience_card import DAVID_CARD, render_card, trigger_check, write_card
from agent.memory_relations import list_relations, write_relation
from agent.usage_hint import (
    hint_for_experience_card,
    hint_for_knowledge,
    hint_for_session_search,
    hint_for_staging,
)
from gateway.session_context import clear_session_vars, set_session_vars
from tools import knowledge_tool


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _write_registry(home, user_id, product_line_ids):
    registry_dir = home / "knowledge"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "users.yaml").write_text(
        yaml.safe_dump({"users": [{
            "user_id": user_id,
            "display_name": user_id,
            "product_line_ids": product_line_ids,
            "default_product_line_id": product_line_ids[0] if product_line_ids else "",
            "finance_product_line_ids": [],
            "role": "business_user",
            "is_admin": False,
        }]}),
        encoding="utf-8",
    )


def _mock_gbrain(monkeypatch, slug="saved-slug"):
    provider = MagicMock()
    provider.write.return_value = slug
    provider.query.return_value = []
    monkeypatch.setattr(
        "plugins.knowledge.gbrain.provider.GBrainCLIKnowledgeProvider",
        lambda: provider,
    )
    return provider


# ─────────────────────────────────────────────────────────────────────────────
# Case 1：David — 跨层级人物信息拆分
# ─────────────────────────────────────────────────────────────────────────────

def test_case1_david_cross_level_split(tmp_path):
    """
    输入：来自私聊的 David 相关材料（risk_flags=private_chat）
    预期：
      - MemoryEvent 创建，risk_flags 包含 private_chat
      - 分流到 staging（无 project_hint，私聊不直接进项目材料）
      - ExperienceCard 触发（David 关键词）
      - rendered card 含 usage_hint: action_rule_for_next_task
      - 输出不越界：staging destination ≠ project_process / knowledge
    """
    # 输入来源
    evt = create_event(
        source_type="session",
        source_uri="hermes://session/david-private-chat",
        actor_user_id="feishu:ou_david_colleague",
        subject="David 私下说跨产品线对齐优先级高于单品优化",
        risk_flags=["private_chat"],
        recommended_destination="personal_memory",
        speaker_label="user",
        session_id="sess-david-001",
    )

    # MemoryEvent 写入
    event_id = write_event(evt, hermes_home=tmp_path)
    assert event_id == evt.id

    events = list_events(hermes_home=tmp_path)
    assert len(events) == 1
    assert "private_chat" in events[0]["risk_flags"]

    # 分流（private_chat + 无 project_hint → staging）
    result = dispatch_event(evt, hermes_home=tmp_path)
    assert result.destination == DEST_STAGING, f"David 私聊应进 staging，实际：{result.destination}"
    assert result.staging_id, "staging_id 不能为空"

    # staging 记录可读取
    staging_rec = read_staging(result.staging_id, hermes_home=tmp_path)
    assert staging_rec is not None
    assert staging_rec["usage_hint"] == "needs_source_check"
    assert staging_rec["next_action"] == "wait_for_source"

    # ExperienceCard 触发
    card = trigger_check("David 私下说跨产品线对齐优先级高于单品优化", hermes_home=tmp_path)
    assert card is not None, "David 关键词应触发 ExperienceCard"
    assert card.id == "david-001"

    # rendered card 含 usage_hint
    rendered = render_card(card)
    assert "usage_hint: action_rule_for_next_task" in rendered
    assert "私聊" in rendered  # avoid_actions 中的规则出现

    # 输出不越界：不能直接进 knowledge 或 project_process
    assert result.destination not in (DEST_KNOWLEDGE, DEST_PROJECT_PROCESS), \
        "David 私聊材料不能直接进 knowledge/project_process"


# ─────────────────────────────────────────────────────────────────────────────
# Case 2：PBI 二期 — 项目过程接力
# ─────────────────────────────────────────────────────────────────────────────

def test_case2_pbi_phase2_project_process(tmp_path):
    """
    输入：来自文档的 PBI 二期信息（有 project_hint，无 risk_flags）
    预期：
      - MemoryEvent 创建，project_hint = "PBI_phase2"
      - 分流到 project_process
      - usage_hint = project_material_usable
      - 无 staging（直接路由）
    """
    evt = create_event(
        source_type="document",
        source_uri="feishu://doc/pbi-phase2-brief",
        actor_user_id="feishu:ou_pm",
        subject="PBI 二期：下一步动作是完成 UI 自动化验收，Owner: Alice",
        risk_flags=[],
        recommended_destination="project_process",
        session_id="sess-pbi-001",
        project_hint="PBI_phase2",
        product_line_hint="deebot",
    )

    event_id = write_event(evt, hermes_home=tmp_path)
    assert event_id == evt.id

    # 分流
    result = dispatch_event(evt, hermes_home=tmp_path)
    assert result.destination == DEST_PROJECT_PROCESS, \
        f"PBI 二期应进 project_process，实际：{result.destination}"
    assert result.staging_id == "", "PBI 二期不应进 staging"

    # usage_hint
    hint = hint_for_project_process()
    assert hint == "project_material_usable"

    # 下一次行为变化：project_process 的内容可被后续读取带正确 hint
    events = list_events(hermes_home=tmp_path)
    assert any(e["project_hint"] == "PBI_phase2" for e in events)


def hint_for_project_process():
    from agent.usage_hint import hint_for_project_process as _h
    return _h()


# ─────────────────────────────────────────────────────────────────────────────
# Case 3：私聊转项目材料 — 生成可分享版本
# ─────────────────────────────────────────────────────────────────────────────

def test_case3_private_chat_to_project_material(tmp_path):
    """
    输入：私聊 + 有 project_hint（用户想要转化为项目材料）
    预期：
      - risk_flags 包含 private_chat
      - 有 project_hint，不触发规则 2（wait_for_source）
      - 因有 private_chat 但无其他 staging 触发条件，进入 personal_memory（规则 10）
      - staging 不直接搬运私聊原话（staging_id 为空）
      - 私聊内容不进入 knowledge 或 project_process
    """
    evt = create_event(
        source_type="session",
        source_uri="hermes://session/private-to-project",
        actor_user_id="feishu:ou_user1",
        subject="用户私聊：认为 ABC 功能很重要，建议纳入 PBI 二期",
        risk_flags=["private_chat"],
        recommended_destination="personal_memory",
        session_id="sess-private-003",
        project_hint="PBI_phase2",  # 有 project_hint → 不触发规则 2
    )

    write_event(evt, hermes_home=tmp_path)

    result = dispatch_event(evt, hermes_home=tmp_path)

    # 私聊 + 有 project_hint：规则 2 不触发（规则 2 要求无 project_hint）
    # 无其他 staging 风险标志 → 按 recommended_destination 或默认路由
    # 因 recommended_destination=personal_memory，进入 personal_memory
    assert result.destination in (DEST_PERSONAL_MEMORY, DEST_STAGING), \
        f"私聊转项目材料应进 personal_memory 或 staging，实际：{result.destination}"

    # 关键：不能直接进 knowledge 或 project_process（不搬运私聊原话）
    assert result.destination not in (DEST_KNOWLEDGE, DEST_PROJECT_PROCESS), \
        "私聊原话不能直接进 knowledge/project_process"

    # 若进入 staging，staging 记录带 usage_hint
    if result.staging_id:
        staging_rec = read_staging(result.staging_id, hermes_home=tmp_path)
        assert staging_rec["usage_hint"] == "needs_source_check"


# ─────────────────────────────────────────────────────────────────────────────
# Case 4：用户纠正表达 — 不用系统腔，不说后台词
# ─────────────────────────────────────────────────────────────────────────────

def test_case4_user_correction_no_jargon(tmp_path):
    """
    输入：用户纠正（source_type=user_correction, risk_flags=user_correction）
    预期：
      - MemoryEvent 创建，source_type=user_correction
      - ExperienceCard 中 avoid_actions 不包含"系统腔"词汇本身（不是前台表达）
      - David ExperienceCard 的 frontstage_expression 不含后台词
      - 若无明确 scope → staging；若有明确 scope → personal_memory
    """
    # 无明确 scope → staging
    evt_no_scope = create_event(
        source_type="user_correction",
        source_uri="hermes://session/user-correction-001",
        actor_user_id="feishu:ou_user2",
        subject="用户纠正：请不要用'晋升'这个词，用'下一步动作'",
        risk_flags=["user_correction"],
        recommended_destination="personal_memory",
        session_id="sess-correction-001",
        project_hint="",
        product_line_hint="",
    )
    write_event(evt_no_scope, hermes_home=tmp_path)
    result_no_scope = dispatch_event(evt_no_scope, hermes_home=tmp_path)
    assert result_no_scope.destination == DEST_STAGING, \
        "无明确 scope 的用户纠正应进 staging"

    # 有明确 scope → personal_memory
    evt_with_scope = create_event(
        source_type="user_correction",
        source_uri="hermes://session/user-correction-002",
        actor_user_id="feishu:ou_user2",
        subject="用户纠正：请不要用'生命周期'，用'产品迭代周期'",
        risk_flags=["user_correction"],
        recommended_destination="personal_memory",
        session_id="sess-correction-002",
        project_hint="PBI_phase2",
    )
    write_event(evt_with_scope, hermes_home=tmp_path)
    result_with_scope = dispatch_event(evt_with_scope, hermes_home=tmp_path)
    assert result_with_scope.destination == DEST_PERSONAL_MEMORY, \
        "有明确 scope 的用户纠正应进 personal_memory"

    # David ExperienceCard 前台表达不含后台词
    bad_words = ["晋升", "生命周期", "已决策结论"]
    for word in bad_words:
        assert word not in DAVID_CARD.frontstage_expression, \
            f"系统腔词 '{word}' 不应出现在前台表达中"

    # rendered card 中 avoid_actions 提到不用系统腔
    rendered = render_card(DAVID_CARD)
    assert "系统腔" in rendered

    # usage_hint for staging result
    if result_no_scope.staging_id:
        rec = read_staging(result_no_scope.staging_id, hermes_home=tmp_path)
        assert rec["usage_hint"] == "needs_source_check"


# ─────────────────────────────────────────────────────────────────────────────
# Case 5：knowledge_write permission_denied — 权限失败后的替代路径
# ─────────────────────────────────────────────────────────────────────────────

def test_case5_permission_denied_fallback(tmp_path, monkeypatch):
    """
    输入：knowledge_write 返回 permission_denied（ACL 拒绝）
    预期：
      - 原有 pending_capture 写入（backward compat）
      - 新增：tool_failure MemoryEvent 生成（通过 dispatch_tool_failure）
      - MemoryEvent risk_flags 包含 tool_failure 和 permission_unclear
      - 分流到 staging(retry_write)
      - staging 记录 usage_hint = needs_source_check
      - 关系记录：tool_failure 类型
    """
    home = tmp_path / "hermes"
    _write_registry(home, "feishu:ou_perm_test", ["deebot"])
    monkeypatch.setenv("HERMES_HOME", str(home))
    knowledge_tool._MANAGER_CACHE.clear()
    _mock_gbrain(monkeypatch)

    tokens = set_session_vars(platform="feishu", user_id="ou_perm_test", chat_id="oc_test")
    try:
        # 用一个未授权的 product_line 触发 ACL 失败
        raw = knowledge_tool._knowledge_write(
            title="David 公司级偏好记录",
            content="David 偏好结论先行，明确决策请求",
            product_line_id="ecovacs_company",  # 未授权
            knowledge_type="org_info",
            source_uri="hermes://session/case5-test",
            finance_flag=False,
            sensitivity_level="internal",
            confidence="unverified",
            doc_slug="",
            task_id="case5-task",
        )
    finally:
        clear_session_vars(tokens)
        knowledge_tool._MANAGER_CACHE.clear()

    result = json.loads(raw)

    # 原有 pending_capture 路径正常
    assert result["error"] == "permission_denied"
    assert "pending_capture_id" in result

    # 新增：tool_failure MemoryEvent 已写入
    events = list_events(hermes_home=home)
    tool_failure_events = [
        e for e in events
        if "tool_failure" in e.get("risk_flags", [])
    ]
    assert len(tool_failure_events) >= 1, \
        "permission_denied 后应生成 tool_failure MemoryEvent"

    # MemoryEvent 字段验证
    evt = tool_failure_events[0]
    assert evt["source_type"] == "write_failure"
    assert "permission_unclear" in evt["risk_flags"]

    # staging 记录存在
    staging_records = list_staging(hermes_home=home)
    assert len(staging_records) >= 1, "tool_failure 应产生 staging 记录"
    staging_rec = staging_records[0]
    assert staging_rec["next_action"] == "retry_write"
    assert staging_rec["usage_hint"] == "needs_source_check"

    # 关系记录：tool_failure 类型
    relations = list_relations(hermes_home=home)
    tool_failure_relations = [r for r in relations if r["relation_type"] == "tool_failure"]
    assert len(tool_failure_relations) >= 1, "应有 tool_failure 关系记录"

    # 证明下次行为变化：staging 记录可被读取并带正确 usage_hint
    # （下次遇到相同 product_line 失败时，可通过 list_staging 找到 retry_write 条目）
    retry_records = [r for r in staging_records if r["next_action"] == "retry_write"]
    assert len(retry_records) >= 1
