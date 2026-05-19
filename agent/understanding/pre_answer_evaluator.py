"""
PreAnswerEvaluation — 纯函数，无 LLM 调用，无副作用。

4 项检测，目标延迟 < 5ms：
  1. check_mixed_questions    — split_frame=True 后，draft 是否混题
  2. check_boundary_violation — draft 是否含 negative boundary 的核心词组
  3. check_scope_regression   — widen_scope=True 后，draft 是否退回单一具体案例
  4. check_synonym_paraphrase — confidence > 0.9 时，draft 与最近 prior response 关键词重叠 > 80%
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.understanding.schemas import BoundaryMemory, PreAnswerEvaluation, UnderstandingState

# 混题关键词（在 split_frame=True 时触发）
_MIXED_QUESTION_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"(综合来看|综合考虑|综合分析)"),
    re.compile(r"(两个问题|这两个|这两类).{0,10}(一起|综合|合并)"),
    re.compile(r"(针对|关于).{0,10}(问题1|问题2|第一个|第二个).{0,20}(同时|也|以及).{0,10}(问题2|问题1|第二个|第一个)"),
]

# 范围回退关键词（在 widen_scope=True 时触发，匹配明显的单一案例回退）
_SCOPE_REGRESSION_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"(以扫地机器人|以这个扫地|扫地机器人的案例|扫地机器人例子)"),
    re.compile(r"(就像|就以|比如说|例如).{0,8}(这个案例|这个例子|这一个具体)"),
    re.compile(r"(只针对|只适用于|仅适用于|专门针对).{0,10}(这个|这类|该).{0,6}(产品|案例|场景|情况)"),
]


def _extract_last_assistant_text(draft_messages: list) -> str:
    """从消息列表中提取最后一条 assistant 消息的文本内容。"""
    for msg in reversed(draft_messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts)
    return ""


def _keyword_overlap_ratio(text_a: str, text_b: str) -> float:
    """计算两段文本的中文关键词重叠率（基于字符 n-gram，简单启发式）。"""
    if not text_a or not text_b:
        return 0.0
    # 用 2-gram 作为关键词单元，适合中文
    def ngrams(text: str, n: int = 2) -> set[str]:
        text = re.sub(r"\s+", "", text)
        return {text[i:i+n] for i in range(len(text) - n + 1)}

    grams_a = ngrams(text_a)
    grams_b = ngrams(text_b)
    if not grams_a or not grams_b:
        return 0.0
    intersection = grams_a & grams_b
    return len(intersection) / min(len(grams_a), len(grams_b))


def evaluate_pre_answer(
    draft_messages: list,
    understanding_state: "UnderstandingState | None",
    boundary_memory: "list[BoundaryMemory]",
    prior_response: str = "",
) -> "PreAnswerEvaluation":
    """
    在 API call 前对 draft 回答进行 4 项本地检测。

    Args:
        draft_messages: 即将发送给 API 的消息列表（含 system + history + 最新 user message）
        understanding_state: 当前 session 理解状态（可为 None，届时跳过状态相关检测）
        boundary_memory: session 内积累的 BoundaryMemory 列表
        prior_response: 上一轮 assistant 回答（用于 paraphrase 检测）

    Returns:
        PreAnswerEvaluation（overall_pass=False 时至少有一项检测触发）
    """
    from agent.understanding.schemas import PreAnswerEvaluation

    draft_text = _extract_last_assistant_text(draft_messages)

    check_mixed = False
    check_violation = False
    check_regression = False
    check_paraphrase = False

    # 1. check_mixed_questions
    if understanding_state is not None and understanding_state.split_frame and draft_text:
        check_mixed = any(p.search(draft_text) for p in _MIXED_QUESTION_KEYWORDS)

    # 2. check_boundary_violation
    if boundary_memory and draft_text:
        for bm in boundary_memory:
            if bm.boundary_type != "negative":
                continue
            # 提取 3-5 字 CJK n-gram 作为关键词，检测是否出现在 draft 中
            cjk_only = re.sub(r"[^一-鿿]", "", bm.content)
            key_terms = {
                cjk_only[i:i+n]
                for n in (3, 4, 5)
                for i in range(len(cjk_only) - n + 1)
            }
            if any(term in draft_text for term in key_terms):
                check_violation = True
                break

    # 3. check_scope_regression
    if understanding_state is not None and understanding_state.widen_scope and draft_text:
        check_regression = any(p.search(draft_text) for p in _SCOPE_REGRESSION_KEYWORDS)

    # 4. check_synonym_paraphrase（仅在 confidence > 0.9 时触发）
    if (understanding_state is not None
            and understanding_state.confidence > 0.9
            and prior_response
            and draft_text):
        ratio = _keyword_overlap_ratio(prior_response, draft_text)
        check_paraphrase = ratio > 0.6

    return PreAnswerEvaluation(
        check_mixed_questions=check_mixed,
        check_synonym_paraphrase=check_paraphrase,
        check_boundary_violation=check_violation,
        check_scope_regression=check_regression,
    )
