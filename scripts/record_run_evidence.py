#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.run_evidence import append_run_evidence, make_run_evidence_record


def main() -> int:
    parser = argparse.ArgumentParser(description="Record real Agent-System run evidence")
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--platform", default="feishu")
    parser.add_argument("--route", required=True)
    parser.add_argument("--status", required=True, choices=["ok", "failed", "blocked"])
    parser.add_argument("--failure-code", default="")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--artifact-path", default="")
    parser.add_argument("--audit-log", default="")
    parser.add_argument("--review-summary", default="")
    parser.add_argument("--model-routing-json", default="")
    parser.add_argument("--memory-event-id", action="append", default=[])
    parser.add_argument("--staging-id", action="append", default=[])
    parser.add_argument("--human-gate-json", default="")
    args = parser.parse_args()

    record = make_run_evidence_record(
        platform=args.platform,
        route=args.route,
        status=args.status,
        message_id=args.message_id,
        session_id=args.session_id,
        run_id=args.run_id,
        failure_code=args.failure_code,
        artifact_path=args.artifact_path,
        audit_log=args.audit_log,
        review_summary=args.review_summary,
        model_routing=_json_obj(args.model_routing_json),
        memory_event_ids=args.memory_event_id,
        staging_ids=args.staging_id,
        human_gate=_json_obj(args.human_gate_json),
    )
    path = append_run_evidence(Path(args.hermes_home), record)
    print(json.dumps({"path": str(path), "record": record}, ensure_ascii=False, indent=2))
    return 0


def _json_obj(value: str) -> dict:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("JSON argument must be an object")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
