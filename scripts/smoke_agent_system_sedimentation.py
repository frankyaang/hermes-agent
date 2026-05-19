#!/usr/bin/env python3
"""Staging-profile smoke for the sedimentation system.

The smoke enables sedimentation flags only for the supplied HERMES_HOME and
checks that events, staging, gstack evidence, and experience-card injection
paths work without granting automatic private-memory writes to external experts.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test sedimentation staging paths")
    parser.add_argument("--hermes-home", default="", help="Temp HERMES_HOME for smoke")
    parser.add_argument("--keep", action="store_true", help="Keep generated smoke home")
    args = parser.parse_args()

    home = Path(args.hermes_home) if args.hermes_home else Path(tempfile.mkdtemp(prefix="hermes_sedimentation_smoke_"))
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HERMES_HOME"] = str(home)
    os.environ["SESSION_CAPTURE_AUTO_ENABLED"] = "true"
    os.environ["USAGE_HINT_INJECTION_ENABLED"] = "true"
    os.environ["GSTACK_SEDIMENTATION_ENABLED"] = "true"

    try:
        _reload_flags()
        result = _run_smoke(home)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "ok" else 1
    finally:
        if not args.keep and not args.hermes_home:
            shutil.rmtree(home, ignore_errors=True)


def _reload_flags() -> None:
    import agent_system.sedimentation.feature_flags as sediment_flags

    importlib.reload(sediment_flags)


def _run_smoke(home: Path) -> dict:
    from agent.experience_card import render_card, trigger_check
    from agent.memory_dispatcher import dispatch_event
    from agent.memory_event import create_event, list_events, write_event
    from agent.staging_store import list_staging
    from agent_system.gstack_control.adapter import GstackResult
    from agent_system.sedimentation.experience_layer import write_to_layer
    from agent_system.sedimentation.gstack_bridge import route_gstack_result

    events = [
        create_event(
            source_type="user_correction",
            source_uri="hermes://smoke/user-correction",
            actor_user_id="feishu:ou_smoke",
            subject="用户纠正：这里不是结论，只是待确认假设",
            risk_flags=["user_correction"],
            recommended_destination="personal_memory",
        ),
        create_event(
            source_type="write_failure",
            source_uri="hermes://smoke/tool-failure",
            actor_user_id="feishu:ou_smoke",
            subject="knowledge_write permission denied",
            risk_flags=["tool_failure", "permission_unclear"],
            recommended_destination="staging",
        ),
        create_event(
            source_type="session",
            source_uri="hermes://smoke/project-process",
            actor_user_id="feishu:ou_smoke",
            subject="项目流程：下一轮需要补齐来源证据",
            risk_flags=[],
            recommended_destination="project_process",
            project_hint="agent_system",
        ),
    ]

    dispatch_results = []
    for event in events:
        write_event(event, hermes_home=home)
        dispatch_results.append(dispatch_event(event, hermes_home=home).__dict__)

    gstack_result = GstackResult(
        available=False,
        command="gstack review --advisory",
        exit_code=None,
        stdout="",
        stderr="",
        blocked_reason="gstack CLI not found at PATH",
        duration_ms=0,
    )
    bridge = route_gstack_result("gstack.review", gstack_result, project_hint="agent_system", hermes_home=home)

    denied = write_to_layer(
        "expert_mem",
        "gstack lesson attempt",
        caller_id="gstack_bridge",
        expert_id="review_expert",
        hermes_home=home,
    )

    card = trigger_check("请按 David 的判断习惯处理这个跨产品信息", hermes_home=home)
    card_rendered = bool(card and render_card(card))

    event_count = len(list_events(hermes_home=home))
    staging_entries = list_staging(hermes_home=home)
    project_process_exists = (home / "project_process" / "records.jsonl").exists()
    automatic_card_store_exists = (home / "experience_cards" / "cards.jsonl").exists()

    checks = {
        "event_count_at_least_5": event_count >= 5,
        "staging_entries_at_least_3": len(staging_entries) >= 3,
        "project_process_written": project_process_exists,
        "gstack_bridge_no_direct_memory": bridge.destination in {"staging", "audit_evidence", "noop"},
        "gstack_acl_denied_to_staging": (not denied.success) and bool(denied.staging_id),
        "experience_card_ephemeral_rendered": card_rendered,
        "experience_card_not_persisted_automatically": not automatic_card_store_exists,
    }
    return {
        "status": "ok" if all(checks.values()) else "failed",
        "hermes_home": str(home),
        "flags": {
            "SESSION_CAPTURE_AUTO_ENABLED": os.environ["SESSION_CAPTURE_AUTO_ENABLED"],
            "USAGE_HINT_INJECTION_ENABLED": os.environ["USAGE_HINT_INJECTION_ENABLED"],
            "GSTACK_SEDIMENTATION_ENABLED": os.environ["GSTACK_SEDIMENTATION_ENABLED"],
        },
        "dispatch_results": dispatch_results,
        "gstack_bridge": bridge.__dict__,
        "experience_layer_denial": denied.__dict__,
        "event_count": event_count,
        "staging_count": len(staging_entries),
        "checks": checks,
        "secret_redaction": "no secrets printed",
    }


if __name__ == "__main__":
    raise SystemExit(main())
