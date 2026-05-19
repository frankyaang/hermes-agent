#!/usr/bin/env python3
"""Hermes release readiness evidence gate.

该脚本只读取仓库、manifest 和 runtime evidence，不修改真实数据。它的目标不是把
能力升级为 ready，而是把 release decision 从自然语言判断固化为可复查报告。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_system.capability_readiness import (  # noqa: E402
    _invalidate_manifest_cache,
    load_readiness_manifest,
    ready_route_candidates,
    validate_readiness_manifest,
)
from hermes_constants import get_hermes_home  # noqa: E402

try:  # noqa: E402
    from cognitive_governance_smoke import artifact_report
except ImportError:  # pragma: no cover - pytest imports this file as a module.
    from scripts.cognitive_governance_smoke import artifact_report

REQUIRED_PHASE9_COMMITS = (
    "ac0dc548c526674b49d79d70d57bd074bade8e5e",
    "522475dda1a0259f2c518ebaff50ede6b3b97279",
    "9c1eca9e56f3105423289622a0706593e0d4afe1",
    "521cc173d71f81e893e294326cfd68b426948603",
)

ARTIFACT_KINDS = (
    "memory_events",
    "staging",
    "experience_cards",
    "project_process",
    "pending_captures",
)

ARTIFACT_REQUIRED_FIELDS = (
    "status",
    "producer_runtime_path",
    "source_capability",
    "sanitized_summary",
)

JsonDict = dict[str, Any]
CommandRunner = Callable[[Sequence[str], Path], JsonDict]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_command(args: Sequence[str], cwd: Path) -> JsonDict:
    proc = subprocess.run(
        list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _shell_command(command: str, cwd: Path) -> JsonDict:
    return _run_command(["zsh", "-lc", command], cwd)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> tuple[list[JsonDict], list[str]]:
    if not path.exists():
        return [], []
    records: list[JsonDict] = []
    errors: list[str] = []
    for index, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{index}: JSON decode failed: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path}:{index}: JSONL record is not an object")
            continue
        records.append(value)
    return records, errors


def _artifact_path(home: Path, kind: str) -> Path:
    return {
        "memory_events": home / "memory_events" / "events.jsonl",
        "staging": home / "staging" / "staging.jsonl",
        "experience_cards": home / "experience_cards" / "cards.jsonl",
        "project_process": home / "project_process" / "records.jsonl",
        "pending_captures": home / "knowledge" / "pending_captures.jsonl",
    }[kind]


def _state_counter(items: list[JsonDict]) -> dict[str, int]:
    counts = Counter(
        f"{item.get('readiness_state', 'unknown')}|production_ready={bool(item.get('production_ready'))}"
        for item in items
    )
    return dict(sorted(counts.items()))


def _entry_id(kind: str, item: JsonDict) -> str:
    if kind == "route":
        return str(item.get("pipeline_id") or "")
    if kind == "skill":
        return str(item.get("skill_id") or "")
    return str(item.get("capability_id") or "")


def _next_action_for(item: JsonDict) -> str:
    state = str(item.get("readiness_state") or "unknown")
    if state == "unknown":
        return "补齐 owner、output_contract、allowed_entrypoints、真实执行证据后再评审"
    if state == "non_ready":
        return "解除 readiness_reason 中记录的阻塞依赖，并补真实 smoke evidence"
    if state == "deferred":
        return "保持 deferred；只有真实依赖和 smoke 证据齐备后才能重新评审"
    if state in {"contract_complete", "smoke_verified"}:
        return "补主路径 runtime evidence、release gate 证据和生产准入口径后再提升"
    if not item.get("production_ready"):
        return "production_ready=false；需要明确发布证据、owner 和升级条件"
    return ""


def readiness_burn_down(manifest: JsonDict) -> list[JsonDict]:
    rows: list[JsonDict] = []
    for section, kind in (("routes", "route"), ("capabilities", "capability"), ("skills", "skill")):
        for item in manifest.get(section, []):
            state = str(item.get("readiness_state") or "unknown")
            production_ready = bool(item.get("production_ready"))
            if state == "ready" and production_ready:
                continue
            rows.append(
                {
                    "kind": kind,
                    "id": _entry_id(kind, item),
                    "readiness_state": state,
                    "production_ready": production_ready,
                    "owner": item.get("owner") or "",
                    "reason": item.get("readiness_reason") or item.get("evidence") or "",
                    "next_action": _next_action_for(item),
                }
            )
    return rows


def build_readiness_ledger(root: Path) -> JsonDict:
    _invalidate_manifest_cache(root)
    manifest = load_readiness_manifest(root)
    return {
        "summary": {
            "routes": _state_counter(list(manifest.get("routes", []))),
            "capabilities": _state_counter(list(manifest.get("capabilities", []))),
            "skills": _state_counter(list(manifest.get("skills", []))),
        },
        "burn_down": readiness_burn_down(manifest),
    }


def build_routes_manifest_check(root: Path) -> JsonDict:
    routes_path = root / "agent_system" / "scheduler" / "main_scheduler" / "routes.json"
    routes_payload = _read_json(routes_path, {"pipelines": []})
    _invalidate_manifest_cache(root)
    manifest = load_readiness_manifest(root)
    errors = list(validate_readiness_manifest(root, routes_payload))

    candidate_ids = {
        str(candidate.get("pipeline_id") or "")
        for candidate in ready_route_candidates(root, routes_payload, entrypoint="gateway")
    }
    blocked_ids = {
        str(route.get("pipeline_id") or "")
        for route in manifest.get("routes", [])
        if route.get("readiness_state") in {"unknown", "non_ready"}
    }
    leaked = sorted(candidate_ids & blocked_ids)
    for pipeline_id in leaked:
        errors.append(
            f"GATE_VIOLATION: non-ready/unknown pipeline {pipeline_id!r} appears in production candidates"
        )

    return {
        "routes_path": str(routes_path),
        "manifest_path": str(root / "agent_system" / "readiness_manifest.json"),
        "manifest_errors": errors,
        "production_candidates": sorted(candidate_ids),
        "non_ready_candidate_leaks": leaked,
        "consistent": not errors,
    }


def build_runtime_artifact_evidence(home: Path) -> JsonDict:
    report = artifact_report(home)
    blockers: list[str] = []
    artifacts: JsonDict = {}

    for kind in ARTIFACT_KINDS:
        path = _artifact_path(home, kind)
        records, parse_errors = _read_jsonl(path)
        missing_fields: list[JsonDict] = []
        status_counts = Counter(str(record.get("status") or "missing") for record in records)
        for index, record in enumerate(records, start=1):
            missing = [field for field in ARTIFACT_REQUIRED_FIELDS if not record.get(field)]
            if missing:
                missing_fields.append({"line": index, "missing": missing})
        if parse_errors:
            blockers.extend(parse_errors)
        if not path.exists():
            blockers.append(f"{kind}: artifact file does not exist")
        if path.exists() and not records:
            blockers.append(f"{kind}: artifact file is empty")
        if status_counts.get("unknown"):
            blockers.append(f"{kind}: contains unknown status records")
        if missing_fields:
            blockers.append(f"{kind}: records missing runtime evidence fields")

        artifacts[kind] = {
            **report.get(kind, {}),
            "required_fields": list(ARTIFACT_REQUIRED_FIELDS),
            "missing_evidence_fields": missing_fields,
        }

    return {
        "hermes_home": str(home),
        "artifacts": artifacts,
        "complete": not blockers,
        "blockers": blockers,
    }


def _parse_ahead_behind(value: str) -> tuple[int | None, int | None]:
    parts = value.split()
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def build_git_delivery(
    root: Path,
    required_commits: Sequence[str] = REQUIRED_PHASE9_COMMITS,
    command_runner: CommandRunner = _run_command,
) -> JsonDict:
    branch = command_runner(["git", "branch", "--show-current"], root)
    head = command_runner(["git", "rev-parse", "HEAD"], root)
    dirty = command_runner(["git", "status", "--porcelain=v1"], root)
    ahead_behind = command_runner(["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"], root)
    remote_head = command_runner(["git", "rev-parse", "--verify", "fork/codex/dev-env"], root)

    ahead, behind = _parse_ahead_behind(ahead_behind.get("stdout", ""))
    head_sha = head.get("stdout", "")
    required: dict[str, bool] = {}
    for commit in required_commits:
        result = command_runner(["git", "merge-base", "--is-ancestor", commit, "HEAD"], root)
        required[commit] = result.get("returncode") == 0

    commands_ok = all(
        result.get("returncode") == 0
        for result in (branch, head, dirty, ahead_behind)
    )
    remote_sha = remote_head.get("stdout", "")

    return {
        "branch": branch.get("stdout", ""),
        "head": head_sha,
        "dirty": bool(dirty.get("stdout")),
        "dirty_entries": dirty.get("stdout", "").splitlines(),
        "ahead": ahead,
        "behind": behind,
        "commands_ok": commands_ok,
        "required_commits": required,
        "all_required_commits_present": all(required.values()),
        "remote_push": {
            "remote": "fork",
            "branch": "codex/dev-env",
            "remote_tracking_ref": "fork/codex/dev-env",
            "remote_head": remote_sha,
            "pushed": bool(head_sha and remote_sha and head_sha == remote_sha),
        },
    }


def _command_path(command: str, root: Path) -> str:
    result = _shell_command(f"command -v {command}; true", root)
    return str(result.get("stdout") or "").strip()


def _gbrain_version(root: Path) -> str:
    path = _command_path("gbrain", root)
    if not path:
        return ""
    result = _shell_command("gbrain --version 2>/dev/null || gbrain --help 2>/dev/null | head -n 1", root)
    return str(result.get("stdout") or "").splitlines()[0] if result.get("stdout") else ""


def build_external_dependency_truth_table(root: Path) -> JsonDict:
    gstack_path = _command_path("gstack", root)
    gbrain_path = _command_path("gbrain", root)
    feishu_env = any(
        os.getenv(name)
        for name in (
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_VERIFICATION_TOKEN",
            "FEISHU_ENCRYPT_KEY",
        )
    )

    dependencies = {
        "gstack": {
            "path": gstack_path,
            "readiness_state": "installed_unverified" if gstack_path else "deferred",
            "production_ready": False,
            "real_gstack": bool(gstack_path),
            "blocks_upgrade": False,
            "reason": "需要真实 gstack smoke 证据后才能 production_ready"
            if gstack_path
            else "gstack CLI not found; keep deferred/non_ready",
        },
        "gbrain": {
            "path": gbrain_path,
            "version": _gbrain_version(root) if gbrain_path else "",
            "readiness_state": "installed_unverified" if gbrain_path else "missing",
            "production_ready": False,
            "blocks_upgrade": False,
            "reason": "CLI 存在不等于 Hermes provider read/write production smoke ready"
            if gbrain_path
            else "gbrain CLI not found",
        },
        "feishu": {
            "path": "",
            "readiness_state": "credentials_present_unverified" if feishu_env else "shadow_advisory",
            "production_ready": False,
            "blocks_upgrade": False,
            "reason": "缺少真实 Feishu send/callback/ledger update production evidence",
        },
    }
    return {
        "dependencies": dependencies,
        "all_production_ready": all(dep.get("production_ready") for dep in dependencies.values()),
        "blocking_dependencies": [
            name for name, dep in dependencies.items() if dep.get("blocks_upgrade")
        ],
        "release_gaps": [
            name for name, dep in dependencies.items() if not dep.get("production_ready")
        ],
    }


def _git_upgrade_gaps(git_delivery: JsonDict) -> list[str]:
    gaps: list[str] = []
    if not git_delivery.get("commands_ok"):
        gaps.append("git delivery commands did not all succeed")
    if git_delivery.get("dirty"):
        gaps.append("working tree is dirty")
    if git_delivery.get("behind") not in (0, None):
        gaps.append(f"branch is behind origin/main by {git_delivery.get('behind')} commits")
    if git_delivery.get("ahead") is None or git_delivery.get("behind") is None:
        gaps.append("unable to determine ahead/behind versus origin/main")
    if not git_delivery.get("all_required_commits_present"):
        gaps.append("one or more required Phase 9 commits are missing from HEAD")
    if not git_delivery.get("remote_push", {}).get("pushed"):
        gaps.append("HEAD is not evidenced as pushed to fork/codex/dev-env")
    return gaps


def _readiness_gaps(ledger: JsonDict) -> list[str]:
    burn_down = ledger.get("burn_down", [])
    if not burn_down:
        return []
    return [f"{len(burn_down)} readiness entries remain non-production"]


def _external_gaps(external: JsonDict) -> list[str]:
    gaps = list(external.get("release_gaps", []))
    return [f"external dependency {name} is not production_ready" for name in gaps]


def decide_release(report: JsonDict) -> JsonDict:
    blockers: list[str] = []
    gaps: list[str] = []

    routes_check = report["routes_manifest_check"]
    runtime = report["runtime_artifact_evidence"]
    git_delivery = report["git_delivery"]
    external = report["external_dependency_truth_table"]

    blockers.extend(routes_check.get("manifest_errors", []))
    blockers.extend(runtime.get("blockers", []))
    blockers.extend(external.get("blocking_dependencies", []))
    if not git_delivery.get("all_required_commits_present"):
        blockers.append("required Phase 9 commits missing")

    gaps.extend(_git_upgrade_gaps(git_delivery))
    gaps.extend(_readiness_gaps(report["readiness_ledger"]))
    gaps.extend(_external_gaps(external))
    if not report.get("test_evidence", {}).get("attested"):
        gaps.append("required scripts/run_tests.sh evidence not attested in release gate")

    if blockers:
        decision = "release_blocked"
    elif gaps:
        decision = "release_candidate_only"
    else:
        decision = "release_upgrade_allowed"

    return {
        "final_decision": decision,
        "allow_upgrade_hermes": decision == "release_upgrade_allowed",
        "blockers": sorted(set(blockers)),
        "release_gaps": sorted(set(gaps)),
    }


def build_release_readiness_report(
    root: Path = ROOT,
    hermes_home: Path | None = None,
    required_commits: Sequence[str] = REQUIRED_PHASE9_COMMITS,
    tests_attested: bool = False,
    git_delivery_override: JsonDict | None = None,
    external_dependency_override: JsonDict | None = None,
    command_runner: CommandRunner = _run_command,
) -> JsonDict:
    root = Path(root)
    home = Path(hermes_home) if hermes_home is not None else get_hermes_home()
    report: JsonDict = {
        "generated_at": _now(),
        "root": str(root),
        "release_truth_table": {
            "dev_is_delivery_source": True,
            "manifest_is_readiness_truth_source": True,
            "routes_are_scheduling_config_only": True,
            "contract_complete_is_not_production_ready": True,
            "mock_external_dependency_is_not_production_ready": True,
        },
        "git_delivery": git_delivery_override
        if git_delivery_override is not None
        else build_git_delivery(root, required_commits, command_runner),
        "readiness_ledger": build_readiness_ledger(root),
        "routes_manifest_check": build_routes_manifest_check(root),
        "runtime_artifact_evidence": build_runtime_artifact_evidence(home),
        "external_dependency_truth_table": external_dependency_override
        if external_dependency_override is not None
        else build_external_dependency_truth_table(root),
        "test_evidence": {
            "attested": tests_attested,
            "required_runner": "scripts/run_tests.sh",
        },
    }
    report["decision"] = decide_release(report)
    return report


def _print_text(report: JsonDict) -> None:
    decision = report["decision"]
    git_delivery = report["git_delivery"]
    print("\n=== Hermes Release Readiness Gate ===\n")
    print(f"Final decision       : {decision['final_decision']}")
    print(f"Allow Hermes upgrade : {'yes' if decision['allow_upgrade_hermes'] else 'no'}")
    print(f"Branch               : {git_delivery.get('branch')}")
    print(f"HEAD                 : {git_delivery.get('head')}")
    print(
        "Git drift            : "
        f"ahead={git_delivery.get('ahead')} behind={git_delivery.get('behind')} "
        f"dirty={git_delivery.get('dirty')}"
    )
    print(f"Fork push evidence   : {git_delivery.get('remote_push', {}).get('pushed')}")

    print("\n--- Readiness Summary ---")
    for section, counts in report["readiness_ledger"]["summary"].items():
        print(f"{section}: {counts}")

    print("\n--- External Dependencies ---")
    for name, dep in report["external_dependency_truth_table"]["dependencies"].items():
        print(
            f"{name}: state={dep.get('readiness_state')} "
            f"production_ready={dep.get('production_ready')} path={dep.get('path')}"
        )

    print("\n--- Blockers ---")
    for item in decision["blockers"] or ["(none)"]:
        print(f"- {item}")

    print("\n--- Release Gaps ---")
    for item in decision["release_gaps"] or ["(none)"]:
        print(f"- {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument(
        "--tests-passed",
        action="store_true",
        help="声明本轮必要 scripts/run_tests.sh 验证已经通过",
    )
    parser.add_argument(
        "--fail-unless-upgrade",
        action="store_true",
        help="除 release_upgrade_allowed 外均返回非零",
    )
    args = parser.parse_args()

    report = build_release_readiness_report(tests_attested=args.tests_passed)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)

    decision = report["decision"]["final_decision"]
    if decision == "release_blocked":
        return 1
    if args.fail_unless_upgrade and decision != "release_upgrade_allowed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
