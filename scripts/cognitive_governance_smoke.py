#!/usr/bin/env python3
"""Cognitive Governance runtime smoke and artifact evidence report.

用法：
  python scripts/cognitive_governance_smoke.py
  python scripts/cognitive_governance_smoke.py --write-smoke --backfill-legacy-status

脚本只处理 JSONL evidence 字段，不清空真实数据。backfill 会先创建备份。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.experience_card import ExperienceCard, render_card, trigger_check, write_card
from agent.memory_dispatcher import dispatch_event, dispatch_tool_failure
from agent.memory_event import create_event, write_event
from agent.project_process_store import write_record
from agent.runtime_artifact_evidence import sanitize_summary, with_runtime_evidence
from agent.session_capture import capture_turn
from hermes_constants import get_hermes_home

BACKUP_SUFFIX = ".bak_20260519_phase9"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonl_path(home: Path, key: str) -> Path:
    return {
        "memory_events": home / "memory_events" / "events.jsonl",
        "staging": home / "staging" / "staging.jsonl",
        "experience_cards": home / "experience_cards" / "cards.jsonl",
        "project_process": home / "project_process" / "records.jsonl",
        "pending_captures": home / "knowledge" / "pending_captures.jsonl",
    }[key]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"status": "parse_error", "raw_line": line[:160]})
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _backup_once(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def _defaults_for(kind: str, rec: dict[str, Any]) -> dict[str, Any]:
    if kind == "memory_events":
        return with_runtime_evidence(
            rec,
            status="captured",
            producer_runtime_path="agent.memory_event.write_event",
            source_capability="memory_event",
            summary_parts=(rec.get("subject"), rec.get("current_task"), rec.get("source_uri")),
        )
    if kind == "staging":
        status = "archived" if rec.get("status") == "archived" else "staged"
        return with_runtime_evidence(
            rec,
            status=status,
            producer_runtime_path="agent.staging_store.write_staging",
            source_capability="staging_store",
            summary_parts=(rec.get("reason"), rec.get("original_failure"), rec.get("source_uri")),
        )
    if kind == "experience_cards":
        return with_runtime_evidence(
            rec,
            status="active",
            producer_runtime_path="agent.experience_card.write_card",
            source_capability="experience_card",
            summary_parts=(rec.get("trigger"), rec.get("scope"), rec.get("source_case")),
        )
    if kind == "project_process":
        rec = with_runtime_evidence(
            rec,
            status="recorded",
            producer_runtime_path="agent.project_process_store.write_record",
            source_capability="project_process_store",
            summary_parts=(rec.get("subject"), rec.get("project_hint"), rec.get("source_uri")),
        )
        rec.setdefault("usage_hint", "project_material_usable")
        return rec
    if kind == "pending_captures":
        return with_runtime_evidence(
            rec,
            status=str(rec.get("status") or "pending"),
            producer_runtime_path="agent.pending_capture",
            source_capability="pending_capture",
            summary_parts=(
                rec.get("title"),
                rec.get("failure_reason"),
                rec.get("source_uri"),
            ),
        )
    return rec


def backfill_legacy_status(home: Path) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for kind in [
        "memory_events",
        "staging",
        "experience_cards",
        "project_process",
        "pending_captures",
    ]:
        path = _jsonl_path(home, kind)
        records = _read_jsonl(path)
        if not records:
            continue
        updated = [_defaults_for(kind, rec) for rec in records]
        if updated != records:
            backup = _backup_once(path)
            _write_jsonl(path, updated)
            changed[kind] = {
                "path": str(path),
                "line_count": len(updated),
                "backup": str(backup) if backup else "",
            }
    return changed


def _has_card(home: Path, card_id: str) -> bool:
    return any(rec.get("id") == card_id for rec in _read_jsonl(_jsonl_path(home, "experience_cards")))


def write_smoke(home: Path) -> dict[str, Any]:
    smoke_session = "phase9-cognitive-smoke"
    smoke_actor = "smoke:phase9"

    capture_result = capture_turn(
        "David 提到跨产品线优先级需要先确认来源和项目范围",
        session_id=smoke_session,
        actor_user_id=smoke_actor,
        platform="cli",
        hermes_home=home,
    )
    routing_hint = capture_result[1] if capture_result else ""

    failure_result = dispatch_tool_failure(
        title="Phase9 smoke permission_denied fallback",
        source_uri="hermes://smoke/phase9/permission-denied",
        actor_user_id=smoke_actor,
        session_id=smoke_session,
        product_line_hint="smoke_product_line",
        hermes_home=home,
    )

    project_event = create_event(
        source_type="document",
        source_uri="hermes://smoke/phase9/project-process",
        actor_user_id=smoke_actor,
        subject="Phase9 smoke project process record",
        risk_flags=[],
        recommended_destination="project_process",
        session_id=smoke_session,
        project_hint="phase9_smoke_project",
        product_line_hint="smoke_product_line",
        producer_runtime_path="scripts.cognitive_governance_smoke.write_smoke",
        source_capability="project_process_store",
    )
    write_event(project_event, hermes_home=home)
    project_dispatch = dispatch_event(project_event, hermes_home=home)

    card_id = "phase9-smoke-card"
    if not _has_card(home, card_id):
        write_card(
            ExperienceCard(
                id=card_id,
                trigger="Phase9Smoke",
                trigger_patterns=["Phase9Smoke"],
                retrieval_order=["runtime artifact evidence", "readiness manifest"],
                judgment_steps=["check status", "check producer_runtime_path", "check sanitized_summary"],
                avoid_actions=["do not mark production_ready without runtime evidence"],
                frontstage_expression="Use evidence-first release language",
                scope="phase9/cognitive_governance_smoke",
                invalid_when="Phase9 smoke contract changes",
                source_case="phase9-smoke",
                created_at=_now(),
                last_verified_at=_now(),
                sanitized_summary=sanitize_summary("Phase9Smoke", "runtime evidence card"),
            ),
            hermes_home=home,
        )

    card = trigger_check("David 提到要重新判断项目范围", hermes_home=home)
    rendered = render_card(card) if card else ""

    return {
        "capture_event_id": capture_result[0] if capture_result else "",
        "routing_hint_injected": bool(routing_hint and "usage_hint: action_rule_for_next_task" in routing_hint),
        "rendered_card_has_usage_hint": "usage_hint: action_rule_for_next_task" in rendered,
        "tool_failure_destination": failure_result.destination,
        "tool_failure_staging_id": failure_result.staging_id,
        "project_process_destination": project_dispatch.destination,
        "project_process_event_id": project_event.id,
    }


def artifact_report(home: Path) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for kind in [
        "memory_events",
        "staging",
        "experience_cards",
        "project_process",
        "pending_captures",
    ]:
        path = _jsonl_path(home, kind)
        records = _read_jsonl(path)
        counts = Counter(str(r.get("status") or r.get("state") or "unknown") for r in records)
        recent = records[-3:]
        report[kind] = {
            "path": str(path),
            "exists": path.exists(),
            "line_count": len(records),
            "status_counts": dict(sorted(counts.items())),
            "recent_sanitized_summary": [
                r.get("sanitized_summary") or sanitize_summary(r.get("subject"), r.get("reason"), r.get("title"))
                for r in recent
            ],
            "producer_runtime_paths": sorted({
                str(r.get("producer_runtime_path") or "")
                for r in records
                if r.get("producer_runtime_path")
            }),
        }
    return report


def gstack_status() -> dict[str, Any]:
    proc = subprocess.run(["zsh", "-lc", "command -v gstack; true"], capture_output=True, text=True)
    path = proc.stdout.strip()
    return {
        "real_gstack": bool(path),
        "path": path,
        "readiness_state": "ready" if path else "deferred",
        "production_ready": bool(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-smoke", action="store_true", help="写入一组真实主路径 smoke 记录")
    parser.add_argument(
        "--backfill-legacy-status",
        action="store_true",
        help="为旧 JSONL 记录补齐 evidence 字段（会先备份）",
    )
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    args = parser.parse_args()

    home = get_hermes_home()
    result: dict[str, Any] = {
        "hermes_home": str(home),
        "generated_at": _now(),
        "gstack": gstack_status(),
        "backfilled": {},
        "smoke": {},
    }

    if args.write_smoke:
        result["smoke"] = write_smoke(home)
    if args.backfill_legacy_status:
        result["backfilled"] = backfill_legacy_status(home)
    result["artifacts"] = artifact_report(home)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n=== Cognitive Governance Smoke Report ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
