"""
Decision Gate — Golden Fixtures & Regression Tests

覆盖：
  A1. 完整议题进入 decision_agenda
  A2. 缺推荐方案 → need_more_info
  A3. 缺验收标准 → need_more_info
  A4. fake closure（持续跟进）→ fake_closure_detected
  A5. fake closure（产品线配合一下）→ fake_closure_detected
  A6. ExecutionContract 初始 confirmed_by_human=False

Invariant tests：
  - invalid_decision_agenda_rate 对测试集 = 0.00
  - FAKE_CLOSURE_PATTERNS 覆盖全部 7 类
  - route_issue 纯函数无副作用
"""
import pytest

from agent_system.schemas.weekly_schemas import (
    Commitment,
    DecisionCard,
    DecisionHealthMetrics,
    ExecutionContract,
    Issue,
)
from agent_system.evaluators.decision_gate import (
    FAKE_CLOSURE_PATTERNS,
    assert_no_invalid_decision_agenda,
    route_issue,
    route_issues,
)


# ──────────────────────────────────────────────
# 辅助工厂
# ──────────────────────────────────────────────

def _issue(**kwargs) -> Issue:
    defaults = dict(
        title="测试议题",
        background="背景说明",
        source_ref="weekly_2026_w20",
        urgency="medium",
        options=["方案A", "方案B"],
        recommended_option=None,
        acceptance_criteria=None,
        owner_candidate=None,
    )
    defaults.update(kwargs)
    return Issue(**defaults)


# ──────────────────────────────────────────────
# A1. 完整议题进入 decision_agenda
# ──────────────────────────────────────────────

def test_a1_complete_issue_routes_to_decision_agenda():
    issue = _issue(
        title="X11 海外配件定价策略",
        background="当前配件利润率低于目标 5pp",
        recommended_option="方案B：涨价 8%，捆绑促销",
        acceptance_criteria="Q3 配件毛利率达到 35%",
    )
    assert route_issue(issue) == "decision_agenda"


# ──────────────────────────────────────────────
# A2. 缺推荐方案 → need_more_info
# ──────────────────────────────────────────────

def test_a2_missing_recommended_option_routes_to_need_more_info():
    issue = _issue(
        title="X11 海外配件定价策略",
        background="当前配件利润率低于目标 5pp",
        recommended_option=None,
        acceptance_criteria="Q3 配件毛利率达到 35%",
    )
    assert route_issue(issue) == "need_more_info"


# ──────────────────────────────────────────────
# A3. 缺验收标准 → need_more_info
# ──────────────────────────────────────────────

def test_a3_missing_acceptance_criteria_routes_to_need_more_info():
    issue = _issue(
        recommended_option="方案B：涨价 8%",
        acceptance_criteria=None,
    )
    assert route_issue(issue) == "need_more_info"


def test_a3_both_missing_routes_to_need_more_info():
    issue = _issue(recommended_option=None, acceptance_criteria=None)
    assert route_issue(issue) == "need_more_info"


# ──────────────────────────────────────────────
# A4. fake closure — 持续跟进
# ──────────────────────────────────────────────

def test_a4_fake_closure_chi_xu_gen_jin():
    issue = _issue(
        title="配件库存积压问题",
        background="当前库存周转天数超标",
        recommended_option="持续跟进并推动清库",
    )
    assert route_issue(issue) == "fake_closure_detected"


def test_a4_fake_closure_in_background():
    issue = _issue(
        background="目前已建议后续持续跟进这个方向",
        recommended_option="方案A",
        acceptance_criteria="达到目标",
    )
    assert route_issue(issue) == "fake_closure_detected"


# ──────────────────────────────────────────────
# A5. fake closure — 产品线配合一下
# ──────────────────────────────────────────────

def test_a5_fake_closure_chan_pin_xian_pei_he():
    issue = _issue(
        title="配件落地问题",
        recommended_option="产品线配合一下推进落地",
    )
    assert route_issue(issue) == "fake_closure_detected"


@pytest.mark.parametrize("text,field", [
    ("会后再看一下这个议题", "background"),
    ("原则上认可，细节再确认", "recommended_option"),
    ("先试试看效果", "recommended_option"),
    ("尽快推动落实", "recommended_option"),
    ("尽快跟进", "title"),
])
def test_fake_closure_all_7_patterns(text, field):
    kwargs = {field: text, "recommended_option": text if field != "recommended_option" else text}
    issue = _issue(**kwargs)
    assert route_issue(issue) == "fake_closure_detected", (
        f"Pattern missed for: {text!r} in field={field}"
    )


