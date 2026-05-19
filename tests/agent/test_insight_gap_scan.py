"""Tests for agent/insight_gap_scan.py — InsightGapScan 多轮决策。

验收合同：
  - repeat_detected: 当前轮与上一轮实质相同 → "repeat"
  - new_insight: 当前轮有明确新内容 → "new_insight"
  - connection_gap: 发现两个洞察之间缺少连接证据 → "gap"
  - revision: 当前轮修正了上一轮判断 → "revision"
  - continue_thinking: 有深挖空间但还没结论 → "continue"
  - stop_and_execute: 足够执行了，停止深挖 → "stop"
  - enter_promotion: 洞察质量足以进入 PromotionDecision → "promote"
"""
from __future__ import annotations
import pytest
from agent.insight_gap_scan import scan, ScanDecision


class TestRepeatDetection:
    def test_identical_text_is_repeat(self):
        result = scan(
            previous="用户留存率与新功能上线时间相关",
            current="用户留存率与新功能上线时间相关",
        )
        assert result.decision == "repeat"

    def test_near_identical_is_repeat(self):
        result = scan(
            previous="用户留存率和新功能上线时间有关联",
            current="用户留存率与新功能的上线时间存在关联",
        )
        assert result.decision == "repeat"

    def test_empty_previous_is_not_repeat(self):
        result = scan(previous="", current="用户留存率与新功能上线时间相关")
        assert result.decision != "repeat"


class TestNewInsight:
    def test_completely_different_topic_is_new(self):
        result = scan(
            previous="用户留存率与功能上线相关",
            current="DAU 下降与竞品发布时间窗口重合",
        )
        assert result.decision == "new_insight"

    def test_adds_evidence_is_new(self):
        result = scan(
            previous="留存率下降",
            current="留存率下降 3pp，数据来源：第3周复盘报告 P12",
        )
        assert result.decision == "new_insight"


class TestConnectionGap:
    def test_contradiction_between_rounds_is_gap(self):
        result = scan(
            previous="DAU 持续上升",
            current="留存率同期下降",
            check_contradiction=True,
        )
        assert result.decision == "gap"

    def test_missing_link_is_gap(self):
        result = scan(
            previous="功能 A 上线",
            current="GMV 增长",
            check_contradiction=False,
            gap_hint="两个事件之间缺少用户行为链路证据",
        )
        assert result.decision == "gap"


class TestRevision:
    def test_explicit_correction_is_revision(self):
        result = scan(
            previous="留存率下降是功能问题",
            current="留存率下降不是功能问题，而是竞品原因",
        )
        assert result.decision == "revision"

    def test_negation_keyword_is_revision(self):
        result = scan(
            previous="原因是 A",
            current="原因不是 A，而是 B",
        )
        assert result.decision == "revision"


class TestContinueStop:
    def test_no_evidence_suggests_continue(self):
        result = scan(
            previous="用户对功能 X 不满意",
            current="不满意原因可能是交互问题",
            has_sufficient_evidence=False,
        )
        assert result.decision in ("continue", "stop")

    def test_sufficient_evidence_stops(self):
        result = scan(
            previous="用户因交互复杂放弃功能 X",
            current="来源：A/B 测试报告，置信度 high，3 条用户访谈验证",
            has_sufficient_evidence=True,
        )
        assert result.decision == "stop"


class TestPromotionEntry:
    def test_high_confidence_generalizable_promotes(self):
        result = scan(
            previous="",
            current="用户在首次使用功能时需要引导，来源：3 轮用户测试",
            generalizable=True,
            confidence="high",
        )
        assert result.decision == "promote"


class TestScanResult:
    def test_returns_scan_decision_object(self):
        result = scan(previous="A", current="B")
        assert isinstance(result, ScanDecision)
        assert result.decision in ("repeat", "new_insight", "gap", "revision", "continue", "stop", "promote")
        assert result.reason  # 非空理由

    def test_does_not_write_any_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        scan(previous="X", current="Y")
        assert not (tmp_path / "cognitive").exists()
