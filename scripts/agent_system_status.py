#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.status_report import build_status_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Print machine-readable Agent-System production gate status")
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--min-events", type=int, default=50)
    args = parser.parse_args()

    report = build_status_report(
        hermes_home=Path(args.hermes_home).expanduser(),
        repo_root=Path(args.repo_root).expanduser(),
        min_events=args.min_events,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
