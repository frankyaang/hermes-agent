"""
Decision gate — validates IssueSpec list and produces DecisionCard.

Rules:
- Any issue with is_fake_closure=True → return None (no contract possible)
- Any issue with missing required fields → DecisionCard(status="incomplete")
- All issues valid → DecisionCard(status="pending_confirmation")

Pure function — no I/O, no side effects.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .models import DecisionCard, IssueSpec


def evaluate(issues: list[IssueSpec]) -> DecisionCard | None:
    """
    Evaluate list of IssueSpec and return DecisionCard or None.

    Returns None if any issue is a fake closure.
    Returns DecisionCard(status="incomplete") if any required field is missing.
    Returns DecisionCard(status="pending_confirmation") if all issues are valid.
    """
    if not issues:
        return None

    # Fake closure check — any fake closure → reject entire batch
    for issue in issues:
        if issue.is_fake_closure:
            return None

    all_missing: list[str] = []
    follow_up: list[str] = []

    for issue in issues:
        missing = issue.required_fields_present()
        if missing:
            all_missing.extend(missing)
            for field in missing:
                follow_up.append(
                    f"Issue '{issue.title or '(untitled)'}': please provide '{field}'"
                )

    issue_id = _make_issue_id(issues)
    now = datetime.now(timezone.utc).isoformat()
    raw_hash = _raw_material_hash(issues)

    if all_missing:
        return DecisionCard(
            issue_id=issue_id,
            status="incomplete",
            issues=tuple(issues),
            missing_fields=tuple(sorted(set(all_missing))),
            follow_up=tuple(follow_up),
            created_at=now,
            raw_material_hash=raw_hash,
        )

    return DecisionCard(
        issue_id=issue_id,
        status="pending_confirmation",
        issues=tuple(issues),
        missing_fields=(),
        follow_up=(),
        created_at=now,
        raw_material_hash=raw_hash,
    )


def _make_issue_id(issues: list[IssueSpec]) -> str:
    content = json.dumps(
        [{"title": i.title, "owner": i.owner} for i in issues],
        sort_keys=True,
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _raw_material_hash(issues: list[IssueSpec]) -> str:
    content = json.dumps(
        [{"title": i.title, "owner": i.owner, "description": i.description}
         for i in issues],
        sort_keys=True,
    )
    return hashlib.sha256(content.encode()).hexdigest()[:12]
