"""幂等归档脚本：将 knowledge/pending_captures.jsonl 中卡住的条目归档到 staging.

处理策略：
- write_failed:FileNotFoundError → archived_gbrain_unavailable（gbrain CLI 未安装）
- product_line_not_authorized    → archived_acl_denied（ACL 拒绝）
- 其他 failure_reason             → archived_manual_review
- status 非 pending 的条目：跳过（幂等）
- staging.jsonl 中已有相同 event_id 的条目：跳过（幂等）

用法：
  python3 scripts/migrate_pending_captures.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _hermes_home() -> Path:
    import os
    h = os.environ.get("HERMES_HOME", "")
    if h:
        return Path(h)
    return Path.home() / ".hermes"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _archive_reason(failure_reason: str) -> str:
    if "FileNotFoundError" in failure_reason or "write_failed" in failure_reason:
        return "archived_gbrain_unavailable"
    if "product_line_not_authorized" in failure_reason:
        return "archived_acl_denied"
    return "archived_manual_review"


def run(dry_run: bool = False) -> None:
    home = _hermes_home()
    pending_path = home / "knowledge" / "pending_captures.jsonl"
    staging_path = home / "staging" / "staging.jsonl"

    if not pending_path.exists():
        print(f"pending_captures.jsonl not found at {pending_path}")
        sys.exit(0)

    # Backup original
    if not dry_run:
        backup = pending_path.with_suffix(".jsonl.bak_20260519")
        if not backup.exists():
            backup.write_bytes(pending_path.read_bytes())
            print(f"Backup created: {backup}")

    # Load existing staging event_ids for idempotency check
    staged_event_ids: set[str] = set()
    if staging_path.exists():
        for line in staging_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                eid = obj.get("event_id", "")
                if eid:
                    staged_event_ids.add(eid)
            except json.JSONDecodeError:
                pass

    # Read all pending entries
    entries = []
    for line in pending_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    archived = 0
    skipped = 0
    staging_rows: list[dict] = []
    updated_entries: list[dict] = []

    for entry in entries:
        if entry.get("status") != "pending":
            skipped += 1
            updated_entries.append(entry)
            continue

        capture_id = entry.get("capture_id", str(uuid.uuid4()))
        failure_reason = str(entry.get("failure_reason", ""))
        reason = _archive_reason(failure_reason)

        # If already staged (from previous dispatcher run), still mark archived
        already_staged = capture_id in staged_event_ids

        if not already_staged:
            staging_row = {
                "staging_id": str(uuid.uuid4()),
                "event_id": capture_id,
                "reason": reason,
                "original_failure": failure_reason,
                "status": "archived",
                "visibility_scope": "private",
                "created_at": _now_utc(),
            }
            staging_rows.append(staging_row)

        updated_entry = dict(entry)
        updated_entry["status"] = "archived"
        updated_entry["archived_reason"] = reason
        updated_entry["archived_at"] = _now_utc()
        updated_entries.append(updated_entry)
        archived += 1

    print(f"\nPending captures: {len(entries)} total")
    print(f"  To archive: {archived}")
    print(f"  Already processed / skipped: {skipped}")

    if dry_run:
        print("\n[DRY RUN] No files written. Would archive:")
        for row in staging_rows:
            print(f"  {row['event_id']} → {row['reason']}")
        return

    # Write staging entries
    if staging_rows:
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        with staging_path.open("a", encoding="utf-8") as f:
            for row in staging_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"\nWrote {len(staging_rows)} entries to {staging_path}")

    # Rewrite pending_captures.jsonl with updated statuses
    with pending_path.open("w", encoding="utf-8") as f:
        for entry in updated_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"Updated {pending_path}")

    # Summary
    status_counts: dict[str, int] = {}
    for e in updated_entries:
        s = e.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
    print(f"\nFinal status counts: {status_counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
