"""
Decision Gate — 纯函数路由器，无副作用，无 LLM 调用，可在 CI 零成本运行。

路由 invariants（代码级硬约束）：
  1. recommended_option is None  → need_more_info（不得进 decision_agenda）
  2. acceptance_criteria is None → need_more_info（不得进 decision_agenda）
  3. fake_closure_detected       → 不得转成 Commitment
  4. fake_closure 检测优先于其他所有路由
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_system.schemas.weekly_schemas import Issue, DecisionRoute

# 7 类核心伪闭环模式（可配置扩展，无需改代码）
FAKE_CLOSURE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"后续.{0,4}(持续跟进|继续推进|再看|持续推动|跟进)"),
    re.compile(r"产品线.{0,4}(配合一下|跟进)"),
    re.compile(r"会后再(看|跟进|确认|讨论)"),
    re.compile(r"原则上(认可|同意|支持|没问题)"),
    re.compile(r"先试试(看|再说|再评估)"),
    re.compile(r"尽快(推动|落实|跟进|完成|推进)"),
    re.compile(r"持续跟进"),
]


def _is_fake_closure(issue: "Issue") -> bool:
    """检测议题是否含伪闭环语言（title + background + recommended_option 联合检测）。"""
    text = (
        (issue.title or "")
        + (issue.background or "")
        + (issue.recommended_option or "")
    )
    return any(p.search(text) for p in FAKE_CLOSURE_PATTERNS)


def route_issue(issue: "Issue") -> "DecisionRoute":
    """
    对单个 Issue 做路由决策，返回 DecisionRoute 字面量。

    优先级（从高到低）：
      1. fake_closure_detected — 伪闭环拦截
      2. need_more_info       — 缺 recommended_option 或 acceptance_criteria
      3. async_pre_read       — 低紧迫度且选项过多
      4. decision_agenda      — 条件全满足
    """
    # 优先级 1：fake closure 检测
    if _is_fake_closure(issue):
        return "fake_closure_detected"

    # 优先级 2：缺关键字段 → 信息不足
    if issue.recommended_option is None:
        return "need_more_info"
    if issue.acceptance_criteria is None:
        return "need_more_info"

    # 优先级 3：低紧迫度 + 选项过多 → 异步预读
    if issue.urgency == "low" and len(issue.options) > 3:
        return "async_pre_read"

    # 优先级 4：条件全满足 → 进入决策议程
    return "decision_agenda"


def route_issues(issues: list["Issue"]) -> dict[str, "DecisionRoute"]:
    """批量路由，返回 {issue_id: route} 映射。"""
    return {issue.issue_id: route_issue(issue) for issue in issues}


def assert_no_invalid_decision_agenda(issues: list["Issue"]) -> None:
    """
    Invariant 检查器：缺 recommended_option 或 acceptance_criteria 的议题
    不得出现在 decision_agenda 中。失败时抛出 AssertionError。
    用于测试和生产前置检查。
    """
    for issue in issues:
        route = route_issue(issue)
        if route == "decision_agenda":
            assert issue.recommended_option is not None, (
                f"Invariant violated: issue '{issue.issue_id}' routed to decision_agenda "
                f"but recommended_option is None"
            )
            assert issue.acceptance_criteria is not None, (
                f"Invariant violated: issue '{issue.issue_id}' routed to decision_agenda "
                f"but acceptance_criteria is None"
            )
