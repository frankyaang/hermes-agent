"""InsightGapScan — 多轮洞察决策函数（纯规则，不调用 LLM）。

输入：上一轮洞察文本 + 当前轮候选洞察文本 + 可选标志
输出：ScanDecision（7 种决策之一 + 理由）

7 种决策：
  repeat       — 当前轮与上一轮实质相同
  new_insight  — 当前轮有明确新内容
  gap          — 发现两轮之间缺少连接证据或存在矛盾
  revision     — 当前轮修正了上一轮判断
  continue     — 有深挖空间，建议继续
  stop         — 证据足够，停止深挖转执行
  promote      — 洞察质量足以进入 PromotionDecision
"""
from __future__ import annotations

from dataclasses import dataclass

_NEGATION_PATTERNS = ("不是", "并非", "而是", "修正", "更正", "纠正", "不对", "错误")
_UNCERTAINTY_PATTERNS = ("可能", "估计", "猜测", "不确定", "有待", "假设")


def _similarity(a: str, b: str) -> float:
    """字符级 Jaccard 相似度。"""
    if not a or not b:
        return 0.0
    set_a = set(a.strip())
    set_b = set(b.strip())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


@dataclass
class ScanDecision:
    decision: str  # repeat | new_insight | gap | revision | continue | stop | promote
    reason: str


def scan(
    previous: str,
    current: str,
    *,
    check_contradiction: bool = False,
    gap_hint: str = "",
    has_sufficient_evidence: bool = False,
    generalizable: bool = False,
    confidence: str = "",
) -> ScanDecision:
    """InsightGapScan 多轮决策入口。

    优先级（从高到低）：
      1. gap_hint 显式指定 → gap
      2. check_contradiction=True 且两轮内容相似度低 → gap
      3. current 含修正关键词 → revision
      4. generalizable=True + confidence=high → promote
      5. has_sufficient_evidence=True → stop
      6. similarity >= 0.7 → repeat
      7. previous 为空 或 similarity < 0.3 → new_insight
      8. 其他 → continue
    """
    current_stripped = current.strip()
    previous_stripped = previous.strip()

    # 1. 显式 gap_hint
    if gap_hint.strip():
        return ScanDecision(decision="gap", reason=f"显式缺口标记：{gap_hint.strip()[:80]}")

    # 2. 矛盾检测
    if check_contradiction and previous_stripped and current_stripped:
        sim = _similarity(previous_stripped, current_stripped)
        if sim < 0.3:
            return ScanDecision(
                decision="gap",
                reason=f"两轮洞察相似度 {sim:.2f} < 0.3，且 check_contradiction=True，存在潜在矛盾",
            )

    # 3. 修正关键词
    if previous_stripped and current_stripped:
        for pat in _NEGATION_PATTERNS:
            if pat in current_stripped:
                return ScanDecision(
                    decision="revision",
                    reason=f"当前轮含修正关键词 '{pat}'，判断为对上一轮的修正",
                )

    # 4. 可推广 + 高置信度 → 进入 PromotionDecision
    if generalizable and confidence == "high":
        return ScanDecision(
            decision="promote",
            reason="generalizable=True + confidence=high，洞察质量足以进入 PromotionDecision",
        )

    # 5. 足够证据 → 停止
    if has_sufficient_evidence:
        return ScanDecision(
            decision="stop",
            reason="has_sufficient_evidence=True，证据充分，建议停止深挖转执行",
        )

    # 6. 探索性/不确定关键词 → 继续（当有上一轮时）
    if previous_stripped and current_stripped:
        for pat in _UNCERTAINTY_PATTERNS:
            if pat in current_stripped:
                return ScanDecision(
                    decision="continue",
                    reason=f"当前轮含探索性关键词 '{pat}'，建议继续深挖",
                )

    # 7. 高相似度 → 重复
    if previous_stripped and current_stripped:
        sim = _similarity(previous_stripped, current_stripped)
        if sim >= 0.7:
            return ScanDecision(
                decision="repeat",
                reason=f"与上一轮相似度 {sim:.2f} >= 0.7，判断为重复洞察",
            )

        # 8. 低相似度 → 新洞察
        if sim < 0.3:
            return ScanDecision(
                decision="new_insight",
                reason=f"与上一轮相似度 {sim:.2f} < 0.3，判断为新增洞察",
            )

    # 8. 无 previous → 新洞察
    if not previous_stripped:
        return ScanDecision(decision="new_insight", reason="无上一轮洞察，当前轮为首次洞察")

    # 9. 默认 → 继续深挖
    return ScanDecision(
        decision="continue",
        reason="洞察相似度居中，无明确停止信号，建议继续深挖",
    )
