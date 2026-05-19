"""
Understanding Quality Loop — 数据模型。

设计约束：
  - 所有对象在 session 内存中存活；不自动持久化。
  - scope=global 的 BoundaryMemory 由外部（memory_manager）单独持久化，
    但必须有用户明确触发（"以后都..."类表达），数量上限 10 条。
  - memory_scope 不确定时强制 local，禁止系统自动升级为 global。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

CorrectionType = Literal[
    "fact_correction",           # 用户纠正事实
    "scope_correction",          # 缩小/扩大范围
    "frame_correction",          # 换框架
    "depth_correction",          # 要更深/更浅
    "separation_correction",     # "两个问题要分别思考"
    "generalization_correction", # "应该更通用"
    "regression_correction",     # agent 退回到旧错误
    "none",                      # 非纠偏
]

BoundaryScope = Literal["local", "session", "global"]
BoundaryType = Literal["negative", "positive"]

MAX_GLOBAL_BOUNDARIES = 10  # 超出时提示用户清理，防止 prompt 膨胀


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class UnderstandingState:
    """session 级别的任务理解状态，随 session 创建，随 session 结束。"""
    current_task_frame: str = ""
    user_true_intent: str = ""
    positive_rules: list[str] = field(default_factory=list)
    negative_boundaries: list[str] = field(default_factory=list)
    tacit_criteria: list[str] = field(default_factory=list)
    # local=本轮任务; session=本次对话; global=跨 session（需明确触发）
    memory_scope: BoundaryScope = "local"
    migration_limits: list[str] = field(default_factory=list)
    # 0-1；初始为 0.5（不确定）；用户纠偏后降低，确认后升高
    confidence: float = 0.5
    open_assumptions: list[str] = field(default_factory=list)
    # 是否触发过 separation_correction（后续不得混题）
    split_frame: bool = False
    # 是否触发过 generalization_correction（后续不得缩回单一案例）
    widen_scope: bool = False

    def update_from_correction(self, correction: "CorrectionClassification") -> None:
        """根据分类结果更新状态。"""
        ct = correction.correction_type
        if ct == "none":
            self.confidence = min(1.0, self.confidence + 0.1)
            return

        # 任何纠偏都降低置信度
        self.confidence = max(0.0, self.confidence - 0.2)

        if ct == "separation_correction":
            self.split_frame = True
        elif ct == "generalization_correction":
            self.widen_scope = True
        elif ct == "regression_correction":
            # 退回旧错误：置信度额外惩罚
            self.confidence = max(0.0, self.confidence - 0.1)

    def snapshot(self) -> dict:
        """返回当前状态快照，用于 rollback。"""
        import dataclasses
        return dataclasses.asdict(self)


@dataclass
class CorrectionClassification:
    turn_index: int
    correction_type: CorrectionType
    description: str
    # local: 只影响当前子问题; session: 影响整个 session; global: 跨 session
    scope: BoundaryScope = "local"
    confidence: float = 0.8
    classification_id: str = field(default_factory=_new_id)


@dataclass
class BoundaryMemory:
    """
    记录用户否定过的解释路径或确认过的规则。

    Scope 升级规则（系统不能自动升级）：
      local   → 默认值，本轮子任务内有效
      session → 用户说"这次对话都要这样"时才升级
      global  → 用户说"以后都..."才升级；写入 memory_manager built-in provider
    """
    boundary_type: BoundaryType
    content: str                   # 被否定的解释路径 / 确认的规则
    source_turn: int
    session_id: str
    scope: BoundaryScope = "local"
    boundary_id: str = field(default_factory=_new_id)

    def to_prompt_line(self) -> str:
        prefix = "【禁止】" if self.boundary_type == "negative" else "【规则】"
        return f"{prefix} {self.content}"


@dataclass
class PreAnswerEvaluation:
    """
    回答前的质量评估结果（纯本地，无 LLM 调用，延迟 < 5ms）。

    4 项检测：
      1. check_mixed_questions    — 当 split_frame=True 后，回答是否混题
      2. check_synonym_paraphrase — 是否同义重复已说过的内容
      3. check_boundary_violation — 是否违反 BoundaryMemory 中的 negative boundary
      4. check_scope_regression   — 是否退回旧的局限框架
    """
    check_mixed_questions: bool = False
    check_synonym_paraphrase: bool = False
    check_boundary_violation: bool = False
    check_scope_regression: bool = False

    # 整体通过标志；任一检测触发 → overall_pass=False
    overall_pass: bool = True
    # 仅在 overall_pass=False 时填写；优先尝试内部修正
    suggested_rewrite: str | None = None
    # 若 suggested_rewrite 无法覆盖，触发向用户提问
    needs_clarification: bool = False
    # 用于追踪
    eval_id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        self._recompute_pass()

    def _recompute_pass(self) -> None:
        self.overall_pass = not any([
            self.check_mixed_questions,
            self.check_synonym_paraphrase,
            self.check_boundary_violation,
            self.check_scope_regression,
        ])
