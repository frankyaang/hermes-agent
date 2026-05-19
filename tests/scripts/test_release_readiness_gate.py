"""release_readiness_gate script tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import scripts.release_readiness_gate as gate


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_complete_artifacts(home: Path) -> None:
    payloads = {
        "memory_events/events.jsonl": {
            "id": "evt-1",
            "status": "captured",
            "producer_runtime_path": "agent.memory_event.write_event",
            "source_capability": "memory_event",
            "sanitized_summary": "captured event",
        },
        "staging/staging.jsonl": {
            "id": "stage-1",
            "status": "staged",
            "producer_runtime_path": "agent.staging_store.write_staging",
            "source_capability": "staging_store",
            "sanitized_summary": "staged fallback",
        },
        "experience_cards/cards.jsonl": {
            "id": "card-1",
            "status": "active",
            "producer_runtime_path": "agent.experience_card.write_card",
            "source_capability": "experience_card",
            "sanitized_summary": "active card",
        },
        "project_process/records.jsonl": {
            "id": "proc-1",
            "status": "recorded",
            "producer_runtime_path": "agent.project_process_store.write_record",
            "source_capability": "project_process_store",
            "sanitized_summary": "project process",
        },
        "knowledge/pending_captures.jsonl": {
            "id": "pending-1",
            "status": "archived",
            "producer_runtime_path": "agent.pending_capture",
            "source_capability": "pending_capture",
            "sanitized_summary": "archived pending",
        },
    }
    for relative, record in payloads.items():
        _write_jsonl(home / relative, [record])


def _ready_manifest() -> dict[str, Any]:
    return {
        "routes": [
            {
                "pipeline_id": "ready_flow",
                "readiness_state": "ready",
                "production_ready": True,
                "allowed_entrypoints": ["gateway"],
                "required_skills": ["ready_skill"],
                "output_contract": "ready output",
            }
        ],
        "skills": [
            {
                "skill_id": "ready_skill",
                "readiness_state": "ready",
                "production_ready": True,
                "executable": True,
                "executor_type": "system",
                "output_contract": "ready skill output",
            }
        ],
        "capabilities": [
            {
                "capability_id": "ready_capability",
                "readiness_state": "ready",
                "production_ready": True,
            }
        ],
    }


def _ready_routes() -> dict[str, Any]:
    return {
        "scheduler": "main_scheduler",
        "version": 1,
        "pipelines": [
            {
                "pipeline_id": "ready_flow",
                "node": "ready_skill",
                "production_ready": True,
            }
        ],
    }


def _write_project(root: Path, manifest: dict[str, Any], routes: dict[str, Any]) -> None:
    _write_json(root / "agent_system" / "readiness_manifest.json", manifest)
    _write_json(root / "agent_system" / "scheduler" / "main_scheduler" / "routes.json", routes)


def _git_delivery(**overrides: Any) -> dict[str, Any]:
    base = {
        "branch": "codex/dev-env",
        "head": "abc123",
        "dirty": False,
        "dirty_entries": [],
        "ahead": 0,
        "behind": 0,
        "commands_ok": True,
        "required_commits": {"phase9": True},
        "all_required_commits_present": True,
        "remote_push": {
            "remote": "fork",
            "branch": "codex/dev-env",
            "remote_tracking_ref": "fork/codex/dev-env",
            "remote_head": "abc123",
            "pushed": True,
        },
    }
    base.update(overrides)
    return base


def _external_dependencies(**overrides: Any) -> dict[str, Any]:
    dependencies = {
        "gstack": {
            "path": "/usr/local/bin/gstack",
            "readiness_state": "ready",
            "production_ready": True,
            "real_gstack": True,
            "blocks_upgrade": False,
            "reason": "verified in test",
        },
        "gbrain": {
            "path": "/usr/local/bin/gbrain",
            "version": "gbrain test",
            "readiness_state": "ready",
            "production_ready": True,
            "blocks_upgrade": False,
            "reason": "verified in test",
        },
        "feishu": {
            "path": "",
            "readiness_state": "ready",
            "production_ready": True,
            "blocks_upgrade": False,
            "reason": "verified in test",
        },
    }
    dependencies.update(overrides)
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


def _build_report(
    tmp_path: Path,
    manifest: dict[str, Any] | None = None,
    routes: dict[str, Any] | None = None,
    git_delivery: dict[str, Any] | None = None,
    external: dict[str, Any] | None = None,
    tests_attested: bool = True,
) -> dict[str, Any]:
    root = tmp_path / "repo"
    home = tmp_path / "home"
    _write_project(root, manifest or _ready_manifest(), routes or _ready_routes())
    _write_complete_artifacts(home)
    return gate.build_release_readiness_report(
        root=root,
        hermes_home=home,
        required_commits=("phase9",),
        tests_attested=tests_attested,
        git_delivery_override=git_delivery or _git_delivery(),
        external_dependency_override=external or _external_dependencies(),
    )


def test_current_like_state_is_release_candidate_only(tmp_path: Path) -> None:
    manifest = _ready_manifest()
    manifest["routes"][0]["readiness_state"] = "unknown"
    manifest["routes"][0]["production_ready"] = False
    manifest["routes"][0]["allowed_entrypoints"] = []
    manifest["capabilities"][0]["readiness_state"] = "contract_complete"
    manifest["capabilities"][0]["production_ready"] = False

    report = _build_report(
        tmp_path,
        manifest=manifest,
        routes={"scheduler": "main_scheduler", "version": 1, "pipelines": []},
        git_delivery=_git_delivery(behind=1273, ahead=84),
        external=_external_dependencies(
            gstack={
                "path": "",
                "readiness_state": "deferred",
                "production_ready": False,
                "real_gstack": False,
                "blocks_upgrade": False,
                "reason": "missing",
            }
        ),
    )

    assert report["decision"]["final_decision"] == "release_candidate_only"
    assert report["decision"]["allow_upgrade_hermes"] is False


def test_upstream_behind_cannot_upgrade(tmp_path: Path) -> None:
    report = _build_report(tmp_path, git_delivery=_git_delivery(behind=1))

    assert report["decision"]["final_decision"] == "release_candidate_only"
    assert "branch is behind origin/main by 1 commits" in report["decision"]["release_gaps"]


def test_dirty_worktree_cannot_upgrade(tmp_path: Path) -> None:
    report = _build_report(
        tmp_path,
        git_delivery=_git_delivery(dirty=True, dirty_entries=[" M PLANS.md"]),
    )

    assert report["decision"]["final_decision"] == "release_candidate_only"
    assert "working tree is dirty" in report["decision"]["release_gaps"]


def test_gstack_missing_is_deferred_not_ready(tmp_path: Path) -> None:
    external = _external_dependencies(
        gstack={
            "path": "",
            "readiness_state": "deferred",
            "production_ready": False,
            "real_gstack": False,
            "blocks_upgrade": False,
            "reason": "gstack CLI not found",
        }
    )

    report = _build_report(tmp_path, external=external)

    gstack = report["external_dependency_truth_table"]["dependencies"]["gstack"]
    assert gstack["readiness_state"] == "deferred"
    assert gstack["production_ready"] is False
    assert report["decision"]["final_decision"] == "release_candidate_only"


def test_gbrain_cli_only_is_installed_unverified_not_production_ready(tmp_path: Path) -> None:
    external = _external_dependencies(
        gbrain={
            "path": "/tmp/gbrain",
            "version": "gbrain test",
            "readiness_state": "installed_unverified",
            "production_ready": False,
            "blocks_upgrade": False,
            "reason": "CLI only",
        }
    )

    report = _build_report(tmp_path, external=external)

    gbrain = report["external_dependency_truth_table"]["dependencies"]["gbrain"]
    assert gbrain["readiness_state"] == "installed_unverified"
    assert gbrain["production_ready"] is False
    assert report["decision"]["final_decision"] == "release_candidate_only"


def test_runtime_artifact_missing_evidence_field_blocks_release(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    home = tmp_path / "home"
    _write_project(root, _ready_manifest(), _ready_routes())
    _write_complete_artifacts(home)
    _write_jsonl(
        home / "memory_events" / "events.jsonl",
        [{
            "id": "evt-1",
            "status": "captured",
            "producer_runtime_path": "agent.memory_event.write_event",
            "source_capability": "memory_event",
        }],
    )

    report = gate.build_release_readiness_report(
        root=root,
        hermes_home=home,
        required_commits=("phase9",),
        tests_attested=True,
        git_delivery_override=_git_delivery(),
        external_dependency_override=_external_dependencies(),
    )

    assert report["decision"]["final_decision"] == "release_blocked"
    assert any("memory_events" in blocker for blocker in report["decision"]["blockers"])


def test_routes_true_but_manifest_not_ready_blocks_release(tmp_path: Path) -> None:
    manifest = _ready_manifest()
    manifest["routes"][0]["readiness_state"] = "non_ready"
    manifest["routes"][0]["production_ready"] = False

    report = _build_report(tmp_path, manifest=manifest, routes=_ready_routes())

    assert report["decision"]["final_decision"] == "release_blocked"
    assert any("MANIFEST_CONFLICT" in blocker for blocker in report["decision"]["blockers"])


def test_non_ready_candidate_leak_blocks_release(tmp_path: Path, monkeypatch) -> None:
    manifest = _ready_manifest()
    manifest["routes"][0]["readiness_state"] = "non_ready"
    manifest["routes"][0]["production_ready"] = False
    routes = _ready_routes()
    routes["pipelines"][0]["production_ready"] = False

    monkeypatch.setattr(
        gate,
        "ready_route_candidates",
        lambda root, payload, entrypoint="gateway": [{"pipeline_id": "ready_flow"}],
    )

    report = _build_report(tmp_path, manifest=manifest, routes=routes)

    assert report["decision"]["final_decision"] == "release_blocked"
    assert report["routes_manifest_check"]["non_ready_candidate_leaks"] == ["ready_flow"]


def test_all_green_allows_release_upgrade(tmp_path: Path) -> None:
    report = _build_report(tmp_path)

    assert report["decision"]["final_decision"] == "release_upgrade_allowed"
    assert report["decision"]["allow_upgrade_hermes"] is True
    assert report["decision"]["blockers"] == []
    assert report["decision"]["release_gaps"] == []
