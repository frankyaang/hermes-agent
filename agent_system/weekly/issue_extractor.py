"""
Issue extractor — parses weekly material dict into IssueSpec list.

Accepts: dict with "items" list (each item: title, owner, status, priority, description)
Returns: list[IssueSpec]

Pure function — no I/O, no side effects.
"""
from __future__ import annotations

from typing import Any

from .models import IssueSpec

_FAKE_CLOSURE_SIGNALS = frozenset({
    "closed",
    "done",
    "resolved",
    "complete",
    "completed",
})


def extract_issues(material: dict[str, Any]) -> list[IssueSpec]:
    """
    Extract IssueSpec objects from weekly material dict.

    Fake closure detection: status in CLOSED signals AND description is empty
    → marks is_fake_closure=True.
    """
    items = material.get("items", [])
    result: list[IssueSpec] = []
    for item in items:
        title = str(item.get("title", "")).strip()
        owner = str(item.get("owner", "")).strip()
        status = str(item.get("status", "open")).strip().lower()
        priority = str(item.get("priority", "medium")).strip()
        description = str(item.get("description", "")).strip()

        is_fake = (
            status in _FAKE_CLOSURE_SIGNALS
            and not description
        )

        result.append(IssueSpec(
            title=title,
            owner=owner,
            status=status,
            priority=priority,
            description=description,
            is_fake_closure=is_fake,
        ))
    return result
