"""
IssueExtractor skill — 从自由格式周报原材料中提取结构化 Issue 列表。

约束：
  - LLM 禁止推断缺失字段（recommended_option / owner_candidate 缺失时输出 null）
  - LLM 输出必须通过 Issue schema 强验证
  - 验证失败的 Issue 记录日志后跳过，不阻断整体流程
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from agent_system.schemas.weekly_schemas import Issue

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
你是议题提取助手。请从以下周报原材料中提取所有需要决策或跟进的议题，以 JSON 数组形式输出。

输出格式（JSON 数组，每项为一个议题）：
[
  {
    "title": "议题标题（简洁，≤30字）",
    "background": "背景说明（客观描述现状和问题）",
    "source_ref": "来源标记（如 weekly_2026_w20）",
    "urgency": "high|medium|low",
    "options": ["备选方案A", "备选方案B"],
    "recommended_option": "明确推荐的方案（原文无明确推荐时必须输出 null）",
    "owner_candidate": "负责人（原文无明确负责人时必须输出 null）",
    "acceptance_criteria": "验收标准（原文无明确标准时必须输出 null）"
  }
]

严格规则：
1. recommended_option：只能提取原文中明确出现的推荐方案，绝对不能推断或猜测，没有就输出 null
2. owner_candidate：只能提取原文中明确出现的负责人姓名，没有就输出 null
3. acceptance_criteria：只能提取原文中明确的验收标准，没有就输出 null
4. 如果原材料中没有需要决策的议题，输出空数组 []
5. 只输出 JSON，不要有其他文字

周报原材料：
{material}
"""


def _make_default_llm_call():
    """委托给 hermes_llm_provider，获取 Hermes 配置感知的 LLM 调用函数。"""
    from agent_system.providers.hermes_llm_provider import make_hermes_llm_call
    return make_hermes_llm_call()


def _make_default_llm_call_legacy():
    """旧实现保留备用（不再使用）。"""
    try:
        import anthropic
        client = anthropic.Anthropic()

        def _call(prompt: str) -> str:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()

        return _call
    except Exception as exc:
        logger.warning(
            "issue_extractor: cannot create default Anthropic LLM call (%s); "
            "returning empty-list fallback. Pass llm_call_fn explicitly to use a real LLM.",
            exc,
        )

        def _noop(prompt: str) -> str:
            return "[]"

        return _noop


def extract_issues(
    material: str,
    source_ref: str = "weekly_unknown",
    llm_call_fn=None,
) -> list[Issue]:
    """
    从自由格式周报原材料中提取 Issue 列表。

    Args:
        material: 周报原材料文本（任意格式）
        source_ref: 来源标识符，用于追踪（如 "weekly_2026_w20"）
        llm_call_fn: LLM 调用函数，签名 (prompt: str) -> str。
                     为 None 时抛出 RuntimeError（测试中应传入 mock）

    Returns:
        经过 schema 验证的 Issue 列表；验证失败的条目被跳过并记录日志。
    """
    if llm_call_fn is None:
        llm_call_fn = _make_default_llm_call()

    prompt = _EXTRACTION_PROMPT.replace("{material}", material)
    raw_output = llm_call_fn(prompt)

    try:
        raw_list = json.loads(raw_output)
    except json.JSONDecodeError as e:
        logger.error("issue_extractor: LLM output is not valid JSON: %s", e)
        return []

    if not isinstance(raw_list, list):
        logger.error("issue_extractor: LLM output is not a JSON array, got %s", type(raw_list))
        return []

    issues: list[Issue] = []
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            logger.warning("issue_extractor: item[%d] is not a dict, skipping", i)
            continue
        try:
            issue = _parse_issue(item, source_ref)
            issues.append(issue)
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("issue_extractor: item[%d] schema validation failed: %s", i, e)
            continue

    logger.info(
        "issue_extractor: extracted %d issues (%d with recommended_option) from %s",
        len(issues),
        sum(1 for x in issues if x.recommended_option is not None),
        source_ref,
    )
    return issues


def _parse_issue(item: dict, fallback_source_ref: str) -> Issue:
    """Parse and validate a single raw dict into an Issue dataclass."""
    title = str(item["title"]).strip()
    if not title:
        raise ValueError("title is empty")

    background = str(item.get("background", "")).strip()
    source_ref = str(item.get("source_ref", fallback_source_ref)).strip() or fallback_source_ref
    urgency_raw = str(item.get("urgency", "medium")).lower()
    urgency = urgency_raw if urgency_raw in ("high", "medium", "low") else "medium"

    options = item.get("options", [])
    if not isinstance(options, list):
        options = []
    options = [str(o) for o in options if o]

    recommended_option = item.get("recommended_option")
    if recommended_option is not None:
        recommended_option = str(recommended_option).strip() or None

    owner_candidate = item.get("owner_candidate")
    if owner_candidate is not None:
        owner_candidate = str(owner_candidate).strip() or None

    acceptance_criteria = item.get("acceptance_criteria")
    if acceptance_criteria is not None:
        acceptance_criteria = str(acceptance_criteria).strip() or None

    return Issue(
        title=title,
        background=background,
        source_ref=source_ref,
        urgency=urgency,  # type: ignore[arg-type]
        options=options,
        recommended_option=recommended_option,
        owner_candidate=owner_candidate,
        acceptance_criteria=acceptance_criteria,
    )