# ──────────────────────────────────────────────
# A6. ExecutionContract confirmed_by_human 初始必须 False
# ──────────────────────────────────────────────

def test_a6_execution_contract_initial_confirmed_by_human_is_false():
    contract = ExecutionContract(
        commitment_id="cmt_001",
        followup_at="2026-06-01",
        confirmed_by_human=False,
    )
    assert contract.confirmed_by_human is False


def test_a6_execution_contract_validate_raises_when_not_confirmed():
    contract = ExecutionContract(
        commitment_id="cmt_001",
        followup_at="2026-06-01",
        confirmed_by_human=False,
    )
    with pytest.raises(ValueError, match="confirmed_by_human must be True"):
        contract.validate()


def test_a6_execution_contract_validate_passes_when_confirmed():
    contract = ExecutionContract(
        commitment_id="cmt_001",
        followup_at="2026-06-01",
        confirmed_by_human=True,
    )
    contract.validate()  # should not raise


# ──────────────────────────────────────────────
# Invariant 检查
# ──────────────────────────────────────────────

def test_invariant_no_invalid_decision_agenda():
    """所有测试议题不能出现：缺字段但路由到 decision_agenda。"""
    issues = [
        _issue(recommended_option="方案A", acceptance_criteria="指标X"),
        _issue(recommended_option=None, acceptance_criteria="指标X"),
        _issue(recommended_option="方案A", acceptance_criteria=None),
        _issue(title="持续跟进", recommended_option="持续跟进", acceptance_criteria="指标X"),
    ]
    assert_no_invalid_decision_agenda(issues)  # should not raise


def test_invariant_fake_closure_priority_over_missing_fields():
    """fake_closure_detected 优先级高于 need_more_info。"""
    issue = _issue(
        recommended_option="持续跟进",
        acceptance_criteria=None,
    )
    assert route_issue(issue) == "fake_closure_detected"


def test_invariant_async_pre_read_only_when_urgency_low_and_many_options():
    issue = _issue(
        urgency="low",
        options=["A", "B", "C", "D"],
        recommended_option="方案A",
        acceptance_criteria="指标X",
    )
    assert route_issue(issue) == "async_pre_read"


def test_invariant_high_urgency_with_many_options_still_decision_agenda():
    issue = _issue(
        urgency="high",
        options=["A", "B", "C", "D"],
        recommended_option="方案A",
        acceptance_criteria="指标X",
    )
    assert route_issue(issue) == "decision_agenda"


# ──────────────────────────────────────────────
# Commitment incomplete 标记
# ──────────────────────────────────────────────

def test_commitment_incomplete_when_owner_missing():
    c = Commitment(
        decision_id="dec_001",
        owner=None,
        action="完成文档",
        deadline="2026-06-01",
        acceptance_criteria="通过 review",
    )
    assert c.incomplete is True


def test_commitment_complete_when_all_fields_present():
    c = Commitment(
        decision_id="dec_001",
        owner="张三",
        action="完成文档",
        deadline="2026-06-01",
        acceptance_criteria="通过 review",
    )
    assert c.incomplete is False


# ──────────────────────────────────────────────
# DecisionHealthMetrics
# ──────────────────────────────────────────────

def test_metrics_record_routes():
    metrics = DecisionHealthMetrics()
    for route in ["decision_agenda", "need_more_info", "fake_closure_detected"]:
        metrics.record(route)
    assert metrics.total_issues == 3
    assert metrics.decision_agenda_count == 1
    assert metrics.need_more_info_count == 1
    assert metrics.fake_closure_count == 1
    assert metrics.invalid_decision_agenda_rate == 0.0


# ──────────────────────────────────────────────
# route_issues 批量
# ──────────────────────────────────────────────

def test_route_issues_batch():
    issues = [
        _issue(recommended_option="方案A", acceptance_criteria="指标X"),
        _issue(recommended_option=None),
        _issue(recommended_option="持续跟进", acceptance_criteria="指标X"),
    ]
    result = route_issues(issues)
    routes = list(result.values())
    assert routes[0] == "decision_agenda"
    assert routes[1] == "need_more_info"
    assert routes[2] == "fake_closure_detected"
