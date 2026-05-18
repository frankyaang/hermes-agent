"""
Data models for the Weekly flow subsystem.

DecisionCard    — gate output; status=pending_confirmation|incomplete|fake_closure
ExecutionContract — generated only after real owner confirmation
ConfirmationEvent — platform-neutral confirmation event schema
IssueSpec       — a single extracted issue from weekly material
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class IssueSpec:
    title: str
    owner: str
    status: str
    priority: str
    description: str
    is_fake_closure: bool = False

    def required_fields_present(self) -> list[str]:
        """Return list of missing required field names."""
        missing = []
        if not self.title.strip():
            missing.append("title")
        if not self.owner.strip():
            missing.append("owner")
        if not self.description.strip():
            missing.append("description")
        return missing


@dataclass(frozen=True)
class DecisionCard:
    issue_id: str
    status: Literal["pending_confirmation", "incomplete", "fake_closure"]
    issues: tuple            # tuple[IssueSpec, ...] — frozen
    missing_fields: tuple    # tuple[str, ...]
    follow_up: tuple         # tuple[str, ...]
    created_at: str          # ISO8601
    raw_material_hash: str


@dataclass(frozen=True)
class ConfirmationEvent:
    issue_id: str
    decision: Literal["confirmed", "rejected", "incomplete"]
    owner_id: str
    channel: str
    payload: dict = field(default_factory=dict)
    received_at: str = ""


@dataclass(frozen=True)
class ExecutionContract:
    issue_id: str
    card_issue_id: str
    confirmed_by: str
    confirmed_at: str
    confirmation_channel: str
    contract_hash: str
    status: str = "active"
