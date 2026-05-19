#!/usr/bin/env python3
"""Check real-runtime evidence gates for Hermes Agent-System.

This script is intentionally read-only. It does not mark routes ready and does
not write any evidence; it reports whether the current HERMES_HOME has enough
real operational traces for production enablement.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.operational_evidence import summarize_operational_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Agent-System operational evidence")
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--min-events", type=int, default=50)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when not ready")
    args = parser.parse_args()

    summary = summarize_operational_evidence(
        Path(args.hermes_home),
        min_events=args.min_events,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and summary["status"] != "ready":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
