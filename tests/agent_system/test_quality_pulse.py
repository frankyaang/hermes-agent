"""Tests for agent/evaluator.py QualityPulse 扩展 — 认知治理协议违规检测。

验收合同：
  - check_output_for_banned_jargon: 基础禁词检测，已覆盖 PR 3
  - check_insight_missing_source: InsightDelta 必须有来源证据
  - check_assumption_listed_as_fact: 假设不能混入已知事实段落
  - check_promotion_auto_executed: PromotionDecision 不能自动执行
  - check_governance_triggered_for_simple_task: 简单任务不应触发治理框架
"""
from __future__ import annotations

import pytest

from agent.evaluator import (
    check_assumption_listed_as_fact,
    check_governance_triggered_for_simple_task,
    check_insight_missing_source,
    check_output_for_banned_jargon,
    check_promotion_auto_executed,
)


class TestBannedJargon:
    def test_returns_empty_for_clean_output(self):
        assert check_output_for_banned_jargon("这是正常输出", ["禁止词A", "禁止词B"]) == []

    def test_detects_single_banned_word(self):
        result = check_output_for_banned_jargon("输出含有禁止词A", ["禁止词A"])
        assert result == ["禁止词A"]

    def test_detects_multiple_banned_words(self):
        result = check_output_for_banned_jargon("输出含有禁止词A和禁止词B", ["禁止词A", "禁止词B", "禁止词C"])
        assert set(result) == {"禁止词A", "禁止词B"}

    def test_empty_banned_list_returns_empty(self):
        assert check_output_for_banned_jargon("任意输出", []) == []

    def test_empty_output_returns_empty(self):
        assert check_output_for_banned_jargon("", ["禁止词A"]) == []


class TestInsightMissingSource:
    def test_no_violation_when_no_insight(self):
        output = "这是普通分析输出，没有洞察声明。"
        assert check_insight_missing_source(output) == []

    def test_no_violation_when_insight_has_source(self):
        output = "## InsightDelta\n洞察内容：用户留存下降\n来源证据：文档B第3页数据"
        assert check_insight_missing_source(output) == []

    def test_violation_when_insight_lacks_source(self):
        output = "## InsightDelta\n洞察内容：用户留存下降，原因不明。"
        result = check_insight_missing_source(output)
        assert len(result) == 1
        assert "来源证据" in result[0]

    def test_multiple_paragraphs_one_missing_source(self):
        output = (
            "## InsightDelta\n洞察内容：A 洞察\n来源证据：报告第2页\n\n"
            "## InsightDelta\n洞察内容：B 洞察，无来源。"
        )
        result = check_insight_missing_source(output)
        assert len(result) == 1

    def test_no_violation_for_empty_output(self):
        assert check_insight_missing_source("") == []


class TestAssumptionListedAsFact:
    def test_no_violation_for_clean_facts(self):
        output = "## 已知事实\n- API 延迟 p99 < 100ms（来自监控数据）\n- DAU 上周为 50k"
        assert check_assumption_listed_as_fact(output) == []

    def test_violation_when_assumption_in_fact_section(self):
        output = "## 已知事实\n- API 延迟可能是 100ms\n- DAU 大约 50k，推断自上月数据"
        result = check_assumption_listed_as_fact(output)
        assert len(result) >= 1
        assert "假设" in result[0] or "推断" in result[0] or "可能" in result[0]

    def test_no_violation_when_assumption_outside_fact_section(self):
        output = "## 当前假设\n- 用户增长可能是由新功能驱动的\n\n## 已知事实\n- DAU 50k"
        assert check_assumption_listed_as_fact(output) == []

    def test_no_violation_for_empty_output(self):
        assert check_assumption_listed_as_fact("") == []


class TestPromotionAutoExecuted:
    def test_no_violation_when_pending(self):
        output = "## PromotionDecision\n状态：pending_confirmation\n沉淀内容：用户留存规律"
        assert check_promotion_auto_executed(output) == []

    def test_violation_on_already_sedimented(self):
        output = "## PromotionDecision\n已沉淀到长期记忆。\n状态：完成"
        result = check_promotion_auto_executed(output)
        assert len(result) >= 1
        assert "已执行" in result[0] or "禁止" in result[0]

    def test_violation_on_written_to_memory(self):
        output = "已更新 MEMORY.md，知识已写入。"
        result = check_promotion_auto_executed(output)
        assert len(result) >= 1

    def test_no_violation_for_empty_output(self):
        assert check_promotion_auto_executed("") == []

    def test_no_violation_for_unrelated_text(self):
        output = "任务已完成，代码已修复，无沉淀操作。"
        assert check_promotion_auto_executed(output) == []


