#!/usr/bin/env python3
"""Agent-system production readiness gate script.

Checks:
1. All pipelines in routes.json have a manifest entry.
2. All skills in skills/ directory have a manifest entry.
3. ready routes' required_skills are all executable.
4. ready routes have allowed_entrypoints and output_contract.
5. unknown/non-ready routes do not appear in production candidates.
6. Prints summary table.
7. Exits non-zero on any violation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from project root or scripts/ subdirectory.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent_system.capability_readiness import (
    load_readiness_manifest,
    validate_readiness_manifest,
    ready_route_candidates,
)


def main() -> int:
    root = _ROOT
    routes_path = root / "agent_system" / "scheduler" / "main_scheduler" / "routes.json"
    if not routes_path.exists():
        print(f"ERROR: routes.json not found at {routes_path}", file=sys.stderr)
        return 1

    routes_payload = json.loads(routes_path.read_text(encoding="utf-8"))
    manifest = load_readiness_manifest(root)

    errors = validate_readiness_manifest(root, routes_payload)

    routes_list = manifest.get("routes", [])
    skills_list = manifest.get("skills", [])

    ready_routes = [r for r in routes_list if r.get("readiness_state") == "ready"]
    non_ready_routes = [r for r in routes_list if r.get("readiness_state") == "non_ready"]
    unknown_routes = [r for r in routes_list if r.get("readiness_state") == "unknown"]

    ready_skills = [s for s in skills_list if s.get("readiness_state") == "ready"]
    non_ready_skills = [s for s in skills_list if s.get("readiness_state") == "non_ready"]
    unknown_skills = [s for s in skills_list if s.get("readiness_state") == "unknown"]

    print("\n=== Agent-System Production Readiness Check ===\n")
    print(f"Routes  : {len(ready_routes)} ready | {len(non_ready_routes)} non-ready | {len(unknown_routes)} unknown")
    print(f"Skills  : {len(ready_skills)} ready | {len(non_ready_skills)} non-ready | {len(unknown_skills)} unknown")

    print("\n--- Route Summary ---")
    for r in routes_list:
        pid = r.get("pipeline_id", "?")
        state = r.get("readiness_state", "unknown")
        ep = r.get("allowed_entrypoints") or []
        flag = "✓" if state == "ready" else ("✗" if state == "non_ready" else "?")
        print(f"  {flag} [{state:10s}] {pid}  entrypoints={ep}")

    print("\n--- Skill Summary ---")
    for s in skills_list:
        sid = s.get("skill_id", "?")
        state = s.get("readiness_state", "unknown")
        exe = s.get("executable", False)
        etype = s.get("executor_type", "unknown")
        flag = "✓" if state == "ready" else ("✗" if state == "non_ready" else "?")
        print(f"  {flag} [{state:10s}] {sid}  executable={exe}  executor_type={etype}")

    # Rule 5: unknown/non-ready routes must not appear in production candidates
    production_candidates = ready_route_candidates(root, routes_payload, entrypoint="gateway")
    candidate_ids = {c["pipeline_id"] for c in production_candidates}
    non_ready_ids = {
        r.get("pipeline_id")
        for r in routes_list
        if r.get("readiness_state") in ("non_ready", "unknown")
    }
    leaked = candidate_ids & non_ready_ids
    if leaked:
        for pid in sorted(leaked):
            errors.append(f"GATE_VIOLATION: non-ready/unknown pipeline {pid!r} appears in production candidates")

    print(f"\n--- Production Candidates (gateway entrypoint): {len(production_candidates)} ---")
    for c in production_candidates:
        print(f"  ✓ {c['pipeline_id']}")
    if not production_candidates:
        print("  (none — all routes are unknown or non-ready)")

    if errors:
        print(f"\n=== VIOLATIONS ({len(errors)}) ===")
        for e in errors:
            print(f"  ✗ {e}")
        print("\nREADINESS CHECK FAILED")
        return 1

    print("\nREADINESS CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
