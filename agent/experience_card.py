"""ExperienceCard — 结构化动作卡，非普通文本记忆。

经验必须是动作卡：告知下次遇到相似情形时怎么查、怎么写、怎么确认、什么不能做。
触发方式：纯规则关键词匹配（不调用 LLM），保守触发原则。

写入路径：{HERMES_HOME}/experience_cards/cards.jsonl
内置 David 样例卡作为模块常量（不需要文件系统即可触发）。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from hermes_constants import get_hermes_home
from agent.runtime_artifact_evidence import sanitize_summary

logger = logging.getLogger(__name__)


@dataclass
class ExperienceCard:
    id: str
    trigger: str                        # 触发关键词/场景描述（用于规则匹配）
    trigger_patterns: List[str]         # 正则或关键词列表
    retrieval_order: List[str]          # 读取优先级列表
    judgment_steps: List[str]           # 判断步骤
    avoid_actions: List[str]            # 禁止动作
    frontstage_expression: str          # 前台输出风格要求
    scope: str                          # 适用范围（人物/产品线等）
    invalid_when: str                   # 失效条件
    source_case: str                    # 来源 case
    created_at: str
    last_verified_at: str
    status: str = "active"
    producer_runtime_path: str = "agent.experience_card.write_card"
    source_capability: str = "experience_card"
    sanitized_summary: str = ""


# ─── David 样例卡（模块常量，不依赖文件系统）─────────────────────────────────

_NOW = "2026-05-18T00:00:00+00:00"

DAVID_CARD = ExperienceCard(
    id="david-001",
    trigger="David",
    trigger_patterns=["David", "david"],
    retrieval_order=[
        "项目材料/后续版本（最高优先级）",
        "David 长期偏好",
        "个人私下判断（最低优先级，不直接采纳为项目要求）",
    ],
    judgment_steps=[
        "拆公司级背景（ecovacs_company scope）",
        "确认产品线要求（当前版本项目材料）",
        "确认项目动作（PBI/版本计划）",
        "确认用户私下判断（不直接写入项目材料）",
    ],
    avoid_actions=[
        "不要把私聊推演直接写进项目材料",
        "不要把公司级偏好直接当项目要求",
        "不要用系统腔（'晋升'、'生命周期'、'已决策结论' 等后台词）",
    ],
    frontstage_expression="使用自然工作语言，不用系统腔",
    scope="David/high_level_cross_product_context",
    invalid_when="David 本人明确更改了偏好后",
    source_case="case-david-2026",
    created_at=_NOW,
    last_verified_at=_NOW,
)

# 内置卡片列表（从文件写入之前，先用常量）
_BUILTIN_CARDS: list[ExperienceCard] = [DAVID_CARD]


# ─── 触发检测（纯规则，不调用 LLM）──────────────────────────────────────────

def trigger_check(text: str, hermes_home: Path | None = None) -> Optional[ExperienceCard]:
    """检查 text 是否触发某张 ExperienceCard，返回第一张匹配的卡片，否则返回 None。

    优先检查内置卡（常量），再检查持久化卡（文件）。
    规则匹配：关键词出现即触发，保守原则。
    """
    all_cards = list(_BUILTIN_CARDS)
    # 追加从文件加载的用户自定义卡
    for rec in _list_cards_raw(hermes_home=hermes_home):
        try:
            all_cards.append(_dict_to_card(rec))
        except Exception:
            pass

    for card in all_cards:
        for pattern in card.trigger_patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    return card
            except re.error:
                if pattern.lower() in text.lower():
                    return card
    return None


def render_card(card: ExperienceCard) -> str:
    """渲染 ExperienceCard 为带 usage_hint 的文本块，供注入 Agent prompt。"""
    lines = [
        f"[usage_hint: action_rule_for_next_task]",
        f"# ExperienceCard: {card.trigger} (scope: {card.scope})",
        "",
        "## 读取优先级",
    ]
    for i, step in enumerate(card.retrieval_order, 1):
        lines.append(f"  {i}. {step}")
    lines += ["", "## 判断步骤"]
    for i, step in enumerate(card.judgment_steps, 1):
        lines.append(f"  {i}. {step}")
    lines += ["", "## 禁止动作"]
    for action in card.avoid_actions:
        lines.append(f"  - {action}")
    lines += [
        "",
        f"## 前台表达要求",
        f"  {card.frontstage_expression}",
        "",
        f"## 失效条件",
        f"  {card.invalid_when}",
    ]
    return "\n".join(lines)


# ─── 持久化接口 ──────────────────────────────────────────────────────────────

def write_card(card: ExperienceCard, hermes_home: Path | None = None) -> str:
    """将 ExperienceCard 追加写入 JSONL，返回 card.id，never raises。"""
    try:
        if not card.sanitized_summary:
            card.sanitized_summary = sanitize_summary(card.trigger, card.scope, card.source_case)
        base = hermes_home or get_hermes_home()
        path = base / "experience_cards" / "cards.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(card), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("write_card failed (non-fatal): %s", exc)
    return card.id


def _list_cards_raw(hermes_home: Path | None = None) -> list[dict]:
    base = hermes_home or get_hermes_home()
    path = base / "experience_cards" / "cards.jsonl"
    if not path.exists():
        return []
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    except Exception as exc:
        logger.warning("_list_cards_raw failed: %s", exc)
    return records


def _dict_to_card(d: dict) -> ExperienceCard:
    return ExperienceCard(
        id=d.get("id", ""),
        trigger=d.get("trigger", ""),
        trigger_patterns=d.get("trigger_patterns", []),
        retrieval_order=d.get("retrieval_order", []),
        judgment_steps=d.get("judgment_steps", []),
        avoid_actions=d.get("avoid_actions", []),
        frontstage_expression=d.get("frontstage_expression", ""),
        scope=d.get("scope", ""),
        invalid_when=d.get("invalid_when", ""),
        source_case=d.get("source_case", ""),
        created_at=d.get("created_at", ""),
        last_verified_at=d.get("last_verified_at", ""),
        status=d.get("status", "active"),
        producer_runtime_path=d.get(
            "producer_runtime_path", "agent.experience_card.write_card"
        ),
        source_capability=d.get("source_capability", "experience_card"),
        sanitized_summary=d.get("sanitized_summary", ""),
    )


def create_card(
    trigger: str,
    trigger_patterns: List[str],
    retrieval_order: List[str],
    judgment_steps: List[str],
    avoid_actions: List[str],
    frontstage_expression: str,
    scope: str,
    invalid_when: str,
    source_case: str = "",
) -> ExperienceCard:
    """创建新 ExperienceCard，自动填充 id 和时间戳。"""
    now = datetime.now(timezone.utc).isoformat()
    return ExperienceCard(
        id=str(uuid.uuid4()),
        trigger=trigger,
        trigger_patterns=trigger_patterns,
        retrieval_order=retrieval_order,
        judgment_steps=judgment_steps,
        avoid_actions=avoid_actions,
        frontstage_expression=frontstage_expression,
        scope=scope,
        invalid_when=invalid_when,
        source_case=source_case,
        created_at=now,
        last_verified_at=now,
        sanitized_summary=sanitize_summary(trigger, scope, source_case),
    )
