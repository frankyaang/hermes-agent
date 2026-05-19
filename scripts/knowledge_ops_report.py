#!/usr/bin/env python3
"""KnowledgeOps Diagnostic Report.

Produces a human-readable report of the Hermes knowledge asset operations:
- Pending capture analysis (dispositions, identity drift, retryable counts)
- Audit event summary (reads, write intents, ACL outcomes, provider outcomes)
- Transaction lifecycle summary

Usage:
    python scripts/knowledge_ops_report.py
    python scripts/knowledge_ops_report.py --dry-run-replay
    python scripts/knowledge_ops_report.py --hermes-home /path/to/hermes/home
    python scripts/knowledge_ops_report.py --months 3

Safe to run at any time: this script is read-only and never replays production data.
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def get_hermes_home(override: str | None = None) -> Path:
    if override:
        return Path(override)
    from hermes_constants import get_hermes_home as _gh
    return _gh()


def load_pending(hermes_home: Path) -> list[dict]:
    path = hermes_home / "knowledge" / "pending_captures.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    return records


def load_audit_events(hermes_home: Path, months_back: int = 1) -> list[dict]:
    """Load legacy audit.jsonl events for the last N months."""
    events = []
    audit_dir = hermes_home / "knowledge" / "audit"
    if not audit_dir.exists():
        return []
    now = datetime.now(timezone.utc)
    for i in range(months_back):
        month = datetime(now.year, now.month - i if now.month > i else 12 + now.month - i, 1).strftime("%Y-%m")
        path = audit_dir / month / "audit.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
    return events


def load_tx_events(hermes_home: Path, months_back: int = 1) -> list[dict]:
    """Load transaction audit events (tx_audit.jsonl) for the last N months."""
    events = []
    audit_dir = hermes_home / "knowledge" / "audit"
    if not audit_dir.exists():
        return []
    now = datetime.now(timezone.utc)
    for i in range(months_back):
        if now.month - i >= 1:
            month = datetime(now.year, now.month - i, 1).strftime("%Y-%m")
        else:
            month = datetime(now.year - 1, 12 + now.month - i, 1).strftime("%Y-%m")
        path = audit_dir / month / "tx_audit.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
    return events


def report_pending(records: list[dict]) -> None:
    from agent.pending_capture import _classify_pending_disposition

    print("\n" + "=" * 70)
    print("PENDING CAPTURES")
    print("=" * 70)
    print(f"Total pending: {len(records)}")

    if not records:
        print("  (none)")
        return

    dispositions = [_classify_pending_disposition(r) for r in records]
    counts = Counter(d["disposition"] for d in dispositions)

    print("\nDisposition summary:")
    for disposition, count in sorted(counts.items()):
        print(f"  {disposition}: {count}")

    print("\nRetryable captures:")
    retryable = [d for d in dispositions if d.get("retryable")]
    for d in retryable:
        print(f"  [{d['capture_id'][:8]}..] {d['disposition']} — {d['rationale'][:80]}")

    print("\nBlocked captures:")
    blocked = [d for d in dispositions if not d.get("retryable")]
    for d in blocked:
        print(f"  [{d['capture_id'][:8]}..] {d['disposition']} — {d['rationale'][:80]}")

    print("\nIdentity breakdown:")
    identity_groups = defaultdict(list)
    for rec in records:
        uid = rec.get("original_user_id") or rec.get("user_id", "unknown")
        identity_groups[uid].append(rec["capture_id"][:8])
    for uid, ids in sorted(identity_groups.items()):
        print(f"  {uid}: {len(ids)} capture(s) [{', '.join(ids[:3])}{'...' if len(ids) > 3 else ''}]")


def report_audit_events(events: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("AUDIT EVENTS (legacy query/write events)")
    print("=" * 70)
    print(f"Total events: {len(events)}")

    if not events:
        print("  (none)")
        return

    action_counts = Counter(e.get("action", "unknown") for e in events)
    print("\nAction counts:")
    for action, count in sorted(action_counts.items()):
        print(f"  {action}: {count}")

    granted = [e for e in events if e.get("granted")]
    denied = [e for e in events if not e.get("granted")]
    print(f"\nACL granted: {len(granted)} | ACL denied: {len(denied)}")

    if denied:
        deny_reasons = Counter(e.get("deny_reason", "unknown") for e in denied)
        print("Denial reasons:")
        for reason, count in sorted(deny_reasons.items()):
            print(f"  {reason}: {count}")

    users = Counter(e.get("user_id", "unknown") for e in events)
    print("\nTop users by event count:")
    for uid, count in users.most_common(5):
        print(f"  {uid}: {count}")


def report_tx_events(events: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("TRANSACTION LIFECYCLE EVENTS")
    print("=" * 70)
    print(f"Total tx events: {len(events)}")

    if not events:
        print("  (none — tx audit log not yet populated; run with --months for older months)")
        return

    event_type_counts = Counter(e.get("event_type", "unknown") for e in events)
    print("\nEvent type counts:")
    for etype, count in sorted(event_type_counts.items()):
        print(f"  {etype}: {count}")

    # Count write outcomes
    succeeded = sum(1 for e in events if e.get("event_type") == "provider_succeeded")
    failed = sum(1 for e in events if e.get("event_type") == "provider_failed")
    pending_created = sum(1 for e in events if e.get("event_type") == "pending_created")
    identity_blocked = sum(1 for e in events if e.get("event_type") == "identity_blocked")
    acl_denied = sum(1 for e in events if e.get("event_type") == "acl_denied")
    replay_succeeded = sum(1 for e in events if e.get("event_type") == "replay_succeeded")
    query_verified = sum(1 for e in events if e.get("event_type") == "query_verified")

    print(f"\nWrite lifecycle summary:")
    print(f"  provider_succeeded (true write success): {succeeded}")
    print(f"  query_verified (verified): {query_verified}")
    print(f"  provider_failed: {failed}")
    print(f"  pending_created: {pending_created}")
    print(f"  identity_blocked (drift): {identity_blocked}")
    print(f"  acl_denied: {acl_denied}")
    print(f"  replay_succeeded: {replay_succeeded}")

    if identity_blocked > 0:
        print("\n  ⚠ WARNING: identity_blocked events detected — background review may have drifted to CLI identity")

    print("\nNote: 'acl_granted' alone is NOT a write success. Only 'provider_succeeded' counts.")

    # Failure categories
    failed_events = [e for e in events if e.get("event_type") == "provider_failed"]
    if failed_events:
        categories = Counter(e.get("failure_category", "unknown") for e in failed_events)
        print("\nProvider failure categories:")
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count}")

    # Identity summary
    users = Counter(e.get("original_user_id", "unknown") for e in events if e.get("original_user_id"))
    if users:
        print("\nIdentities triggering write intents:")
        for uid, count in users.most_common(5):
            prefix = "⚠ CLI " if uid.startswith("cli:") else "  "
            print(f"  {prefix}{uid}: {count} event(s)")


def do_dry_run_replay(records: list[dict]) -> None:
    from agent.pending_capture import _classify_pending_disposition

    print("\n" + "=" * 70)
    print("DRY-RUN REPLAY ANALYSIS")
    print("=" * 70)
    print("(No production data modified — dry_run=True)")

    for rec in records:
        classification = _classify_pending_disposition(rec)
        capture_id = rec.get("capture_id", "?")
        disp = classification["disposition"]
        print(f"\n  [{capture_id[:8]}..] disposition={disp}")
        print(f"    user_id: {rec.get('user_id', '?')}")
        print(f"    original_user_id: {rec.get('original_user_id', '(not set)')}")
        print(f"    failure_reason: {rec.get('failure_reason', '?')}")
        print(f"    retryable: {classification.get('retryable', False)}")
        print(f"    rationale: {classification.get('rationale', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="KnowledgeOps Diagnostic Report")
    parser.add_argument("--hermes-home", help="Override HERMES_HOME path")
    parser.add_argument("--months", type=int, default=1, help="Audit months to include (default: 1)")
    parser.add_argument("--dry-run-replay", action="store_true", help="Analyze pending captures for replay eligibility")
    args = parser.parse_args()

    hermes_home = get_hermes_home(args.hermes_home)
    print(f"KnowledgeOps Diagnostic Report")
    print(f"HERMES_HOME: {hermes_home}")
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")

    pending = load_pending(hermes_home)
    audit_events = load_audit_events(hermes_home, months_back=args.months)
    tx_events = load_tx_events(hermes_home, months_back=args.months)

    report_pending(pending)
    report_audit_events(audit_events)
    report_tx_events(tx_events)

    if args.dry_run_replay:
        do_dry_run_replay(pending)

    print("\n" + "=" * 70)
    print("END OF REPORT")
    print("=" * 70)


if __name__ == "__main__":
    main()
