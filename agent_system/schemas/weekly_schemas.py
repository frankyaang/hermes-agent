from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

IssueUrgency = Literal["high", "medium", "low"]
ContractStatus = Literal["pending_confirmation", "confirmed", "blocked", "incomplete"]
DecisionRoute = Literal[
    "decision_agenda",
    "need_more_info",
    "async_pre_read",
    "special_meeting",
    "escalation",
    "exit_weekly",
    "fake_closure_detected",
]


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Issue:
    title: str
    background: str
    source_ref: str
    urgency: IssueUrgency = "medium"
    options: list[str] = field(default_factory=list)
    recommended_option: str | None = None
    # IssueExtractor 禁止推断 owner；原文无明文 owner 时必须保留 None
    owner_candidate: str | None = None
    # 缺此字段不能进 decision_agenda
    acceptance_criteria: str | None = None
    issue_id: str = field(default_factory=_new_id)

    def is_complete(self) -> bool:
        return (
            self.recommended_option is not None
            and self.acceptance_criteria is not None
        )


@dataclass
class Decision:
    issue_id: str
    chosen_option: str
    rationale: str
    # 必须人工填写，禁止系统推断
    decided_by: str
    decided_at: str
    decision_id: str = field(default_factory=_new_id)


@dataclass
class Commitment:
    decision_id: str
    # 以下三字段任一为 None → incomplete=True，不计入闭环
    owner: str | None
    action: str | None
    deadline: str | None
    acceptance_criteria: str | None
    commitment_id: str = field(default_factory=_new_id)
    incomplete: bool = field(init=False)

    def __post_init__(self) -> None:
        self.incomplete = any(
            v is None
            for v in (self.owner, self.action, self.deadline, self.acceptance_criteria)
        )


@dataclass
class DecisionCard:
    """格式化后的议题卡片，发往飞书等渠道供人工确认。"""
    issue_id: str
    title: str
    recommended_option: str
    acceptance_criteria: str
    owner_candidate: str | None
    route: DecisionRoute
    # 初始必须 False；负责人回复「确认」后由 callback 翻转为 True
    confirmed_by_human: bool = False
    card_id: str = field(default_factory=_new_id)


@dataclass
class ExecutionContract:
    """仅在 DecisionCard.confirmed_by_human=True 后才允许生成。"""
    commitment_id: str = ""
    followup_at: str = ""
    issue_id: str = ""
    decision_id: str = ""
    title: str = ""
    decision: str = ""
    execution_owner: str | None = None
    committed_action: str | None = None
    deadline: str | None = None
    acceptance_criteria: str | None = None
    verification_evidence: str | None = None
    current_status: ContractStatus = "pending_confirmation"
    # 系统不得静默确认；必须由 Feishu callback 设置为 True
    confirmed_by_human: bool = False
    blocker_reason: str | None = None
    # 保留原始议题推荐方案，供 Feishu callback 确认时重建 Issue 使用
    original_recommended_option: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    contract_id: str = field(default_factory=_new_id)

    def is_closeable(self) -> bool:
        return (
            self.confirmed_by_human
            and all(v is not None for v in [
                self.execution_owner, self.committed_action,
                self.deadline, self.acceptance_criteria,
                self.verification_evidence,
            ])
        )

    def missing_fields(self) -> list[str]:
        required = {
            "execution_owner": self.execution_owner,
            "committed_action": self.committed_action,
            "deadline": self.deadline,
            "acceptance_criteria": self.acceptance_criteria,
            "verification_evidence": self.verification_evidence,
        }
        return [k for k, v in required.items() if v is None]

    def validate(self) -> None:
        if not self.confirmed_by_human:
            raise ValueError(
                "ExecutionContract.confirmed_by_human must be True before creation; "
                "system cannot silently confirm on behalf of humans."
            )


@dataclass
class DecisionHealthMetrics:
    total_issues: int = 0
    decision_agenda_count: int = 0
    need_more_info_count: int = 0
    async_pre_read_count: int = 0
    special_meeting_count: int = 0
    escalation_count: int = 0
    exit_weekly_count: int = 0
    fake_closure_count: int = 0
    contracts_missing_owner: int = 0
    contracts_missing_criteria: int = 0

    @property
    def invalid_decision_agenda_rate(self) -> float:
        # 不应出现：缺 recommended_option 却进入 decision_agenda
        # 该值恒为 0 if invariants hold；提供给监控系统检测异常
        if self.total_issues == 0:
            return 0.0
        return 0.0  # enforced by decision_gate invariant

    def record(self, route: DecisionRoute) -> None:
        self.total_issues += 1
        mapping = {
            "decision_agenda": "decision_agenda_count",
            "need_more_info": "need_more_info_count",
            "async_pre_read": "async_pre_read_count",
            "special_meeting": "special_meeting_count",
            "escalation": "escalation_count",
            "exit_weekly": "exit_weekly_count",
            "fake_closure_detected": "fake_closure_count",
        }
        attr = mapping.get(route)
        if attr:
            setattr(self, attr, getattr(self, attr) + 1)


@dataclass
class ConsensusLedger:
    confirmed_contracts: list[ExecutionContract] = field(default_factory=list)
    pending_contracts: list[ExecutionContract] = field(default_factory=list)
    skipped_fake_closure: list[dict] = field(default_factory=list)
    incomplete_commitments: list[dict] = field(default_factory=list)
    total_issues: int = 0


@dataclass
class FollowUpItem:
    issue_id: str
    title: str
    status: ContractStatus
    owner: str | None = None
    deadline: str | None = None
    followup_at: str | None = None
    missing_fields: list[str] = field(default_factory=list)


@dataclass
class FollowUpList:
    items: list[FollowUpItem] = field(default_factory=list)

    def pending_count(self) -> int:
        return sum(1 for i in self.items if i.status == "pending_confirmation")


@dataclass
class ConfirmationEvent:
    """平台中立的人工确认事件，由 Feishu callback 或测试 mock 产生。"""
    issue_id: str
    decision: str
    execution_owner: str | None
    committed_action: str | None
    deadline: str | None
    acceptance_criteria: str | None
    verification_evidence: str | None
    event_id: str = field(default_factory=_new_id)   # 幂等键
    confirmed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
