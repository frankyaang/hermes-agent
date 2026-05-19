from __future__ import annotations

import json
from pathlib import Path

from agent_system.capability_readiness import check_pipeline_readiness, ready_route_candidates
from agent_system.runtime import HermesAgentSystemRuntime
from agent_system.system_skill_executor import execute_system_skill


def _write(path: Path, content: str = "ok") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _context(path: Path) -> dict:
    return {
        "task_package": {"node_id": "artifact_status"},
        "input_payload": {"source_materials": [str(path)]},
        "prior_results": {},
    }


def test_artifact_status_system_executor_returns_file_meta(tmp_path: Path):
    artifact = _write(tmp_path / "report.md", "# Report\nok")

    result = execute_system_skill(
        skill_id="artifact_status",
        context=_context(artifact),
        project_root=tmp_path,
    )

    assert result["status"] == "completed"
    assert result["execution_mode"] == "system_skill_executor"
    output = result["output"]
    assert output["artifact_path"] == str(artifact)
    assert output["artifact_status"] == "available"
    assert output["file_meta"]["size_bytes"] > 0
    assert output["real_skill_execution"] is True


def test_artifact_delivery_system_executor_caps_text_preview(tmp_path: Path):
    artifact = _write(tmp_path / "large.md", "x" * 25000)

    result = execute_system_skill(
        skill_id="artifact_delivery",
        context=_context(artifact),
        project_root=tmp_path,
    )

    assert result["status"] == "completed"
    output = result["output"]
    assert output["delivery_mode"] == "inline_preview"
    assert len(output["content_preview"]) == 20000
    assert output["content_truncated"] is True


def test_doc_publish_system_executor_is_local_fallback(tmp_path: Path):
    artifact = _write(tmp_path / "publish.md", "# Publish me")

    result = execute_system_skill(
        skill_id="doc_publish",
        context=_context(artifact),
        project_root=tmp_path,
    )

    assert result["status"] == "completed"
    output = result["output"]
    assert output["publish_mode"] == "local_fallback_package"
    assert output["requires_external_publish"] is True
    assert output["content_preview"] == "# Publish me"


def test_missing_artifact_blocks_with_missing_input(tmp_path: Path):
    result = execute_system_skill(
        skill_id="artifact_status",
        context={
            "task_package": {"node_id": "artifact_status"},
            "input_payload": {"source_materials": ["请找报告"]},
            "prior_results": {},
        },
        project_root=tmp_path,
    )

    assert result["status"] == "blocked"
    assert result["missing_inputs"] == ["artifact_reference"]
    assert result["exceptions"][0]["blocking"] is True


def test_runtime_uses_system_executor_for_ready_system_skill(tmp_path: Path):
    project = tmp_path / "agent_system"
    artifact = _write(tmp_path / "status.md", "runtime ok")
    _seed_project(project)

    def fail_if_delegate_called(_context: dict) -> dict:
        raise AssertionError("system executor should bypass delegate_task")

    runtime = HermesAgentSystemRuntime(
        root_dir=project,
        skill_executor=fail_if_delegate_called,
        enforce_skill_readiness=True,
    )
    result = runtime.run_pipeline(
        pipeline_id="artifact_status_flow",
        input_payload={"source_materials": [str(artifact)]},
        parallel=False,
    )

    assert result["status"] == "completed"
    node_result = result["results"][0]
    assert node_result["skill_execution_modes"] == ["system_skill_executor"]
    assert node_result["output"]["artifact_path"] == str(artifact)


def test_readiness_manifest_loads_from_agent_system_root(tmp_path: Path):
    project = tmp_path / "agent_system"
    _seed_project(project)
    routes = json.loads(
        (project / "scheduler" / "main_scheduler" / "routes.json").read_text(encoding="utf-8")
    )

    result = check_pipeline_readiness(project, routes, "artifact_status_flow")
    candidates = ready_route_candidates(project, routes)

    assert result.blocking is False
    assert result.production_ready is True
    assert [c["pipeline_id"] for c in candidates] == ["artifact_status_flow"]


def _seed_project(project: Path) -> None:
    skill_dir = project / "skills" / "artifact_status"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "skill.json").write_text(
        json.dumps(
            {
                "name": "artifact_status",
                "display_name": "产物状态查询",
                "description": "status",
                "type": "status_report",
                "pipeline": "artifact_status_pipeline",
                "private_memory": True,
                "root": "skills/artifact_status",
            }
        ),
        encoding="utf-8",
    )
    routes_dir = project / "scheduler" / "main_scheduler"
    routes_dir.mkdir(parents=True, exist_ok=True)
    (routes_dir / "routes.json").write_text(
        json.dumps(
            {
                "pipelines": [
                    {
                        "pipeline_id": "artifact_status_flow",
                        "pipeline_name": "状态查询流程",
                        "node": "artifact_status",
                        "display_name": "产物状态查询",
                        "constraints": {"output_type": "状态报告"},
                        "supervision": {
                            "primary_expert": None,
                            "secondary_experts": [],
                        },
                        "final_output": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (project / "readiness_manifest.json").write_text(
        json.dumps(
            {
                "version": "test",
                "routes": [
                    {
                        "pipeline_id": "artifact_status_flow",
                        "readiness_state": "ready",
                        "production_ready": True,
                        "allowed_entrypoints": ["gateway", "cli"],
                        "required_skills": ["artifact_status"],
                        "output_contract": "status_report",
                        "readiness_reason": "test",
                        "owner": "test",
                    }
                ],
                "skills": [
                    {
                        "skill_id": "artifact_status",
                        "readiness_state": "ready",
                        "executable": True,
                        "executor_type": "system",
                        "production_ready": True,
                        "output_contract": "status_report",
                        "readiness_reason": "test",
                        "owner": "test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
