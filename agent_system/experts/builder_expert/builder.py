"""
Builder Expert state machine — Task #8 first slice.

Owns stages INTAKE → ARCHITECT (3a reuse scan) → DRAFT(stub).

The dispatcher (agent_system/builder_dispatcher.py) routes every in-mode user
message through `handle()`. Each call advances the state machine by one round
and persists the updated state back to disk.

Scope of this slice:
- INTAKE: full sequential 5-question flow + optional form
- ARCHITECT 3a: keyword/skill-overlap reuse scan, returns top-3 candidates
- ARCHITECT 3b/3c: template-based proposal placeholder (LLM upgrade is the
  follow-up half of Task #8)
- DRAFT/VALIDATE/DRY_RUN/TRIAL_RUN/COMMIT: stubs that hand control back with
  a clear "not implemented yet" marker, so end-to-end smoke tests still flow
  through every transition.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Order matters — this is the canonical INTAKE question sequence.
INTAKE_QUESTIONS: list[tuple[str, str, str]] = [
    ("Q1", "business_goal", "你想解决什么问题？请用一句话描述业务目标。"),
    ("Q2", "scenario", "这个能力什么时候被调用？\n  • 定时（cron）\n  • 用户主动（聊天关键词 / 命令）\n  • 事件驱动（某 pipeline 完成后 / 某 channel 收到特定消息）\n（也可以直接说时间/频率/触发方式，比如\"每周一早上\"或\"用户喊我才跑\"，我会自动归类。）"),
    ("Q3", "input_type", "典型输入是什么类型？（VOC / 工单 / 评论 / 竞品数据 / 用户上传文件 / 多模态 / 已有数据源）"),
    ("Q4", "output_type", "期望产出什么？（报告 / 异常清单 / 看板结构 / 对话回复 / 写入数据库）"),
    ("Q5", "pipeline_description", "请一步一步描述这个能力的执行流程，比如\"先 X，再 Y，最后 Z\"。\n（前面讲过的输入/产出不用重说，重点说步骤顺序——这是架构推断的核心依据。）"),
]

OPTIONAL_PROMPT = (
    "必填项已收齐。下面这些是选填，可一次性填，没有就回复 \"默认\" 或 \"跳过\"：\n"
    "  • 期望最长运行时间（默认 300 秒）\n"
    "  • 优先级 high / normal / low（默认 normal）\n"
    "  • 谁可以调用（owner / 全体 / 群白名单，默认 owner）\n"
    "  • 是否需要人工审核（user_gate，默认 false）\n"
    "  • 是否定时（如选定时，请同时提供 cron 或周期描述）"
)

PROGRESS_LABELS = {
    "INTAKE": "📋 阶段 1/9：需求收集（INTAKE）",
    "ARCHITECT": "🏗 阶段 2/9：架构推断（ARCHITECT）",
    "DRAFT": "📄 阶段 3/9：草稿生成（DRAFT）",
    "VALIDATE": "✅ 阶段 4/9：自动校验（VALIDATE）",
    "DRY_RUN": "🧪 阶段 5/9：dry-run（含 mock 数据）",
    "TRIAL_RUN": "🚦 阶段 6/9：试运行（真实数据）",
    "COMMIT": "💾 阶段 7/9：落盘（COMMIT）",
    "NEXT_OR_EXIT": "🔁 阶段 8/9：继续 / 退出",
}


# ---------- state I/O ----------

def load_state(state_path: Path) -> dict[str, Any]:
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any], state_path: Path) -> None:
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _push_history(state: dict[str, Any], stage: str) -> None:
    state.setdefault("history", []).append(
        {"stage": stage, "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    )


# ---------- INTAKE ----------

def _next_intake_question(intake: dict[str, Any]) -> tuple[str, str, str] | None:
    """Return the first unanswered (qid, key, prompt) tuple, or None when done."""
    for qid, key, prompt in INTAKE_QUESTIONS:
        if not intake.get(key):
            return (qid, key, prompt)
    return None


# 意图 → 内部 intent_id 映射。intent 决定 ARCHITECT 阶段的拆分倾向，但用户不感知。
_USER_INTENT_MAP = {
    # 数字 / 中文数字精确匹配
    "1": "data_analysis",
    "2": "automation",
    "3": "new_perspective",
    "4": "extend_existing",
    "5": "codify_knowledge",
    "6": "free_form",
    "一": "data_analysis", "二": "automation", "三": "new_perspective",
    "四": "extend_existing", "五": "codify_knowledge", "六": "free_form",
    # 关键词子串匹配（按优先级，越具体越靠前）
    "扩展": "extend_existing", "现有能力": "extend_existing",
    "数据分析": "data_analysis", "分析能力": "data_analysis",
    "自动化": "automation", "定时": "automation", "每周": "automation", "每天": "automation",
    "决策视角": "new_perspective", "判断": "new_perspective",
    "知识固化": "codify_knowledge", "沉淀": "codify_knowledge", "固化": "codify_knowledge",
    "自由描述": "free_form", "自由": "free_form",
}

_USER_INTENT_LABELS = {
    "data_analysis": "数据分析能力",
    "automation": "自动化任务",
    "new_perspective": "新决策视角",
    "extend_existing": "现有能力扩展",
    "codify_knowledge": "知识固化",
    "free_form": "自由描述（系统自动判断结构）",
}


def _parse_user_intent(message: str) -> str | None:
    msg = message.strip().lower()
    if not msg:
        return None
    if msg in _USER_INTENT_MAP:
        return _USER_INTENT_MAP[msg]
    for token, value in _USER_INTENT_MAP.items():
        if token in msg:
            return value
    return None


# Scenario keyword → trigger kind. Order matters: scheduled checked first because
# explicit time/frequency is the strongest actionable signal for ARCHITECT (cron gen).
_SCENARIO_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("scheduled", (
        "定时", "cron", "每天", "每日", "每周", "每月", "每年",
        "周一", "周二", "周三", "周四", "周五", "周六", "周日",
        "早上", "上午", "中午", "下午", "晚上", "夜里", "凌晨",
        "小时", "分钟",
    )),
    ("event_driven", (
        "事件", "触发", "完成后", "之后", "收到", "pipeline", "回调",
    )),
    ("user_triggered", (
        "用户", "主动", "命令", "关键词", "@", "聊天", "对话", "喊我", "点开",
    )),
]


def _normalize_scenario(text: str) -> str | None:
    """Map free-text scenario answer → scheduled / event_driven / user_triggered."""
    if not text:
        return None
    msg = text.lower()
    for kind, keywords in _SCENARIO_KEYWORDS:
        if any(kw in msg for kw in keywords):
            return kind
    return None


# Step-sequence markers for Q5 light validation. Detection is best-effort:
# false negatives just trigger one polite re-ask, never block the user.
_STEP_MARKERS: tuple[str, ...] = (
    "先", "再", "然后", "最后", "接着", "之后", "首先", "其次", "接下来",
    "步骤", "第一步", "第二步", "第三步",
    "→", "->", "=>",
    "step", "then", "finally", "first", "second", "next",
)


def _looks_like_steps(text: str) -> bool:
    if not text:
        return False
    msg = text.lower()
    if any(marker in msg for marker in _STEP_MARKERS):
        return True
    # Numbered list (1. / 2) / 1、 / 1)) at start of any line.
    for line in msg.splitlines():
        s = line.strip()
        if len(s) >= 2 and s[0].isdigit() and s[1] in ".、)）":
            return True
    return False


def handle_intake(state: dict[str, Any], user_message: str, parent_agent: Any) -> str:
    """Sequential answer collection. No LLM needed."""
    intake = state.setdefault("intake", {})
    current_qid = intake.get("_current_question")

    # Stage 0: pick user intent. Default to INTENT_CHOICE if unset.
    # (Architect stage will derive whether this becomes 1 expert + N skills,
    # 1 skill alone, an extension, etc. The user never sees those terms here.)
    if current_qid is None:
        current_qid = "INTENT_CHOICE"

    if current_qid == "INTENT_CHOICE":
        user_intent = _parse_user_intent(user_message)
        if user_intent is None:
            return (
                "没看懂你想做什么，请回复数字 1-6，或者用关键词描述：\n"
                "  • 数据分析 / 自动化 / 决策视角 / 扩展现有 / 知识固化 / 自由描述"
            )
        intake["_user_intent"] = user_intent
        intake["_current_question"] = "Q1"
        intent_label = _USER_INTENT_LABELS.get(user_intent, user_intent)
        return (
            f"{PROGRESS_LABELS['INTAKE']}\n\n"
            f"已确认意图：**{intent_label}**\n\n"
            f"**第 1 个问题（共 5 个必填）**：\n"
            f"{INTAKE_QUESTIONS[0][2]}"
        )

    if current_qid == "OPTIONAL":
        return _handle_optional_answer(state, user_message)

    # Find which key this answer belongs to.
    key_for_qid = next((k for q, k, _ in INTAKE_QUESTIONS if q == current_qid), None)
    if key_for_qid:
        # Q5 light validation: ask once if step-sequence markers are missing.
        # On re-ask, accept whatever the user sends next.
        if current_qid == "Q5" and not intake.get("_q5_reasked"):
            if not _looks_like_steps(user_message):
                intake["_q5_reasked"] = True
                return (
                    f"{PROGRESS_LABELS['INTAKE']}\n\n"
                    f"这个回答看起来不太像执行流程。能否用 \"先 X，再 Y，最后 Z\" "
                    f"的方式描述一下步骤顺序？\n"
                    f"（如果你坚持就是这个回答，再发一遍即可。）"
                )
        intake[key_for_qid] = user_message.strip()
        if current_qid == "Q2":
            intake["_scenario_kind"] = _normalize_scenario(user_message)

    # Find the next unanswered question.
    nxt = _next_intake_question(intake)
    if nxt is not None:
        nqid, _nkey, nprompt = nxt
        intake["_current_question"] = nqid
        idx = next(i for i, (q, _, _) in enumerate(INTAKE_QUESTIONS) if q == nqid) + 1
        return (
            f"{PROGRESS_LABELS['INTAKE']}\n\n"
            f"**第 {idx} 个问题（共 5 个必填）**：\n{nprompt}"
        )

    # All required answered → ask optional form.
    intake["_current_question"] = "OPTIONAL"
    return f"{PROGRESS_LABELS['INTAKE']}\n\n{OPTIONAL_PROMPT}"


def _handle_optional_answer(state: dict[str, Any], user_message: str) -> str:
    intake = state["intake"]
    msg = user_message.strip().lower()

    if msg in {"默认", "跳过", "skip", "no", "无"}:
        intake.setdefault("max_runtime", 300)
        intake.setdefault("priority", "normal")
        intake.setdefault("audience", "owner")
        intake.setdefault("user_gate", False)
        intake.setdefault("schedule", None)
    else:
        # Lightweight parsing — naive substring/value extraction. For MVP we
        # keep the user-provided string verbatim and let ARCHITECT decide.
        intake.setdefault("optional_raw", user_message.strip())

    intake["_current_question"] = None  # done with INTAKE
    state["stage"] = "ARCHITECT"
    _push_history(state, "INTAKE")
    return (
        f"{PROGRESS_LABELS['ARCHITECT']}\n\n"
        "INTAKE 完成。我现在扫描现有 expert 看是否能复用，稍后会给你一个拆分方案。\n"
        "👉 请回复 \"继续\" 触发架构分析。"
    )


# ---------- ARCHITECT 3a: reuse scan ----------

@dataclass
class ExpertCandidate:
    name: str
    display_name: str
    description: str
    skills: list[str]
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


def _experts_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "experts"


def _load_existing_experts() -> list[ExpertCandidate]:
    """Read all expert.json files under agent_system/experts/, skip _drafts and self."""
    out: list[ExpertCandidate] = []
    base = _experts_dir()
    if not base.exists():
        return out
    for child in base.iterdir():
        if not child.is_dir():
            continue
        if child.name in {"_drafts", "builder_expert"}:
            continue
        manifest = child / "expert.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append(
            ExpertCandidate(
                name=data.get("name", child.name),
                display_name=data.get("display_name", child.name),
                description=data.get("description", ""),
                skills=list(data.get("skills", [])),
            )
        )
    return out


def _tokenize(text: str) -> set[str]:
    """Mixed CN/EN tokenizer: word tokens (for spaced EN) + char bigrams (for CN).

    CN text has no word boundaries; bigram coverage works as a cheap proxy
    without bringing in jieba. Trade-off: may produce noise bigrams across
    semantic boundaries — acceptable at this granularity since the score is
    used only to rank top-K candidates (LLM rerank lives in the next slice).
    """
    if not text:
        return set()
    seps = " ,.;:/()[]{}、，。；：（）【】「」!?！？\n\t"
    cleaned = text.lower()
    for s in seps:
        cleaned = cleaned.replace(s, " ")
    tokens: set[str] = set()
    for w in cleaned.split():
        if len(w) >= 2:
            tokens.add(w)
    # Char bigrams for CJK-glued runs.
    no_space = "".join(cleaned.split())
    for i in range(len(no_space) - 1):
        bigram = no_space[i : i + 2]
        if all(c.isalnum() or "一" <= c <= "鿿" for c in bigram):
            tokens.add(bigram)
    return tokens


def _score_candidate(cand: ExpertCandidate, intake: dict[str, Any]) -> float:
    """Token-overlap score (0..1) between intake fields and expert description+skills."""
    intake_tokens: set[str] = set()
    for key in ("business_goal", "scenario", "input_type", "output_type", "pipeline_description"):
        intake_tokens |= _tokenize(intake.get(key, ""))
    if not intake_tokens:
        return 0.0
    cand_tokens = _tokenize(cand.description) | {s.lower() for s in cand.skills}
    if not cand_tokens:
        return 0.0
    overlap = len(intake_tokens & cand_tokens)
    return overlap / max(len(intake_tokens), 1)


def scan_reusable_experts(intake: dict[str, Any], top_k: int = 3, threshold: float = 0.05) -> list[ExpertCandidate]:
    """Stage 3a — return top-k experts whose score ≥ threshold."""
    cands = _load_existing_experts()
    for c in cands:
        c.score = _score_candidate(c, intake)
    cands = [c for c in cands if c.score >= threshold]
    cands.sort(key=lambda x: x.score, reverse=True)
    return cands[:top_k]


def handle_architect(state: dict[str, Any], user_message: str, parent_agent: Any) -> str:
    """Stage 3 entry point.

    First call: run reuse scan, present candidates, ask user choice (3b).
    Subsequent calls: parse user choice and finalize architect_proposal (3c).
    """
    proposal = state.get("architect_proposal") or {}
    sub_stage = proposal.get("_sub_stage")  # None → 3a/3b; 'awaiting_choice' → 3c

    if sub_stage is None:
        # 3a: scan
        intake = state.get("intake", {})
        candidates = scan_reusable_experts(intake)
        if candidates:
            lines = [f"{PROGRESS_LABELS['ARCHITECT']}", "", "**复用扫描结果（top 3）**："]
            for i, c in enumerate(candidates, 1):
                lines.append(
                    f"  {i}. `{c.name}`（{c.display_name}） · score={c.score:.2f}\n"
                    f"     {c.description[:80]}"
                )
            lines.append("")
            lines.append("你倾向：")
            lines.append("  • [A] **复用** 上面某个 expert（回复 \"复用 1\" / \"复用 2\" 选择）")
            lines.append("  • [B] **新建** 独立 expert（回复 \"新建\"）")
            lines.append("  • [C] **复用 + 扩展**（回复 \"扩展 1\"，把新 skill 注册到 #1）")
            response = "\n".join(lines)
        else:
            lines = [
                f"{PROGRESS_LABELS['ARCHITECT']}",
                "",
                "**复用扫描结果**：未找到匹配度足够的现有 expert。",
                "默认走新建路径。请回复 \"新建\" 确认。",
            ]
            response = "\n".join(lines)

        # Persist scan result so 3c can reference it.
        proposal["_sub_stage"] = "awaiting_choice"
        proposal["candidates"] = [
            {"rank": i + 1, "name": c.name, "display_name": c.display_name, "score": c.score}
            for i, c in enumerate(candidates)
        ]
        state["architect_proposal"] = proposal
        return response

    # sub_stage == 'awaiting_choice' → parse 3c
    choice = user_message.strip().lower()
    candidates = proposal.get("candidates", [])

    intake = state.get("intake", {})
    if choice.startswith("复用") or choice.startswith("reuse"):
        rank = _extract_rank(choice)
        chosen = next((c for c in candidates if c["rank"] == rank), None)
        if not chosen:
            return "没看懂你选哪个，请回复 \"复用 1\" / \"复用 2\" / \"复用 3\"。"
        names = _derive_names(intake, "reuse", chosen["name"])
        proposal["experts"] = [{"action": "reuse", "name": names["expert_name"], "rationale": "用户选择复用现有 expert"}]
    elif choice.startswith("扩展") or choice.startswith("extend"):
        rank = _extract_rank(choice)
        chosen = next((c for c in candidates if c["rank"] == rank), None)
        if not chosen:
            return "没看懂你选哪个，请回复 \"扩展 1\" / \"扩展 2\" 等。"
        names = _derive_names(intake, "extend", chosen["name"])
        proposal["experts"] = [{"action": "extend", "name": names["expert_name"], "rationale": "用户选择扩展现有 expert"}]
    elif choice.startswith("新建") or "create" in choice:
        names = _derive_names(intake, "create", None)
        proposal["experts"] = [{"action": "create", "name": names["expert_name"], "rationale": "用户选择新建独立 expert"}]
    else:
        return "请回复以下之一：\n  • \"复用 N\"\n  • \"扩展 N\"\n  • \"新建\""

    # Architect 3c — deterministic skill/route names (LLM-driven naming pending).
    schedule = "weekly" if intake.get("_scenario_kind") == "scheduled" else None
    proposal["skills"] = [{"name": names["skill_name"], "rationale": "占位 — LLM 命名在 #8 后半段接入"}]
    proposal["routes"] = [{"pipeline_id": names["pipeline_id"], "steps": [], "schedule": schedule}]
    proposal["_sub_stage"] = "ready"
    proposal["user_confirmed"] = True
    state["stage"] = "DRAFT"
    state["architect_proposal"] = proposal
    _push_history(state, "ARCHITECT")
    # Chain immediately into DRAFT so the user sees the file generation result
    # in the same response — no extra "继续" round-trip required.
    architect_summary = (
        f"{PROGRESS_LABELS['ARCHITECT']}\n\n"
        f"已确认方案：\n"
        f"  • expert：{proposal['experts'][0]['action']} → `{proposal['experts'][0]['name']}`\n"
        f"  • skill：`{names['skill_name']}`\n"
        f"  • pipeline：`{names['pipeline_id']}`（schedule={schedule}）\n"
    )
    return architect_summary + "\n" + handle_draft(state, user_message, parent_agent)


def _extract_rank(text: str) -> int:
    """Pull first 1/2/3 (or one/two/three) out of free text."""
    for digit in "123":
        if digit in text:
            return int(digit)
    cn_map = {"一": 1, "二": 2, "三": 3}
    for k, v in cn_map.items():
        if k in text:
            return v
    return 0


def _derive_names(intake: dict[str, Any], action: str, reused_name: str | None) -> dict[str, str]:
    """Generate deterministic skill / expert / pipeline names from intake.

    Includes microsecond suffix so VALIDATE-triggered regeneration in the same
    second still produces a fresh, collision-free name. LLM-driven semantic
    naming is the follow-up half of Task #8.
    """
    import datetime
    intent = intake.get("_user_intent") or "general"
    now = datetime.datetime.utcnow()
    ts = now.strftime("%Y%m%d_%H%M%S_") + f"{now.microsecond:06d}"
    skill_name = f"{intent}_{ts}"
    pipeline_id = f"{skill_name}_pipeline"
    if action == "create":
        expert_name = f"{intent}_expert_{ts}"
    else:
        expert_name = reused_name or "unknown"
    return {
        "skill_name": skill_name,
        "expert_name": expert_name,
        "pipeline_id": pipeline_id,
    }


# ---------- stubs for later stages ----------

def handle_draft(state: dict[str, Any], user_message: str, parent_agent: Any) -> str:
    """Stage 4 — generate draft files from intake + architect_proposal.

    First call: writes files to _drafts/, records paths into state['drafts'],
    advances stage to VALIDATE.
    Subsequent calls (re-entry): just report what's already on disk.
    """
    from agent_system.experts.builder_expert.draft_writer import write_drafts

    drafts = state.get("drafts") or {}
    if drafts.get("skill_paths"):
        return (
            f"{PROGRESS_LABELS['DRAFT']}\n\n"
            "草稿文件已生成（详见 state.drafts）。下一步：VALIDATE 阶段（待接入 Task #9）。"
        )

    try:
        result = write_drafts(state)
    except Exception as exc:
        logger.exception("draft writer failed: %s", exc)
        return (
            f"{PROGRESS_LABELS['DRAFT']}\n\n"
            f"草稿生成失败：{exc.__class__.__name__}: {exc}\n"
            "状态已保留，可说 \"退出深度养马模式\" 重置后重试。"
        )

    state["drafts"] = result
    state["stage"] = "VALIDATE"
    _push_history(state, "DRAFT")

    skill_files = "\n".join(f"  • {p}" for p in result["skill_paths"])
    expert_files = (
        "\n".join(f"  • {p}" for p in result["expert_paths"])
        if result["expert_paths"]
        else "  （复用现有 expert，未生成新 expert 文件）"
    )
    return (
        f"{PROGRESS_LABELS['DRAFT']}\n\n"
        f"草稿生成完成。\n\n"
        f"**Skill** (`{result['skill_name']}`)：\n{skill_files}\n\n"
        f"**Expert** (`{result['expert_name']}`, action={result['expert_action']})：\n{expert_files}\n\n"
        f"**Routes draft**：\n  • {result['routes_draft_path']}\n\n"
        f"下一步会进入 VALIDATE（自动校验），目前还是 stub。"
    )


def handle_validate(state: dict[str, Any], user_message: str, parent_agent: Any) -> str:
    """Stage 5 — auto-validate the draft. EXPERT.md §5 retry contract:

    First failure → if name_collision involved, regenerate (timestamp differs)
    once and re-check. Other failures or second failure → form fallback:
    list errors and let user say "重试" (after manually editing files) or
    "退出" to leave the mode.
    """
    from agent_system.experts.builder_expert.draft_writer import write_drafts
    from agent_system.experts.builder_expert.validators import run_all

    validation = state.setdefault("validation", {})
    drafts = state.get("drafts") or {}
    if not drafts.get("skill_paths"):
        return (
            f"{PROGRESS_LABELS['VALIDATE']}\n\n"
            "缺少 draft 产物（state.drafts 为空），请先完成 DRAFT 阶段。"
        )

    # Form-fallback re-entry: user said "重试" or "退出" after a previous failure.
    if validation.get("awaiting_user"):
        msg = user_message.strip().lower()
        if msg.startswith("退出"):
            # Let dispatcher's exit phrase handler take over on next message.
            validation["awaiting_user"] = False
            return (
                f"{PROGRESS_LABELS['VALIDATE']}\n\n"
                "好，可以说 \"退出深度养马模式\" 真正退出，未完成 draft 会保留在 _drafts/。"
            )
        if msg.startswith("重试") or msg.startswith("retry"):
            validation["awaiting_user"] = False
            # fall through to re-run validators
        else:
            return (
                f"{PROGRESS_LABELS['VALIDATE']}\n\n"
                "请回复 \"重试\" 重新校验，或 \"退出\" 离开。"
            )

    report = run_all(drafts)

    if report["ok"]:
        validation["last_report"] = report
        state["stage"] = "DRY_RUN"
        _push_history(state, "VALIDATE")
        return (
            f"{PROGRESS_LABELS['VALIDATE']}\n\n"
            f"3 项校验全部通过：JSON schema ✓、重名 ✓、依赖完整性 ✓\n\n"
            + handle_dry_run(state, user_message, parent_agent)
        )

    # Failure path
    attempts = validation.get("attempts", 0)
    failed = report["failed_check_names"]

    # Auto-retry only if name_collision is the (only) issue and we haven't retried yet.
    if attempts == 0 and "name_collision" in failed:
        validation["attempts"] = 1
        # Refresh names so the regen uses fresh timestamps — write_drafts itself
        # reads from proposal, it doesn't re-derive.
        proposal = state.get("architect_proposal") or {}
        action = (proposal.get("experts") or [{}])[0].get("action", "create")
        reused = (proposal.get("experts") or [{}])[0].get("name") if action != "create" else None
        names = _derive_names(state.get("intake", {}), action, reused)
        proposal["experts"][0]["name"] = names["expert_name"]
        proposal["skills"][0]["name"] = names["skill_name"]
        proposal["routes"][0]["pipeline_id"] = names["pipeline_id"]
        state["architect_proposal"] = proposal
        try:
            new_drafts = write_drafts(state)
        except Exception as exc:
            logger.exception("regenerate during VALIDATE retry failed: %s", exc)
            validation["last_report"] = report
            validation["awaiting_user"] = True
            return _validate_form_fallback(report)
        state["drafts"] = new_drafts
        # Re-run validators with the new artifacts.
        report = run_all(new_drafts)
        if report["ok"]:
            validation["last_report"] = report
            state["stage"] = "DRY_RUN"
            _push_history(state, "VALIDATE")
            return (
                f"{PROGRESS_LABELS['VALIDATE']}\n\n"
                f"首次校验有重名，已自动重新生成（新时间戳 → `{new_drafts['skill_name']}`）后通过。\n\n"
                + handle_dry_run(state, user_message, parent_agent)
            )

    # Other failures, or retry didn't help → form fallback.
    validation["last_report"] = report
    validation["awaiting_user"] = True
    return _validate_form_fallback(report)


def _validate_form_fallback(report: dict[str, Any]) -> str:
    bullet_errors = "\n".join(f"  • {e}" for e in report["all_errors"])
    return (
        f"{PROGRESS_LABELS['VALIDATE']}\n\n"
        f"校验未通过（{len(report['all_errors'])} 项）：\n{bullet_errors}\n\n"
        f"你可以直接编辑 `_drafts/` 下的文件修复问题，然后回复 \"重试\" 重新校验；"
        f"或回复 \"退出\" 离开本次养马。"
    )


def handle_dry_run(state: dict[str, Any], user_message: str, parent_agent: Any) -> str:
    """Stage 6 — structural试加载 + canned mock + output-shape sanity check.

    Real pipeline execution is gated on Task #8 LLM upgrade (until then,
    pipeline.steps == [] so there's nothing to actually run end-to-end).
    """
    from agent_system.experts.builder_expert.mock_generator import make_mock, output_kind

    intake = state.get("intake", {}) or {}
    drafts = state.get("drafts", {}) or {}
    dry = state.setdefault("dry_run", {})

    # 1. Structural試加载: routes.draft entries must shape-match init_scheduler's expectations.
    issues: list[str] = []
    routes_path = drafts.get("routes_draft_path")
    if routes_path:
        try:
            data = json.loads(Path(routes_path).read_text(encoding="utf-8"))
            for entry in data.get("pipelines", []):
                cstr = entry.get("constraints") or {}
                if not isinstance(cstr.get("max_runtime"), int):
                    issues.append(
                        f"路由 `{entry.get('pipeline_id')}` constraints.max_runtime "
                        f"必须为 int（init_scheduler 要求）"
                    )
                supv = entry.get("supervision") or {}
                if not isinstance(supv.get("scheduler_monitor"), bool):
                    issues.append(
                        f"路由 `{entry.get('pipeline_id')}` supervision.scheduler_monitor "
                        f"必须为 bool"
                    )
        except Exception as exc:
            issues.append(f"routes.draft.json 试加载失败: {exc}")
    else:
        issues.append("缺少 routes.draft.json — DRY_RUN 跳过试加载")

    # 2. Mock data generation
    mock = make_mock(intake)
    out_kind = output_kind(intake.get("output_type", ""))

    dry["load_test"] = {"ok": not issues, "issues": issues}
    dry["mock"] = mock
    dry["output_kind"] = out_kind

    # 3. Without LLM-generated pipeline content we cannot actually execute. Be honest.
    pipeline_steps_empty = True  # current ARCHITECT 3c always emits steps=[]

    if issues:
        # Send back to VALIDATE — but EXPERT.md says §6 failure → back to Stage 3.
        # For MVP we surface to user and let them choose (避免悄悄回退状态机).
        bullet = "\n".join(f"  • {i}" for i in issues)
        return (
            f"{PROGRESS_LABELS['DRY_RUN']}\n\n"
            f"试加载发现 {len(issues)} 个结构问题：\n{bullet}\n\n"
            f"建议回 ARCHITECT 重新生成。可说 \"回到架构\" 或 \"退出\"。"
        )

    state["stage"] = "TRIAL_RUN"
    _push_history(state, "DRY_RUN")

    note = (
        "  ⚠️ pipeline.steps 为空（LLM 升级后才会有真实步骤），本次未真跑端到端。"
        if pipeline_steps_empty
        else "  ✓ pipeline 已含步骤，本次跑通了 mock → 输出。"
    )
    dry_summary = (
        f"{PROGRESS_LABELS['DRY_RUN']}\n\n"
        f"  ✓ 结构试加载通过\n"
        f"  ✓ Mock 数据已生成（kind=`{mock['_mock_kind']}`）\n"
        f"  ✓ 期望输出类型：`{out_kind}`\n"
        f"{note}\n"
    )
    return dry_summary + "\n" + handle_trial_run(state, user_message, parent_agent)


_SOURCE_MENU = (
    "**请选择真实数据来源**：\n"
    "  1️⃣ 飞书云文档（粘贴 doc URL）\n"
    "  2️⃣ 直接贴文本（markdown / 表格 / 任意片段）\n"
    "  3️⃣ Hermes 已接入数据源（如 \"群:产线运营 最近 7 天\"）\n"
    "  4️⃣ 本地文件路径\n\n"
    "回复数字，或直接发数据 / URL / 路径，我会自动识别。"
)


def handle_trial_run(state: dict[str, Any], user_message: str, parent_agent: Any) -> str:
    """Stage 7 sub-state machine:
       ASK_SOURCE → (AWAIT_DATA if menu picked) → JUDGE → COMMIT or back to ARCHITECT.

    Real pipeline execution is gated on Task #8 LLM upgrade. This stage provides
    the gating UX (data ingest + 是否符合预期 confirmation) so COMMIT is only
    reached after explicit user approval.
    """
    from agent_system.experts.builder_expert.trial_runner import (
        ingest, detect_source_kind, render_trial_summary,
    )
    from agent_system.experts.builder_expert.mock_generator import output_kind

    trial = state.setdefault("trial_run", {})
    sub = trial.get("_sub_stage")

    # Entry: first time landing here, prompt for source.
    if sub is None:
        trial["_sub_stage"] = "ASK_SOURCE"
        return f"{PROGRESS_LABELS['TRIAL_RUN']}\n\n{_SOURCE_MENU}"

    intake = state.get("intake", {}) or {}

    if sub == "ASK_SOURCE":
        # User's reply is either a menu number ("1".."4") or actual data.
        kind = detect_source_kind(user_message)
        if kind in {"1", "2", "3", "4"}:
            # detect_source_kind never returns digits; this branch is defensive only
            kind = {"1": "feishu_url", "2": "paste", "3": "channel_ref", "4": "file_path"}[kind]

        # If pure menu selection (numeric only), wait for the actual data next.
        if user_message.strip() in {"1", "2", "3", "4", "一", "二", "三", "四"}:
            trial["_picked_kind"] = kind
            trial["_sub_stage"] = "AWAIT_DATA"
            hint = {
                "feishu_url": "请贴飞书 doc 的完整 URL",
                "paste": "请直接贴文本内容",
                "channel_ref": "请用 \"群:名称 时间窗口\" 或 channel_id 描述",
                "file_path": "请提供文件的绝对路径",
            }[kind]
            return f"{PROGRESS_LABELS['TRIAL_RUN']}\n\n{hint}。"

        # Otherwise the user already gave data inline — ingest now.
        result = ingest(user_message, kind)
        return _trial_after_ingest(state, intake, result)

    if sub == "AWAIT_DATA":
        kind = trial.get("_picked_kind")
        result = ingest(user_message, kind)
        return _trial_after_ingest(state, intake, result)

    if sub == "JUDGE":
        msg = user_message.strip().lower()
        if msg in {"是", "符合", "ok", "yes", "确认", "通过", "y"}:
            state["stage"] = "COMMIT"
            _push_history(state, "TRIAL_RUN")
            return (
                f"{PROGRESS_LABELS['TRIAL_RUN']}\n\n"
                "✓ 已确认通过。进入 COMMIT 阶段。\n\n"
                + handle_commit(state, user_message, parent_agent)
            )
        if msg in {"否", "不行", "不通过", "n", "no", "回退", "重做"}:
            # Per EXPERT.md §7: 否 → 回 Stage 3 (ARCHITECT) 带失败原因
            state["stage"] = "ARCHITECT"
            # Reset architect sub_stage so it'll re-scan / re-propose
            ap = state.get("architect_proposal") or {}
            ap["_sub_stage"] = None
            ap["_user_rejection_note"] = trial.get("_judge_context", "用户在 TRIAL_RUN 阶段否决了方案")
            state["architect_proposal"] = ap
            # Reset trial sub-state so a fresh round restarts cleanly
            trial.clear()
            return (
                f"{PROGRESS_LABELS['TRIAL_RUN']}\n\n"
                "好，已回到 ARCHITECT 阶段。请回复 \"继续\" 重新触发架构分析"
                "（你可以在分析时说明哪里不对，比如 \"上次的拆分太散\"）。"
            )
        return (
            f"{PROGRESS_LABELS['TRIAL_RUN']}\n\n"
            "请回复 \"是\" 确认通过进 COMMIT，或 \"否\" 回退到 ARCHITECT 调整方案。"
        )

    return (
        f"{PROGRESS_LABELS['TRIAL_RUN']}\n\n"
        f"未知子状态 `{sub}`，请说 \"退出深度养马模式\" 重置。"
    )


def _trial_after_ingest(
    state: dict[str, Any], intake: dict[str, Any], result: dict[str, Any]
) -> str:
    from agent_system.experts.builder_expert.trial_runner import render_trial_summary
    from agent_system.experts.builder_expert.mock_generator import output_kind

    trial = state["trial_run"]
    if not result.get("ok"):
        # Stay in current sub-state, let user retry with corrected input.
        return (
            f"{PROGRESS_LABELS['TRIAL_RUN']}\n\n"
            f"数据源未就绪：{result.get('note', '未知错误')}\n"
            f"请修正后再发一次，或回数字重新选数据源类型。"
        )

    out_kind = output_kind(intake.get("output_type", ""))
    summary = render_trial_summary(intake, result, out_kind)

    trial["_sub_stage"] = "JUDGE"
    trial["data_source"] = result["kind"]
    trial["data_ref"] = result.get("data_ref")
    trial["output_summary"] = summary
    trial["_judge_context"] = (
        f"data_kind={result['kind']} deferred={result.get('deferred')} "
        f"output_kind={out_kind}"
    )

    return (
        f"{PROGRESS_LABELS['TRIAL_RUN']}\n\n"
        f"{summary}\n\n"
        f"**这个流程符合你的预期吗？**\n"
        f"  • 是 → 进入 COMMIT（落正式位置 + git add）\n"
        f"  • 否 → 回 ARCHITECT 调整方案"
    )


def handle_commit(state: dict[str, Any], user_message: str, parent_agent: Any) -> str:
    """Auto-execute commit: mv drafts → production, patch routes.json, git add."""
    import subprocess
    from agent_system.experts.builder_expert.draft_writer import _agent_system_root

    drafts = state.get("drafts") or {}
    skill_name = drafts.get("skill_name")
    expert_name = drafts.get("expert_name")
    expert_action = drafts.get("expert_action", "create")
    routes_draft_str = drafts.get("routes_draft_path")

    if not skill_name or not routes_draft_str:
        return f"{PROGRESS_LABELS['COMMIT']}\n\n⚠️ 草稿信息缺失，请说【退出深度养马模式】重置。"

    root = _agent_system_root()
    errors: list[str] = []
    committed: list[str] = []

    # Move skill draft → production
    skill_src = root / "skills" / "_drafts" / skill_name
    skill_dst = root / "skills" / skill_name
    if skill_src.exists():
        skill_src.rename(skill_dst)
        committed.append(f"skills/{skill_name}/")
        skill_json = skill_dst / "skill.json"
        if skill_json.exists():
            data = json.loads(skill_json.read_text(encoding="utf-8"))
            if data.get("type") == "draft":
                data["type"] = "analysis"
            skill_json.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    else:
        errors.append(f"skill draft 不存在：{skill_src}")

    # Handle expert by action
    if expert_action == "create" and expert_name:
        expert_src = root / "experts" / "_drafts" / expert_name
        expert_dst = root / "experts" / expert_name
        if expert_src.exists():
            expert_src.rename(expert_dst)
            committed.append(f"experts/{expert_name}/")
        else:
            errors.append(f"expert draft 不存在：{expert_src}")
    elif expert_action == "extend" and expert_name:
        expert_json = root / "experts" / expert_name / "expert.json"
        if expert_json.exists():
            data = json.loads(expert_json.read_text(encoding="utf-8"))
            skills_list = data.setdefault("skills", [])
            if skill_name not in skills_list:
                skills_list.append(skill_name)
            expert_json.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            committed.append(f"experts/{expert_name}/expert.json")
        else:
            errors.append(f"extend 目标 expert 不存在：{expert_json}")

    # Patch routes.json
    routes_draft = Path(routes_draft_str)
    routes_prod = root / "scheduler" / "main_scheduler" / "routes.json"
    if routes_draft.exists() and routes_prod.exists():
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        routes_prod.with_name(f"routes.json.bak.{ts}").write_bytes(routes_prod.read_bytes())
        draft_data = json.loads(routes_draft.read_text(encoding="utf-8"))
        prod_data = json.loads(routes_prod.read_text(encoding="utf-8"))
        existing_ids = {p["pipeline_id"] for p in prod_data.get("pipelines", [])}
        added = 0
        for entry in draft_data.get("pipelines", []):
            clean = {k: v for k, v in entry.items() if k != "_draft_meta"}
            if clean["pipeline_id"] not in existing_ids:
                prod_data.setdefault("pipelines", []).append(clean)
                added += 1
        routes_prod.write_text(
            json.dumps(prod_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        routes_draft.unlink()
        committed.append(f"scheduler/main_scheduler/routes.json (+{added} pipeline)")
    else:
        if not routes_draft.exists():
            errors.append(f"routes.draft.json 不存在：{routes_draft}")
        if not routes_prod.exists():
            errors.append("routes.json 不存在")

    # git add
    git_files = [f"agent_system/skills/{skill_name}"]
    if expert_action in {"create", "extend"} and expert_name:
        git_files.append(f"agent_system/experts/{expert_name}")
    git_files.append("agent_system/scheduler/main_scheduler/routes.json")
    git_ok = False
    try:
        subprocess.run(
            ["git", "add"] + git_files,
            cwd=str(root.parent),
            check=True,
            capture_output=True,
        )
        git_ok = True
    except Exception as exc:
        errors.append(f"git add 失败：{exc}")

    if errors:
        return (
            f"{PROGRESS_LABELS['COMMIT']}\n\n"
            "⚠️ 落盘中断，请检查后说【重试】：\n"
            + "\n".join(f"  • {e}" for e in errors)
        )

    _push_history(state, "COMMIT")
    state["stage"] = "NEXT_OR_EXIT"
    file_lines = "\n".join(f"  • `{f}`" for f in committed)
    git_note = "✅ 已 staged，请自行 review 后执行 `git commit`" if git_ok else "⚠️ git add 失败，请手动 stage"
    return (
        f"{PROGRESS_LABELS['COMMIT']}\n\n"
        f"✅ 落盘完成！\n\n"
        f"**已落盘文件：**\n{file_lines}\n\n"
        f"**Git**：{git_note}\n\n"
        + handle_next_or_exit(state, "", parent_agent)
    )


_NEXT_OR_EXIT_MENU = (
    "**还要继续创建其他能力吗？**\n"
    "  • 继续 / 是 → 重新开始（保持在养马模式）\n"
    "  • 退出 / 否 → 说【退出深度养马模式】完全退出"
)

_INTENT_MENU_REPROMPT = (
    "**你想做什么？**\n\n"
    "1️⃣ **数据分析能力** — 分析 VOC / 工单 / 评论 / 竞品等数据\n"
    "2️⃣ **自动化任务** — 定时或事件触发（每天 / 每周 / 异常告警）\n"
    "3️⃣ **新决策视角** — 让 Hermes 学会新的判断角度\n"
    "4️⃣ **现有能力扩展** — 在已有能力上加新功能\n"
    "5️⃣ **知识固化** — 把反复做的事沉淀成可调用能力\n"
    "6️⃣ **自由描述** — 直接说需求，我来判断\n\n"
    "回复数字（1-6）或直接描述。"
)


def handle_next_or_exit(state: dict[str, Any], user_message: str, parent_agent: Any) -> str:
    """Stage 9: offer to create another skill or end the session."""
    if not user_message.strip():
        return f"{PROGRESS_LABELS['NEXT_OR_EXIT']}\n\n{_NEXT_OR_EXIT_MENU}"

    msg = user_message.strip().lower()
    if msg in {"继续", "是", "yes", "y", "再来一个", "再来", "继续创建"}:
        state.update({
            "stage": "INTAKE",
            "intake": {"_current_question": "INTENT_CHOICE"},
            "architect_proposal": None,
            "drafts": {},
            "validation": {},
            "dry_run": {},
            "trial_run": {},
        })
        return (
            f"{PROGRESS_LABELS['NEXT_OR_EXIT']}\n\n"
            f"好的，开始新一轮！\n\n{_INTENT_MENU_REPROMPT}"
        )

    if msg in {"退出", "否", "不", "不了", "no", "n", "完成", "结束"}:
        count = len(state.get("history", []))
        return (
            f"{PROGRESS_LABELS['NEXT_OR_EXIT']}\n\n"
            f"本次共完成 {count} 个阶段。\n"
            "请说【退出深度养马模式】完全退出（状态文件将被清理）。"
        )

    return f"{PROGRESS_LABELS['NEXT_OR_EXIT']}\n\n{_NEXT_OR_EXIT_MENU}"


# ---------- main entry ----------

_HANDLERS = {
    "INTAKE": handle_intake,
    "ARCHITECT": handle_architect,
    "DRAFT": handle_draft,
    "VALIDATE": handle_validate,
    "DRY_RUN": handle_dry_run,
    "TRIAL_RUN": handle_trial_run,
    "COMMIT": handle_commit,
    "NEXT_OR_EXIT": handle_next_or_exit,
}


def handle(user_message: str, state_path: Path, parent_agent: Any) -> str:
    """Dispatch a single in-mode user message. Returns the response text."""
    state = load_state(state_path)
    stage = state.get("stage", "INTAKE")
    handler = _HANDLERS.get(stage)
    if handler is None:
        return f"未知 stage: {stage}。请说 \"退出深度养马模式\" 重置。"
    response = handler(state, user_message, parent_agent)
    save_state(state, state_path)
    return response
