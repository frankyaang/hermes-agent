#!/usr/bin/env python3
"""Local smoke for ready business routes.

This smoke uses a temp agent_system project and a deterministic contract
executor. It validates Hermes runtime plumbing, audit/review files, and memory
write scope without calling external LLMs or printing secrets.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.capability_readiness import _invalidate_manifest_cache
from agent_system.hermes_sdk import HermesExpertManager, HermesSchedulerManager, HermesSkillManager
from agent_system.output_contracts import normalize_business_delegate_output
from agent_system.runtime import HermesAgentSystemRuntime


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Agent-System business routes")
    parser.add_argument("--work-dir", default="", help="Optional temp work dir to reuse")
    parser.add_argument("--keep", action="store_true", help="Keep temp work dir")
    args = parser.parse_args()

    tmp = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="hermes_business_smoke_"))
    if tmp.exists() and not args.work_dir:
        pass
    tmp.mkdir(parents=True, exist_ok=True)
    project_root = tmp / "agent_system"

    try:
        _create_project(project_root)
        source_report = project_root / "input_report.md"
        source_report.write_text("# Existing Report\n\nVOC baseline\n", encoding="utf-8")
        source_report_resolved = source_report.resolve()
        runtime = HermesAgentSystemRuntime(
            root_dir=project_root,
            skill_executor=_contract_executor(project_root),
            now_fn=lambda: datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc),
        )
        results = {}
        for pipeline_id in ("insight_flow", "dashboard_flow", "html_flow", "dashboard_from_artifact_flow"):
            run = runtime.run_pipeline(
                pipeline_id=pipeline_id,
                input_payload={"source_materials": ["VOC smoke sample", str(source_report_resolved)], "task": pipeline_id},
                human_inputs={"ops_dashboard": "人工确认使用该报告生成看板"},
                parallel=False,
            )
            results[pipeline_id] = {
                "status": run["status"],
                "audit_log_exists": Path(run["audit_log"]).exists(),
                "review_summary_exists": (project_root / "audit" / "review_summary.json").exists(),
                "artifact_paths": [
                    node.get("output", {}).get("artifact_path", "")
                    for node in run.get("results", [])
                ],
                "quality_flags_present": all(
                    node.get("node_id") == "artifact_resolver"
                    or bool(node.get("output", {}).get("quality_flags"))
                    for node in run.get("results", [])
                ),
                "artifact_input_resolved": any(
                    node.get("node_id") == "artifact_resolver"
                    and Path(str(node.get("output", {}).get("artifact_path"))).resolve() == source_report_resolved
                    for node in run.get("results", [])
                ),
            }

        failures = [
            pid
            for pid, rec in results.items()
            if rec["status"] != "completed"
            or not rec["audit_log_exists"]
            or not rec["review_summary_exists"]
            or not all(rec["artifact_paths"])
            or not rec["quality_flags_present"]
            or (pid == "dashboard_from_artifact_flow" and not rec["artifact_input_resolved"])
        ]
        payload = {
            "work_dir": str(tmp),
            "project_root": str(project_root),
            "results": results,
            "status": "ok" if not failures else "failed",
            "failed_pipelines": failures,
            "secret_redaction": "no secrets printed",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if failures else 0
    finally:
        if not args.keep and not args.work_dir:
            shutil.rmtree(tmp, ignore_errors=True)


def _create_project(root: Path) -> None:
    skill_manager = HermesSkillManager(project_name="agent_system", root_dir=root)
    for name, display_name in [
        ("voc_insight", "用户洞察"),
        ("ops_dashboard", "运营看板"),
        ("dashboard_html", "看板渲染"),
        ("audit", "核查"),
        ("briefing", "过程汇报"),
        ("artifact_resolver", "产物定位"),
    ]:
        skill_manager.create_skill(
            name=name,
            display_name=display_name,
            description=f"{display_name} Skill",
            type="analysis",
            pipeline=f"{name}_pipeline",
            private_memory=True,
        )

    expert_manager = HermesExpertManager(project_name="agent_system", root_dir=root)
    for expert_id, skill_id in [
        ("user_analyst", "voc_insight"),
        ("ops_expert", "ops_dashboard"),
        ("render_expert", "dashboard_html"),
        ("audit_expert", "audit"),
    ]:
        expert_manager.create_expert(
            name=expert_id,
            display_name=expert_id,
            description=f"{expert_id} smoke expert",
            skills=[skill_id],
            private_memory=True,
        )

    scheduler = HermesSchedulerManager(project_name="agent_system", root_dir=root)
    scheduler.create_scheduler(
        name="main_scheduler",
        display_name="主调度器",
        description="业务 route smoke",
        supervised_modules=["experts", "skills"],
        exception_handling="block_on_required_node",
        decision_logging=True,
    )
    scheduler.initialize_routes(
        scheduler_name="main_scheduler",
        pipelines=[
            _route("insight_flow", 1, "voc_insight", "用户洞察", "user_analyst"),
            _route("insight_flow", "key_node_completion", "briefing", "过程汇报", None, ["voc_insight"], optional=True, final=True),
            _route("dashboard_flow", 1, "voc_insight", "用户洞察", "user_analyst"),
            _route("dashboard_flow", 2, "ops_dashboard", "运营看板", "ops_expert", ["voc_insight"], final=True),
            _route("dashboard_flow", "key_node_completion", "briefing", "过程汇报", None, ["ops_dashboard"], optional=True),
            _route("html_flow", 1, "voc_insight", "用户洞察", "user_analyst"),
            _route("html_flow", 2, "ops_dashboard", "运营看板", "ops_expert", ["voc_insight"]),
            _route("html_flow", 3, "dashboard_html", "看板渲染", "render_expert", ["ops_dashboard"], final=True),
            _route("html_flow", "quality_gate", "audit", "核查", "audit_expert", ["dashboard_html"], optional=True),
            _route("dashboard_from_artifact_flow", 1, "artifact_resolver", "产物定位", None),
            _route(
                "dashboard_from_artifact_flow",
                2,
                "ops_dashboard",
                "运营看板",
                "ops_expert",
                ["artifact_resolver"],
                final=True,
                user_gate=True,
            ),
        ],
    )
    _write_manifest(root)


def _route(
    pipeline_id: str,
    step: int | str,
    node: str,
    display_name: str,
    primary_expert: str | None,
    depends_on: list[str] | None = None,
    *,
    optional: bool = False,
    final: bool = False,
    user_gate: bool = False,
) -> dict:
    route = {
        "pipeline_id": pipeline_id,
        "pipeline_name": pipeline_id,
        "step": step,
        "node": node,
        "display_name": display_name,
        "constraints": {"input_type": "VOC", "output_type": "artifact_path", "max_runtime": 120},
        "supervision": {
            "scheduler_monitor": True,
            "expert_required": primary_expert is not None,
            "primary_expert": primary_expert,
            "secondary_experts": [],
        },
        "user_gate": user_gate,
    }
    if depends_on:
        route["depends_on"] = depends_on
    if optional:
        route["optional"] = True
    if final:
        route["final_output"] = True
    return route


def _write_manifest(root: Path) -> None:
    skills = ["voc_insight", "ops_dashboard", "dashboard_html", "audit", "briefing"]
    routes = {
        "insight_flow": ["voc_insight", "briefing"],
        "dashboard_flow": ["voc_insight", "ops_dashboard", "briefing"],
        "html_flow": ["voc_insight", "ops_dashboard", "dashboard_html", "audit"],
        "dashboard_from_artifact_flow": ["artifact_resolver", "ops_dashboard"],
    }
    manifest = {
        "version": "1.1",
        "routes": [
            {
                "pipeline_id": pid,
                "readiness_state": "ready",
                "production_ready": True,
                "executor_type": "system+delegate_task" if pid == "dashboard_from_artifact_flow" else "delegate_task",
                "allowed_entrypoints": ["gateway", "feishu", "cli", "test"],
                "required_skills": reqs,
                "output_contract": "artifact_path, main_report_path, result_summary, quality_flags",
                "readiness_reason": "smoke manifest",
                "owner": "smoke",
                "evidence": {"local_smoke": "scripts/smoke_agent_system_business_routes.py"},
            }
            for pid, reqs in routes.items()
        ],
        "skills": [
            {
                "skill_id": sid,
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "delegate_task",
                "production_ready": True,
                "output_contract": "artifact_path, main_report_path, result_summary, quality_flags",
                "readiness_reason": "smoke manifest",
                "owner": "smoke",
                "evidence": {"local_smoke": "scripts/smoke_agent_system_business_routes.py"},
            }
            for sid in skills
        ]
        + [
            {
                "skill_id": "artifact_resolver",
                "readiness_state": "ready",
                "executable": True,
                "executor_type": "system",
                "production_ready": True,
                "output_contract": "artifact_path",
                "readiness_reason": "smoke manifest",
                "owner": "smoke",
                "evidence": {"local_smoke": "scripts/smoke_agent_system_business_routes.py"},
            }
        ],
    }
    (root / "readiness_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _invalidate_manifest_cache(root)


def _contract_executor(project_root: Path):
    def executor(context: dict) -> dict:
        skill_id = context["skill_id"]
        artifact = project_root / "smoke_artifacts" / f"{skill_id}.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f"# {skill_id}\n\nok\n", encoding="utf-8")
        output = normalize_business_delegate_output(
            skill_id=skill_id,
            output={"result_summary": f"{skill_id} smoke completed", "main_report_path": str(artifact)},
            completed=True,
            main_report_path=str(artifact),
            child_status="completed",
            api_calls=1,
            credential_status="available",
        )
        return {
            "status": "completed",
            "output_quality": 92,
            "execution_mode": "production_delegate_task",
            "output": output,
            "audit_checks": {"real_delegate_task_executed": True},
            "exceptions": [],
        }

    return executor


if __name__ == "__main__":
    raise SystemExit(main())
