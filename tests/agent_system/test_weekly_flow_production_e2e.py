"""
Weekly Flow Production E2E Tests

从 raw weekly material 开始的完整链路测试：
  1. raw material → issue_extractor → Issue[] → decision_gate → execution_contract → pending ledger
  2. fake_closure 在链路中被正确过滤
  3. pending → Feishu 确认（mock handler）→ confirmed
  4. 完整链路：raw material → decision_gate route → pending → confirmed
  5. 空材料 → 空 Issue 列表，pipeline 安全完成

P0-3 Provider Integration Tests（TestIssueExtractorProviderIntegration）：
  6. mock anthropic.Anthropic 边界，不注入 llm_call_fn，验证完整解析链路
  7. prompt 构建：raw material 内容出现在发送给 provider 的 prompt 中
"""
from __future__ import annotations

import json

import pytest

from agent_system.evaluators.decision_gate import route_issues
from agent_system.schemas.weekly_schemas import ConfirmationEvent, Issue
from agent_system.skills.execution_contract.skill import run as run_execution_contract
from agent_system.skills.issue_extractor.skill import extract_issues
from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore

# ──────────────────────────────────────────────────────────────────────────────
# 测试原材料（含一个合法议题 + 一个 fake_closure）
# ──────────────────────────────────────────────────────────────────────────────

_RAW_MATERIAL_MIXED = """\
本周香农 Weekly 议题：

【议题1】X11 海外配件定价策略
背景：当前配件利润率低于目标 5pp，Q2 连续亏损。
推荐方案：方案B — 涨价 8%，搭配促销套装。
负责人：张三。
验收标准：Q3 配件毛利率达到 35%。

【议题2】配件库存积压问题
背景：K900 配件库存积压 3 个月。
推荐方案：持续跟进并推动清库。
"""

_LLM_OUTPUT_MIXED = json.dumps([
    {
        "title": "X11 海外配件定价策略",
        "background": "当前配件利润率低于目标 5pp，Q2 连续亏损",
        "source_ref": "weekly_2026_w20",
        "urgency": "high",
        "options": ["方案A：维持现价", "方案B：涨价 8%"],
        "recommended_option": "方案B：涨价 8%，搭配促销套装",
        "owner_candidate": "张三",
        "acceptance_criteria": "Q3 配件毛利率达到 35%",
    },
    {
        "title": "配件库存积压问题",
        "background": "K900 配件库存积压 3 个月",
        "source_ref": "weekly_2026_w20",
        "urgency": "low",
        "options": [],
        "recommended_option": "持续跟进并推动清库",
        "owner_candidate": None,
        "acceptance_criteria": None,
    },
])


# ──────────────────────────────────────────────────────────────────────────────
# 1. raw material → issue_extractor → Issue[] → decision_gate
# ──────────────────────────────────────────────────────────────────────────────

def test_raw_material_to_decision_gate():
    issues = extract_issues(
        _RAW_MATERIAL_MIXED,
        source_ref="weekly_2026_w20",
        llm_call_fn=lambda p: _LLM_OUTPUT_MIXED,
    )
    assert len(issues) == 2

    routes = route_issues(issues)
    assert routes[issues[0].issue_id] == "decision_agenda"   # 合法议题
    assert routes[issues[1].issue_id] == "fake_closure_detected"  # 伪闭环


# ──────────────────────────────────────────────────────────────────────────────
# 2. fake_closure 在 execution_contract 链路中被过滤
# ──────────────────────────────────────────────────────────────────────────────

def test_fake_closure_filtered_in_execution_contract():
    issues = extract_issues(
        _RAW_MATERIAL_MIXED,
        source_ref="weekly_2026_w20",
        llm_call_fn=lambda p: _LLM_OUTPUT_MIXED,
    )
    routes = route_issues(issues)

    result_json = run_execution_contract(
        issues_json=json.dumps([{
            "issue_id": iss.issue_id,
            "title": iss.title,
            "background": iss.background,
            "source_ref": iss.source_ref,
            "urgency": iss.urgency,
            "options": iss.options,
            "recommended_option": iss.recommended_option,
            "owner_candidate": iss.owner_candidate,
            "acceptance_criteria": iss.acceptance_criteria,
        } for iss in issues]),
        routes_json=json.dumps(routes),
        confirmation_json=None,
    )
    result = json.loads(result_json)

    # 只有 1 个 pending（fake_closure 被过滤）
    assert result["consensus_ledger"]["pending_count"] == 1
    assert result["consensus_ledger"]["fake_closure_count"] == 1
    assert len(result["decision_cards"]) == 1


# ──────────────────────────────────────────────────────────────────────────────
# 3. pending → Feishu 确认 → confirmed（通过 WeeklyLedgerStore）
# ──────────────────────────────────────────────────────────────────────────────

