#!/usr/bin/env python3
"""可复跑 Memory Control Panel MVP 验证入口。

运行：
    cd /Users/frank/.hermes/hermes-agent-integrate
    python scripts/verify_memory_mvp.py

退出码：0 = 全部通过，1 = 有失败。

验证 5 个标杆 case：
  1. David     — 跨层级人物信息拆分
  2. PBI 二期  — 项目过程接力
  3. 私聊转项目 — 不搬运私聊原话
  4. 用户纠正  — 不用系统腔，不说后台词
  5. permission_denied — 权限失败后的替代路径
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

# 确保项目根在 sys.path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _ok(case_name: str, msg: str = ""):
    tag = f"  {msg}" if msg else ""
    print(f"  ✓ {case_name}{tag}")


def _fail(case_name: str, msg: str):
    print(f"  ✗ {case_name}: {msg}")


def _assert(condition: bool, case_name: str, msg: str) -> bool:
    if condition:
        _ok(case_name, msg)
        return True
    _fail(case_name, msg)
    return False


# ─── Case 1：David 跨层级人物信息拆分 ────────────────────────────────────────

def verify_case1_david(tmp_dir: Path) -> dict:
    from agent.memory_event import create_event, list_events, write_event
    from agent.memory_dispatcher import DEST_KNOWLEDGE, DEST_PROJECT_PROCESS, DEST_STAGING, dispatch_event
    from agent.experience_card import render_card, trigger_check
    from agent.staging_store import read_staging

    passed = []
    failed = []

    evt = create_event(
        source_type="session",
        source_uri="hermes://session/david-private",
        actor_user_id="feishu:ou_david_colleague",
        subject="David 私下说跨产品线对齐优先级高于单品优化",
        risk_flags=["private_chat"],
        recommended_destination="personal_memory",
        session_id="sess-david-001",
        project_hint="",
    )

    # 写入 MemoryEvent
    eid = write_event(evt, hermes_home=tmp_dir)
    events = list_events(hermes_home=tmp_dir)
    check = "MemoryEvent 写入"
    if events and "private_chat" in events[0]["risk_flags"]:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, "MemoryEvent 未写入或 risk_flags 缺失")

    # 分流
    result = dispatch_event(evt, hermes_home=tmp_dir)
    check = "分流到 staging（非 knowledge/project_process）"
    if result.destination == DEST_STAGING and result.destination not in (DEST_KNOWLEDGE, DEST_PROJECT_PROCESS):
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"实际 destination={result.destination}")

    # staging usage_hint
    if result.staging_id:
        rec = read_staging(result.staging_id, hermes_home=tmp_dir)
        check = "staging 带 usage_hint=needs_source_check"
        if rec and rec.get("usage_hint") == "needs_source_check":
            passed.append(check)
            _ok(check)
        else:
            failed.append(check)
            _fail(check, f"实际={rec}")

    # ExperienceCard 触发
    card = trigger_check("David 私下说跨产品线对齐优先级", hermes_home=tmp_dir)
    check = "ExperienceCard 触发（David 关键词）"
    if card is not None and card.id == "david-001":
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"card={card}")

    # render 含 usage_hint
    if card:
        rendered = render_card(card)
        check = "rendered card 含 action_rule_for_next_task"
        if "action_rule_for_next_task" in rendered:
            passed.append(check)
            _ok(check)
        else:
            failed.append(check)
            _fail(check, "rendered card 缺失 usage_hint")

    return {
        "case": "Case 1 David",
        "passed": passed,
        "failed": failed,
        "residual_risks": ["David 触发规则基于关键词匹配，复杂写法可能不触发"],
    }


# ─── Case 2：PBI 二期项目过程接力 ────────────────────────────────────────────

def verify_case2_pbi(tmp_dir: Path) -> dict:
    from agent.memory_event import create_event, list_events, write_event
    from agent.memory_dispatcher import DEST_PROJECT_PROCESS, dispatch_event
    from agent.usage_hint import hint_for_project_process

    passed = []
    failed = []

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

    write_event(evt, hermes_home=tmp_dir)
    result = dispatch_event(evt, hermes_home=tmp_dir)

    check = "分流到 project_process"
    if result.destination == DEST_PROJECT_PROCESS:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"实际={result.destination}")

    check = "staging_id 为空（不进 staging）"
    if result.staging_id == "":
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"staging_id={result.staging_id}")

    check = "usage_hint=project_material_usable"
    hint = hint_for_project_process()
    if hint == "project_material_usable":
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"实际={hint}")

    check = "MemoryEvent 含 project_hint"
    events = list_events(hermes_home=tmp_dir)
    if any(e["project_hint"] == "PBI_phase2" for e in events):
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, "MemoryEvent 未含 project_hint=PBI_phase2")

    return {
        "case": "Case 2 PBI 二期",
        "passed": passed,
        "failed": failed,
        "residual_risks": ["project_process 存储暂为逻辑目标，无独立持久化层"],
    }


# ─── Case 3：私聊转项目材料 ───────────────────────────────────────────────────

def verify_case3_private_to_project(tmp_dir: Path) -> dict:
    from agent.memory_event import create_event, write_event
    from agent.memory_dispatcher import DEST_KNOWLEDGE, DEST_PROJECT_PROCESS, dispatch_event
    from agent.staging_store import read_staging

    passed = []
    failed = []

    evt = create_event(
        source_type="session",
        source_uri="hermes://session/private-to-project",
        actor_user_id="feishu:ou_user1",
        subject="用户私聊：认为 ABC 功能很重要，建议纳入 PBI 二期",
        risk_flags=["private_chat"],
        recommended_destination="personal_memory",
        session_id="sess-private-003",
        project_hint="PBI_phase2",
    )

    write_event(evt, hermes_home=tmp_dir)
    result = dispatch_event(evt, hermes_home=tmp_dir)

    check = "不直接进 knowledge 或 project_process"
    if result.destination not in (DEST_KNOWLEDGE, DEST_PROJECT_PROCESS):
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"私聊原话不应进 {result.destination}")

    check = "staging 带 usage_hint（若进 staging）"
    if result.staging_id:
        rec = read_staging(result.staging_id, hermes_home=tmp_dir)
        if rec and rec.get("usage_hint") == "needs_source_check":
            passed.append(check)
            _ok(check)
        else:
            failed.append(check)
            _fail(check, f"staging 无 usage_hint")
    else:
        passed.append(check + "（进 personal_memory，不需 staging）")
        _ok(check + "（进 personal_memory，不需 staging）")

    return {
        "case": "Case 3 私聊转项目材料",
        "passed": passed,
        "failed": failed,
        "residual_risks": ["生成'可分享版本'的重写逻辑暂未实现，只做了分流隔离"],
    }


# ─── Case 4：用户纠正表达 ─────────────────────────────────────────────────────

def verify_case4_user_correction(tmp_dir: Path) -> dict:
    from agent.memory_event import create_event, write_event
    from agent.memory_dispatcher import DEST_PERSONAL_MEMORY, DEST_STAGING, dispatch_event
    from agent.experience_card import DAVID_CARD, render_card
    from agent.staging_store import read_staging

    passed = []
    failed = []

    # 无明确 scope → staging
    evt_no_scope = create_event(
        source_type="user_correction",
        source_uri="hermes://session/correction-001",
        actor_user_id="feishu:ou_user2",
        subject="用户纠正：请不要用'晋升'这个词",
        risk_flags=["user_correction"],
        recommended_destination="personal_memory",
        project_hint="",
        product_line_hint="",
    )
    write_event(evt_no_scope, hermes_home=tmp_dir)
    result_no = dispatch_event(evt_no_scope, hermes_home=tmp_dir)

    check = "无 scope 的纠正进 staging"
    if result_no.destination == DEST_STAGING:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"实际={result_no.destination}")

    # 有明确 scope → personal_memory
    evt_scope = create_event(
        source_type="user_correction",
        source_uri="hermes://session/correction-002",
        actor_user_id="feishu:ou_user2",
        subject="用户纠正：请不要用'生命周期'",
        risk_flags=["user_correction"],
        recommended_destination="personal_memory",
        project_hint="PBI_phase2",
    )
    write_event(evt_scope, hermes_home=tmp_dir)
    result_yes = dispatch_event(evt_scope, hermes_home=tmp_dir)

    check = "有 scope 的纠正进 personal_memory"
    if result_yes.destination == DEST_PERSONAL_MEMORY:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"实际={result_yes.destination}")

    # ExperienceCard 前台表达无后台词
    bad_words = ["晋升", "生命周期", "已决策结论"]
    check = "David ExperienceCard 前台表达无系统腔词"
    violations = [w for w in bad_words if w in DAVID_CARD.frontstage_expression]
    if not violations:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"含后台词：{violations}")

    # rendered card 提示不用系统腔
    rendered = render_card(DAVID_CARD)
    check = "rendered card 包含系统腔禁止规则"
    if "系统腔" in rendered:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, "rendered card 未提及系统腔规则")

    return {
        "case": "Case 4 用户纠正表达",
        "passed": passed,
        "failed": failed,
        "residual_risks": ["对前台语言的约束需 Agent 遵守，测试只验证 ExperienceCard 内容正确"],
    }


# ─── Case 5：permission_denied 替代路径 ──────────────────────────────────────

def verify_case5_permission_denied(tmp_dir: Path) -> dict:
    import os
    import yaml
    from unittest.mock import MagicMock, patch
    from agent.memory_event import list_events
    from agent.memory_relations import list_relations
    from agent.staging_store import list_staging
    from gateway.session_context import clear_session_vars, set_session_vars
    from tools import knowledge_tool

    passed = []
    failed = []

    home = tmp_dir / "hermes_case5"
    registry_dir = home / "knowledge"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "users.yaml").write_text(
        yaml.safe_dump({"users": [{
            "user_id": "feishu:ou_perm_test",
            "display_name": "perm test",
            "product_line_ids": ["deebot"],
            "default_product_line_id": "deebot",
            "finance_product_line_ids": [],
            "role": "business_user",
            "is_admin": False,
        }]}),
        encoding="utf-8",
    )

    os.environ["HERMES_HOME"] = str(home)
    knowledge_tool._MANAGER_CACHE.clear()

    provider = MagicMock()
    provider.write.return_value = "mock-slug"
    provider.query.return_value = []

    with patch(
        "plugins.knowledge.gbrain.provider.GBrainCLIKnowledgeProvider",
        lambda: provider,
    ):
        tokens = set_session_vars(platform="feishu", user_id="ou_perm_test", chat_id="oc_test")
        try:
            raw = knowledge_tool._knowledge_write(
                title="David 公司级偏好",
                content="David 偏好结论先行",
                product_line_id="ecovacs_company",  # 未授权
                knowledge_type="org_info",
                source_uri="hermes://session/case5-verify",
                finance_flag=False,
                sensitivity_level="internal",
                confidence="unverified",
                doc_slug="",
                task_id="case5-verify-task",
            )
        finally:
            clear_session_vars(tokens)
            knowledge_tool._MANAGER_CACHE.clear()

    result = json.loads(raw)

    check = "knowledge_write 返回 permission_denied"
    if result.get("error") == "permission_denied":
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"实际={result}")

    check = "pending_capture_id 存在（backward compat）"
    if "pending_capture_id" in result:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, "无 pending_capture_id")

    check = "tool_failure MemoryEvent 生成"
    events = list_events(hermes_home=home)
    tf_events = [e for e in events if "tool_failure" in e.get("risk_flags", [])]
    if tf_events:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"无 tool_failure MemoryEvent，共 {len(events)} 条 event")

    check = "staging(retry_write) 记录存在"
    staging = list_staging(hermes_home=home)
    retry_recs = [s for s in staging if s.get("next_action") == "retry_write"]
    if retry_recs:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"无 retry_write staging，共 {len(staging)} 条 staging")

    check = "staging 带 usage_hint=needs_source_check"
    if retry_recs and retry_recs[0].get("usage_hint") == "needs_source_check":
        passed.append(check)
        _ok(check)
    elif not retry_recs:
        failed.append(check)
        _fail(check, "无 staging 记录")
    else:
        failed.append(check)
        _fail(check, f"实际={retry_recs[0].get('usage_hint')}")

    check = "tool_failure 关系记录存在"
    relations = list_relations(hermes_home=home)
    tf_rels = [r for r in relations if r.get("relation_type") == "tool_failure"]
    if tf_rels:
        passed.append(check)
        _ok(check)
    else:
        failed.append(check)
        _fail(check, f"无 tool_failure 关系，共 {len(relations)} 条关系")

    return {
        "case": "Case 5 permission_denied 替代路径",
        "passed": passed,
        "failed": failed,
        "residual_risks": ["staging retry_write 的实际重试逻辑需人工触发或后续自动化"],
    }


# ─── 主入口 ───────────────────────────────────────────────────────────────────

def main():
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║      Memory Control Panel MVP — 5 Case 验证报告              ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    cases = [
        ("Case 1 David 跨层级拆分", verify_case1_david),
        ("Case 2 PBI 二期项目接力", verify_case2_pbi),
        ("Case 3 私聊转项目材料", verify_case3_private_to_project),
        ("Case 4 用户纠正表达", verify_case4_user_correction),
        ("Case 5 permission_denied 替代", verify_case5_permission_denied),
    ]

    all_results = []
    total_passed = 0
    total_failed = 0

    for name, fn in cases:
        print(f"── {name} ──")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            try:
                result = fn(tmp_dir)
                all_results.append(result)
                total_passed += len(result["passed"])
                total_failed += len(result["failed"])
                if result["failed"]:
                    print(f"  → FAIL ({len(result['failed'])} 项失败)\n")
                else:
                    print(f"  → PASS ({len(result['passed'])} 项全通过)\n")
                if result.get("residual_risks"):
                    print(f"  剩余风险：{'; '.join(result['residual_risks'])}\n")
            except Exception as exc:
                print(f"  → ERROR: {exc}")
                traceback.print_exc()
                total_failed += 1
                all_results.append({"case": name, "passed": [], "failed": [str(exc)], "residual_risks": []})

    print("╔══════════════════════════════════════════════════════════════╗")
    print(f"║  汇总：{total_passed} 项通过，{total_failed} 项失败")
    if total_failed == 0:
        print("║  结论：✓ 全部通过")
    else:
        print("║  结论：✗ 有失败项，请查看上方详情")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
