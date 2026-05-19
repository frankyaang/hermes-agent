"""
CorrectionClassifier — 纯函数，无副作用，无 LLM 调用。

基于 regex + heuristics，覆盖 7 类纠偏 pattern。
精度目标：correction_classification_accuracy ≥ 0.85。

Invariants：
  - 所有 scope 默认 local；升级到 session/global 需要明确触发词
  - regression_correction 的检测依赖上下文（需传入 prior_corrections）
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.understanding.schemas import CorrectionClassification, CorrectionType, BoundaryScope

# ──────────────────────────────────────────────
# 分类规则：每类一组 pattern，按优先级排列
# ──────────────────────────────────────────────

_SEPARATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(两个|这两个|这两类|多个).{0,8}(问题|任务|方向).{0,8}(分别|独立|分开).{0,8}(思考|回答|处理|分析)"),
    re.compile(r"(分别|独立|分开).{0,8}(思考|回答|处理|分析).{0,8}(这?两个|这?多个)"),
    re.compile(r"不要(混|合|放).{0,4}(在一起|到一起|成一个)"),
    re.compile(r"(这是|它们是).{0,4}两个?(独立|不同|分开)"),
    re.compile(r"分开(来|分别|各自).{0,4}(看|想|答|处理)"),
    re.compile(r"不要把.{0,8}(放在一起|合在一起|混在一起).{0,8}分开"),
    re.compile(r"分开(处理|回答|分析|考虑)"),
]

_GENERALIZATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(太|过于|比较).{0,4}(具体|局限|狭窄|单一|片面)"),
    re.compile(r"(应该|需要|要).{0,4}(更通用|更普遍|更广|更宏观|抽象|泛化)"),
    re.compile(r"(不要|别).{0,4}(局限|限定|绑定|针对).{0,8}(一个|某个|这个|单一|具体)"),
    re.compile(r"(通用|普适|一般化|泛化)(解?法|方案|思路|框架)"),
    re.compile(r"(不只是|不仅仅是|不单单是).{0,8}(这个案例|这个例子|这一个)"),
]

_FACT_CORRECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(不对|错了|不是这样|不对的|这不准确)"),
    re.compile(r"(实际上|事实上|其实|准确来说).{0,4}(是|不是|应该是)"),
    re.compile(r"你(说错了|理解错了|搞错了|搞混了)"),
    re.compile(r"(纠正|更正|修正).{0,4}(一下|你|刚才)"),
]

_SCOPE_CORRECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(范围|边界).{0,4}(太宽|太广|太大|太窄|太小|太限|不对)"),
    re.compile(r"(只|仅|专注于|聚焦于|限于).{0,8}(这个|这部分|这块|这里)"),
    re.compile(r"(不用|不需要|别|不要).{0,4}(考虑|包括|涵盖).{0,8}(这|那|其他|额外)"),
    re.compile(r"(扩大|缩小|收窄|拓展).{0,4}(范围|边界|讨论)"),
]

_FRAME_CORRECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(换个|换一个|换种|换一种).{0,4}(角度|思路|框架|方式|视角)"),
    re.compile(r"(不是这个|不是从这个).{0,4}(角度|思路|维度)"),
    re.compile(r"(应该从|要从|得从).{0,8}(角度|维度|视角).{0,4}(来|去)?(看|想|分析)"),
]

_DEPTH_CORRECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(太|过于).{0,4}(浅|表面|简单|基础)"),
    re.compile(r"(太|过于).{0,4}(深|复杂|详细|冗长|繁琐)"),
    re.compile(r"(更深|深入|深一点|更深层).{0,4}(分析|思考|展开|探讨)"),
    re.compile(r"(简单|简短|精简|简洁).{0,4}(一点|点|些)"),
]

_REGRESSION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(又|还是|又在|你又).{0,4}(回到|用|说|提).{0,8}(之前|刚才|上面)"),
    re.compile(r"(说过了|讲过了|提过了|我说过).{0,4}(不要|别|不用)"),
    re.compile(r"(还是|仍然|依然).{0,4}(犯|出现|重复).{0,4}(这个|同样|一样)"),
]

# scope 升级触发词
_GLOBAL_SCOPE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"以后.{0,4}(都|每次|永远|任何时候)"),
    re.compile(r"永远(不要|不能|都要|都应该)"),
    re.compile(r"从今(以后|往后|起).{0,4}(都|每次)"),
    re.compile(r"(以后|今后|未来).{0,4}(每次|所有|任何).{0,4}(情况|时候|场合)"),
]

_SESSION_SCOPE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(这次|本次|这个).{0,4}对话.{0,4}(都|里|中).{0,4}(要|应该|需要)"),
    re.compile(r"(整个|这整个|这次).{0,4}(对话|会话|讨论).{0,4}(都|里|内)"),
]


def _detect_scope(text: str) -> "BoundaryScope":
    if any(p.search(text) for p in _GLOBAL_SCOPE_PATTERNS):
        return "global"
    if any(p.search(text) for p in _SESSION_SCOPE_PATTERNS):
        return "session"
    return "local"


def classify_correction(
    user_message: str,
    turn_index: int = 0,
    prior_corrections: list["CorrectionClassification"] | None = None,
) -> "CorrectionClassification":
    """
    对单条用户消息进行纠偏分类。

    返回 CorrectionClassification，correction_type 为以下之一：
      separation_correction / generalization_correction / fact_correction /
      scope_correction / frame_correction / depth_correction /
      regression_correction / none

    优先级（从高到低）：
      1. separation_correction   — 明确要求分别思考
      2. generalization_correction — 明确要求更通用
      3. regression_correction   — 仅在有 prior_corrections 时检测
      4. fact_correction         — 纠正事实
      5. scope_correction        — 调整范围
      6. frame_correction        — 换框架
      7. depth_correction        — 调整深度
      8. none                    — 非纠偏
    """
    from agent.understanding.schemas import CorrectionClassification

    text = user_message.strip()
    scope = _detect_scope(text)

    def _make(ct: "CorrectionType", confidence: float = 0.85) -> "CorrectionClassification":
        return CorrectionClassification(
            turn_index=turn_index,
            correction_type=ct,
            description=text[:200],
            scope=scope,
            confidence=confidence,
        )

    # 优先级 1
    if any(p.search(text) for p in _SEPARATION_PATTERNS):
        return _make("separation_correction", 0.90)

    # 优先级 2
    if any(p.search(text) for p in _GENERALIZATION_PATTERNS):
        return _make("generalization_correction", 0.88)

    # 优先级 3（需要上下文）
    if prior_corrections and any(p.search(text) for p in _REGRESSION_PATTERNS):
        return _make("regression_correction", 0.80)

    # 优先级 4
    if any(p.search(text) for p in _FACT_CORRECTION_PATTERNS):
        return _make("fact_correction", 0.85)

    # 优先级 5
    if any(p.search(text) for p in _SCOPE_CORRECTION_PATTERNS):
        return _make("scope_correction", 0.82)

    # 优先级 6
    if any(p.search(text) for p in _FRAME_CORRECTION_PATTERNS):
        return _make("frame_correction", 0.80)

    # 优先级 7
    if any(p.search(text) for p in _DEPTH_CORRECTION_PATTERNS):
        return _make("depth_correction", 0.80)

    return _make("none", 1.0)


def classify_corrections_batch(
    messages: list[str],
    prior_corrections: list["CorrectionClassification"] | None = None,
) -> list["CorrectionClassification"]:
    """批量分类，返回与 messages 等长的分类结果列表。"""
    results: list["CorrectionClassification"] = []
    for i, msg in enumerate(messages):
        result = classify_correction(msg, turn_index=i, prior_corrections=prior_corrections)
        results.append(result)
        prior_corrections = (prior_corrections or []) + [result]
    return results