def test_pending_to_confirmed_via_ledger_store(tmp_path):
    issues = extract_issues(
        _RAW_MATERIAL_MIXED,
        source_ref="weekly_2026_w20",
        llm_call_fn=lambda p: _LLM_OUTPUT_MIXED,
    )
    valid_issue = next(i for i in issues if i.recommended_option and "持续跟进" not in i.recommended_option)

    event = ConfirmationEvent(
        issue_id=valid_issue.issue_id,
        decision="采用方案B，涨价 8%",
        execution_owner="张三",
        committed_action="完成定价方案文档并通过 review",
        deadline="2026-06-30",
        acceptance_criteria="Q3 配件毛利率达到 35%",
        verification_evidence="review 通过记录截图",
        event_id="EVT-PROD-001",
    )

    store = WeeklyLedgerStore(home=tmp_path)
    contract = store.apply_event(event, valid_issue, route="decision_agenda")
    assert contract is not None
    assert contract.current_status == "confirmed"
    assert contract.execution_owner == "张三"
    assert contract.issue_id == valid_issue.issue_id

    # 验证 ledger 持久化
    ledger = WeeklyLedgerStore(home=tmp_path).load()
    assert len(ledger.confirmed_contracts) == 1


# ──────────────────────────────────────────────────────────────────────────────
# 4. 完整链路：raw material → decision_gate route → pending → confirmed
# ──────────────────────────────────────────────────────────────────────────────

def test_full_chain_raw_material_to_confirmed(tmp_path):
    # Step 1: IssueExtractor
    issues = extract_issues(
        _RAW_MATERIAL_MIXED,
        source_ref="weekly_2026_w20",
        llm_call_fn=lambda p: _LLM_OUTPUT_MIXED,
    )

    # Step 2: DecisionGate
    routes = route_issues(issues)
    valid_issue = next(i for i in issues if routes[i.issue_id] == "decision_agenda")

    # Step 3: ExecutionContract (pending)
    result_json = run_execution_contract(
        issues_json=json.dumps([{
            "issue_id": iss.issue_id,
            "title": iss.title,
            "background": iss.background,
            "source_ref": iss.source_ref,
            "urgency": iss.urgency,
            "options": iss.options,
            "recommended_option": iss.recommended_option,
            "owner_candidate": iss.owner_candidate,
            "acceptance_criteria": iss.acceptance_criteria,
        } for iss in issues]),
        routes_json=json.dumps(routes),
    )
    result = json.loads(result_json)
    assert result["consensus_ledger"]["pending_count"] == 1

    # Step 4: Feishu 确认 → confirmed
    store = WeeklyLedgerStore(home=tmp_path)
    event = ConfirmationEvent(
        issue_id=valid_issue.issue_id,
        decision="采用方案B",
        execution_owner="张三",
        committed_action="完成定价文档",
        deadline="2026-06-30",
        acceptance_criteria="Q3 毛利达标",
        verification_evidence="review 截图",
        event_id="EVT-FULL-001",
    )
    contract = store.apply_event(event, valid_issue, route="decision_agenda")
    assert contract is not None
    assert contract.current_status == "confirmed"

    # 整个链路：从 raw material 到 confirmed contract
    assert contract.issue_id == valid_issue.issue_id
    assert contract.execution_owner == "张三"


# ──────────────────────────────────────────────────────────────────────────────
# 5. 空材料 → 空 Issue 列表，pipeline 安全完成
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_material_pipeline_safe():
    issues = extract_issues("", source_ref="weekly_empty", llm_call_fn=lambda p: "[]")
    assert issues == []

    result_json = run_execution_contract(
        issues_json=json.dumps([]),
        routes_json=json.dumps({}),
    )
    result = json.loads(result_json)
    assert result["consensus_ledger"]["pending_count"] == 0
    assert result["consensus_ledger"]["confirmed_count"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# P0-3：Provider Integration Tests（mock Anthropic 边界，不注入 llm_call_fn）
# ──────────────────────────────────────────────────────────────────────────────

class TestIssueExtractorProviderIntegration:
    """验证 issue_extractor 通过 provider 边界完整运行，不依赖 llm_call_fn 注入。"""

    def test_extractor_parses_anthropic_response_without_lambda_injection(self, monkeypatch):
        """不传 llm_call_fn，mock anthropic.Anthropic，验证完整解析链路。"""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=_LLM_OUTPUT_MIXED)]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        with patch("anthropic.Anthropic", return_value=mock_client):
            # 关键：不传 llm_call_fn，让 extract_issues 自行构建 provider
            issues = extract_issues(_RAW_MATERIAL_MIXED, source_ref="w_provider_test")

        assert len(issues) >= 1, "issue_extractor 应至少提取 1 个 Issue"
        mock_client.messages.create.assert_called_once()  # 确认真实 provider 调用发生了

    def test_extractor_prompt_contains_raw_material(self, monkeypatch):
        """验证 provider 收到的 prompt 包含原始 raw material 内容。"""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="[]")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_resp

        unique_marker = "UNIQUE_MARKER_XYZ_12345_TEST"
        with patch("anthropic.Anthropic", return_value=mock_client):
            extract_issues(f"周报原材料：{unique_marker}", source_ref="marker_test")

        call_args = mock_client.messages.create.call_args
        messages_sent = call_args[1].get("messages", call_args[0][0] if call_args[0] else [])
        all_content = " ".join(
            str(m.get("content", "")) for m in messages_sent if isinstance(m, dict)
        )
        assert unique_marker in all_content, (
            "raw material 内容应出现在发送给 LLM provider 的 prompt 中"
        )
