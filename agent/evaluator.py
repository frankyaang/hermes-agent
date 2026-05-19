"""agent/evaluator — evaluator 框架，检测 agent 输出是否违反 usage_hint 和认知治理约束。"""
from __future__ import annotations

from typing import List


def check_output_for_banned_jargon(output: str, banned_words: List[str]) -> List[str]:
    """返回 output 中出现的 banned_words 列表。空列表表示无违规。"""
    return [w for w in banned_words if w in output]


# 认知治理协议违规检测
# 以下函数用于检查 agent 输出是否违反 cognitive_governance SKILL 定义的规则。
# 每个函数返回违规描述列表，空列表表示无违规。

_INSIGHT_KEYWORDS = ("InsightDelta", "洞察内容", "洞察：", "新增洞察")
_SOURCE_EVIDENCE_KEYWORDS = ("来源证据", "source:", "来源：", "引用：")
_ASSUMPTION_KEYWORDS = ("假设", "推断", "猜测", "可能是", "应该是")
_FACT_SECTION_KEYWORDS = ("已知事实", "确认事实", "事实：")
_PROMOTION_EXECUTED_PHRASES = ("已沉淀", "已写入", "已执行沉淀", "沉淀完成", "已更新 MEMORY")
_PROMOTION_PENDING_PHRASES = ("pending_confirmation", "待确认", "等待人工确认")


def check_insight_missing_source(output: str) -> List[str]:
    """检测 InsightDelta 声明是否缺少来源证据。

    规则：出现 InsightDelta 类关键词时，必须在同一段落出现来源证据关键词。
    """
    violations: List[str] = []
    paragraphs = output.split("\n\n")
    for para in paragraphs:
        has_insight = any(k in para for k in _INSIGHT_KEYWORDS)
        has_source = any(k in para for k in _SOURCE_EVIDENCE_KEYWORDS)
        if has_insight and not has_source:
            violations.append("InsightDelta 声明缺少来源证据（违反：来源证据不允许为空）")
    return violations


def check_assumption_listed_as_fact(output: str) -> List[str]:
    """检测假设内容是否被放入已知事实段落（违反 CognitiveState 规则）。"""
    violations: List[str] = []
    lines = output.splitlines()
    in_fact_section = False
    for line in lines:
        if any(k in line for k in _FACT_SECTION_KEYWORDS):
            in_fact_section = True
        elif line.strip().startswith("##") or line.strip().startswith("---"):
            in_fact_section = False
        if in_fact_section and any(k in line for k in _ASSUMPTION_KEYWORDS):
            violations.append(f"假设内容出现在已知事实段落：{line.strip()[:80]}")
    return violations


def check_promotion_auto_executed(output: str) -> List[str]:
    """检测 PromotionDecision 是否被标记为已执行（必须保持 pending_confirmation）。"""
    violations: List[str] = []
    for phrase in _PROMOTION_EXECUTED_PHRASES:
        if phrase in output:
            violations.append(f"PromotionDecision 被标记为已执行（禁止自动沉淀）：'{phrase}'")
    return violations


def check_governance_triggered_for_simple_task(output: str, task_hint: str = "") -> List[str]:
    """检测简单任务（改写/事实问答/单点修复）是否触发了不必要的认知治理框架。

    task_hint: "rewrite" | "factual_qa" | "bug_fix" | ""
    """
    if task_hint not in ("rewrite", "factual_qa", "bug_fix"):
        return []
    governance_keywords = ("ProblemContract", "CognitiveState", "InsightDelta",
                           "PromotionDecision", "问题边界", "gap_scan")
    violations: List[str] = []
    for kw in governance_keywords:
        if kw in output:
            violations.append(f"简单任务（{task_hint}）不应触发认知治理框架，但输出包含：'{kw}'")
    return violations
