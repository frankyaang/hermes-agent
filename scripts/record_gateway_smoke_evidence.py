#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.run_evidence import make_gateway_smoke_record, record_gateway_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description="Record real Gateway/Feishu smoke evidence")
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--route", required=True)
    parser.add_argument("--status", required=True, choices=["ok", "failed", "blocked"])
    parser.add_argument("--platform", default="feishu")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--failure-code", default="")
    parser.add_argument("--artifact-path", default="")
    parser.add_argument("--audit-log", default="")
    parser.add_argument("--review-summary", default="")
    args = parser.parse_args()

    record = make_gateway_smoke_record(
        route=args.route,
        status=args.status,
        platform=args.platform,
        run_id=args.run_id,
        failure_code=args.failure_code,
        artifact_path=args.artifact_path,
        audit_log=args.audit_log,
        review_summary=args.review_summary,
    )
    path = record_gateway_smoke(Path(args.hermes_home), record)
    print(json.dumps({"path": str(path), "record": record}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
