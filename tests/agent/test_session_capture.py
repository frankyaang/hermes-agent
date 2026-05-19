"""Tests for agent/session_capture.py — PR 1 验收测试。

验收合同：
  - 含用户纠正关键词的消息 → 创建 MemoryEvent，risk_flags 含 "user_correction"
  - 含 ExperienceCard 触发词（David）的消息 → 创建 MemoryEvent，risk_flags 含 "identity_missing"
  - 普通消息（无 risk pattern）→ 不创建事件
  - 空消息 → 不创建事件
  - HERMES_HOME 无效 → 不抛出异常（静默失败）
  - capture_turn 不修改任何 API 消息对象
"""
from __future__ import annotations

import pytest

from agent.memory_event import list_events
from agent.session_capture import _extract_text, capture_turn


# ─── _extract_text ────────────────────────────────────────────────────────────


class TestExtractText:
    def test_string_input(self):
        assert _extract_text("hello") == "hello"

    def test_list_dict_input(self):
        msg = [{"type": "text", "text": "你好"}, {"type": "image_url", "url": "x"}]
        assert _extract_text(msg) == "你好"

    def test_list_mixed_input(self):
        msg = [{"type": "text", "text": "part1"}, "part2"]
        result = _extract_text(msg)
        assert "part1" in result

    def test_empty_string(self):
        assert _extract_text("") == ""

    def test_none_input(self):
        assert _extract_text(None) == ""


# ─── capture_turn：无 risk pattern ───────────────────────────────────────────


class TestCaptureNoRisk:
    def test_normal_message_returns_none(self, tmp_path):
        result = capture_turn("今天天气不错", session_id="s1", hermes_home=tmp_path)
        assert result is None

    def test_no_event_written_for_normal_message(self, tmp_path):
        capture_turn("产品功能更新说明", session_id="s1", hermes_home=tmp_path)
        assert list_events(hermes_home=tmp_path) == []

    def test_empty_text_returns_none(self, tmp_path):
        assert capture_turn("", hermes_home=tmp_path) is None

    def test_whitespace_only_returns_none(self, tmp_path):
        assert capture_turn("   ", hermes_home=tmp_path) is None


# ─── capture_turn：用户纠正 ────────────────────────────────────────────────────


class TestCaptureUserCorrection:
    def test_correction_returns_event_id(self, tmp_path):
        result = capture_turn(
            "不要用'晋升'这个词，用'下一步动作'",
            session_id="s-corr",
            hermes_home=tmp_path,
        )
        assert result is not None

    def test_correction_creates_event_in_jsonl(self, tmp_path):
        capture_turn(
            "请不要用'生命周期'，改用'产品迭代周期'",
            session_id="s-corr2",
            hermes_home=tmp_path,
        )
        events = list_events(hermes_home=tmp_path)
        assert len(events) == 1

    def test_correction_event_has_user_correction_flag(self, tmp_path):
        capture_turn(
            "别用'系统腔'那套词了",
            session_id="s-corr3",
            hermes_home=tmp_path,
        )
        events = list_events(hermes_home=tmp_path)
        assert "user_correction" in events[0]["risk_flags"]

    def test_correction_event_routes_to_personal_memory(self, tmp_path):
        capture_turn(
            "不要用这个词，换一个说法",
            session_id="s-corr4",
            hermes_home=tmp_path,
        )
        events = list_events(hermes_home=tmp_path)
        assert events[0]["recommended_destination"] == "personal_memory"

    def test_correction_event_stores_session_id(self, tmp_path):
        capture_turn(
            "不要用'赋能'这种词",
            session_id="sess-correction-001",
            hermes_home=tmp_path,
        )
        events = list_events(hermes_home=tmp_path)
        assert events[0]["session_id"] == "sess-correction-001"


# ─── capture_turn：David 关键词 ────────────────────────────────────────────────


class TestCaptureDavidKeyword:
    def test_david_mention_returns_event_id(self, tmp_path):
        result = capture_turn(
            "David 提到了跨产品线优先级调整",
            session_id="s-david",
            hermes_home=tmp_path,
        )
        assert result is not None

    def test_david_mention_creates_event(self, tmp_path):
        capture_turn(
            "David 说要重新评估 PBI 优先级",
            session_id="s-david2",
            hermes_home=tmp_path,
        )
        events = list_events(hermes_home=tmp_path)
        assert len(events) == 1

    def test_david_event_has_identity_missing_flag(self, tmp_path):
        capture_turn(
            "david 提到了一些想法",
            session_id="s-david3",
            hermes_home=tmp_path,
        )
        events = list_events(hermes_home=tmp_path)
        assert "identity_missing" in events[0]["risk_flags"]

    def test_david_event_routes_to_staging(self, tmp_path):
        capture_turn(
            "David 在私下说了几个方向",
            session_id="s-david4",
            hermes_home=tmp_path,
        )
        events = list_events(hermes_home=tmp_path)
        assert events[0]["recommended_destination"] == "staging"


# ─── 错误恢复：never raises ───────────────────────────────────────────────────


class TestCaptureNeverRaises:
    def test_bad_hermes_home_does_not_raise(self, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", "/nonexistent/path/that/does/not/exist")
        result = capture_turn("不要用这个词", session_id="s-err")
        # 不抛出，返回 None（写入失败但静默）或 event_id（若写入成功）
        # 主要验证：不抛出异常

    def test_empty_session_id_does_not_raise(self, tmp_path):
        result = capture_turn("不要用'晋升'", hermes_home=tmp_path)
        assert result is not None

    def test_empty_actor_does_not_raise(self, tmp_path):
        result = capture_turn(
            "不要用'赋能'",
            session_id="s1",
            actor_user_id="",
            hermes_home=tmp_path,
        )
        assert result is not None

    def test_does_not_mutate_input_message(self, tmp_path):
        msg = "不要用'生命周期'这个词"
        original = msg
        capture_turn(msg, session_id="s1", hermes_home=tmp_path)
        assert msg == original
