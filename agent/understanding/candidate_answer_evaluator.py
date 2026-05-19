"""
CandidateAnswerEvaluator — 6 项候选回答检测，纯本地，无 LLM 调用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from agent.understanding.schemas import BoundaryMemory, UnderstandingState
    from agent.understanding.user_quality_function import UserQualityFunction

_MIXED_RE = [
    re.compile(r"综合来看|综合考虑|综合分析"),
    re.compile(r"(两个问题|这两个|这两类).{0,10}(一起|综合|合并)"),
]
_SCOPE_REGRESSION_RE = [
    re.compile(r"以扫地机器人|以这个扫地|扫地机器人的案例|扫地机器人例子"),
    re.compile(r"(就像|就以|比如说|例如).{0,8}(这个案例|这个例子|这一个具体)"),
    re.compile(r"(只针对|只适用于|仅适用于|专门针对).{0,10}(这个|这类|该).{0,6}(产品|案例|场景|情况)"),
]
_SYSTEM_LAYER_RE = re.compile(r"新(的)?系统层|新层级|机制层|结构化层|新模块|新能力层")
_AGENT_SYS_RE = re.compile(r"agent.{0,4}system|智能体系统|pipeline.{0,4}节点|skill.{0,4}node|workflow.{0,4}节点")


@dataclass
class CandidateAnswerEvaluation:
    overall_pass: bool
    failed_checks: list[str] = field(default_factory=list)
    reason: str = ""
    rewrite_guidance: str = ""
    rewrite_or_clarify: Literal["pass", "rewrite", "clarify"] = "pass"


def _ngrams(text: str, n: int = 2) -> set[str]:
    text = re.sub(r"\s+", "", text)
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def _overlap_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ga, gb = _ngrams(a), _ngrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def evaluate_candidate_answer(
    candidate_answer: str,
    prior_response: str,
    understanding_state: "UnderstandingState",
    boundary_memory: "list[BoundaryMemory]",
    quality_fn: "UserQualityFunction",
) -> CandidateAnswerEvaluation:
    failed: list[str] = []
    guidance_lines: list[str] = []

    # 1. mixed_questions
    if quality_fn.must_separate_questions and candidate_answer:
        if any(p.search(candidate_answer) for p in _MIXED_RE):
            failed.append("mixed_questions")
            guidance_lines.append("- [mixed_questions]: 当前问题需要分别回答，请勿在同一段落综合两个问题")

    # 2. scope_regression
    if quality_fn.must_keep_generalized_scope and candidate_answer:
        if any(p.search(candidate_answer) for p in _SCOPE_REGRESSION_RE):
            failed.append("scope_regression")
            guidance_lines.append("- [scope_regression]: 已要求通用化视角，请勿退回到单一案例")

    # 3. boundary_violation
    if quality_fn.must_avoid_negative_boundaries and candidate_answer:
        for content in quality_fn.must_avoid_negative_boundaries:
            cjk_only = re.sub(r"[^一-鿿]", "", content)
            key_terms = {
                cjk_only[i:i + n]
                for n in (3, 4, 5)
                for i in range(len(cjk_only) - n + 1)
            }
            if key_terms and any(term in candidate_answer for term in key_terms):
                failed.append("boundary_violation")
                guidance_lines.append(f"- [boundary_violation]: 回答触及已否定路径，请调整方向")
                break

    # 4. synonym_paraphrase
    if quality_fn.must_avoid_synonym_paraphrase and prior_response and candidate_answer:
        ratio = _overlap_ratio(prior_response, candidate_answer)
        if ratio > 0.6:
            failed.append("synonym_paraphrase")
            guidance_lines.append("- [synonym_paraphrase]: 本次回答与上一轮高度重复，请提供新角度或新信息")

    # 5. missing_new_system_layer
    if quality_fn.must_add_new_system_layer and candidate_answer:
        if not _SYSTEM_LAYER_RE.search(candidate_answer):
            failed.append("missing_new_system_layer")
            guidance_lines.append("- [missing_new_system_layer]: 用户要求新系统层级，请在回答中说明新层级的设计")

    # 6. missing_agent_system_mechanism
    if quality_fn.must_use_agent_system_mechanism and candidate_answer:
        if not _AGENT_SYS_RE.search(candidate_answer):
            failed.append("missing_agent_system_mechanism")
            guidance_lines.append("- [missing_agent_system_mechanism]: 用户要求 agent system 机制，请在回答中说明具体机制")

    if not failed:
        return CandidateAnswerEvaluation(overall_pass=True)

    _REWRITE_CHECKS = {"mixed_questions", "scope_regression", "boundary_violation", "synonym_paraphrase"}
    _CLARIFY_CHECKS = {"missing_new_system_layer", "missing_agent_system_mechanism"}
    failed_set = set(failed)

    if failed_set & _CLARIFY_CHECKS:
        action: Literal["pass", "rewrite", "clarify"] = "clarify"
    else:
        action = "rewrite"

    guidance = "【修复建议】\n" + "\n".join(guidance_lines)
    return CandidateAnswerEvaluation(
        overall_pass=False,
        failed_checks=failed,
        reason="；".join(failed),
        rewrite_guidance=guidance,
        rewrite_or_clarify=action,
    )