class TestGovernanceForSimpleTask:
    def test_no_violation_for_unknown_task_type(self):
        output = "## ProblemContract\n问题边界：分析用户数据\n约束：不涉及财务"
        assert check_governance_triggered_for_simple_task(output, task_hint="complex") == []

    def test_no_violation_for_empty_task_hint(self):
        output = "## ProblemContract\n问题边界：..."
        assert check_governance_triggered_for_simple_task(output) == []

    def test_violation_when_rewrite_triggers_problem_contract(self):
        output = "## ProblemContract\n问题边界：改写这段话\n约束：不改意思"
        result = check_governance_triggered_for_simple_task(output, task_hint="rewrite")
        assert len(result) >= 1
        assert "rewrite" in result[0]

    def test_violation_when_factual_qa_triggers_insight_delta(self):
        output = "## InsightDelta\n洞察内容：Python list 是可变的"
        result = check_governance_triggered_for_simple_task(output, task_hint="factual_qa")
        assert len(result) >= 1

    def test_violation_when_bug_fix_triggers_cognitive_state(self):
        output = "## CognitiveState\n已知事实：函数存在 off-by-one\n未知：其他 bug"
        result = check_governance_triggered_for_simple_task(output, task_hint="bug_fix")
        assert len(result) >= 1

    def test_no_violation_when_simple_task_outputs_cleanly(self):
        output = "这段话改写后更简洁：用户留存率呈下降趋势。"
        assert check_governance_triggered_for_simple_task(output, task_hint="rewrite") == []


class TestNegativeControls:
    """Requirement H: 系统不会做的事情。"""

    def test_private_verbatim_not_in_knowledge(self):
        """私聊原话不得出现在 knowledge 输出中（没有改写标记）。"""
        output = "## KnowledgeOps candidate\n原始对话：David 在私聊说 '跨产品线优先级高'"
        violations = check_output_for_banned_jargon(output, ["原始对话：", "私聊说"])
        assert len(violations) > 0

    def test_provider_failure_not_sedimented(self):
        """provider failure 不得被标记为事实知识。"""
        from agent.promotion_decision import classify
        from agent.memory_event import create_event
        evt = create_event(
            source_type="write_failure",
            source_uri="hermes://tool/knowledge_write",
            actor_user_id="feishu:ou_test",
            subject="GBrain CLI 超时",
            risk_flags=["tool_failure"],
            recommended_destination="knowledge",
        )
        result = classify(evt)
        assert result.scope == "rejected_temp"
        assert result.can_auto_promote is False

    def test_expert_judgment_not_replaced_by_kernel(self):
        """Cognitive Kernel 的 InsightGapScan 不替代专家层判断。

        InsightGapScan 只做元层面决策（重复/新增/停止）；
        它不应该产生领域判断（如"这个功能好不好"）。
        """
        from agent.insight_gap_scan import scan
        result = scan(
            previous="功能 X 交互复杂",
            current="功能 X 交互复杂",
        )
        assert result.decision == "repeat"
        assert "好" not in result.reason
        assert "不好" not in result.reason
        assert "应该" not in result.reason

    def test_synonym_not_marked_as_new_insight(self):
        """同义重复不应被标记为新增洞察。"""
        from agent.insight_gap_scan import scan
        result = scan(
            previous="用户留存率与新功能上线时间有关联",
            current="新功能上线时间与用户留存率存在关联关系",
        )
        assert result.decision == "repeat"

    def test_promotion_without_scope_blocked(self):
        """无 scope 判断依据时，PromotionDecision 返回 needs_human_review。"""
        from agent.promotion_decision import classify
        from agent.memory_event import create_event
        evt = create_event(
            source_type="session",
            source_uri="hermes://session/no-scope",
            actor_user_id="feishu:ou_test",
            subject="模糊的会话笔记",
            risk_flags=[],
            recommended_destination="personal_memory",
            project_hint="",
            product_line_hint="",
        )
        result = classify(evt)
        assert result.scope == "needs_human_review"
        assert result.can_auto_promote is False

    def test_promotion_auto_executed_violation_detected(self):
        """PromotionDecision 自动执行被 evaluator 检测为违规。"""
        output = "沉淀决策已执行：已沉淀到用户长期记忆。"
        violations = check_promotion_auto_executed(output)
        assert len(violations) >= 1
