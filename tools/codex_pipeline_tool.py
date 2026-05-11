#!/usr/bin/env python3
"""
Codex Pipeline Tool

Runs a three-stage Plan→Execute→Audit pipeline for complex coding tasks:
  1. Plan   : Claude Opus 4.7 decomposes the requirement into structured tasks (JSON)
  2. Execute : Codex CLI (gpt-5.5, xhigh reasoning) executes each task serially
  3. Audit  : Codex CLI (gpt-5.5, high reasoning) reviews results and returns PASS/FAIL

Up to 3 automatic retry cycles if the audit fails. On PASS the tool returns the
audit report and the path to all run artifacts. On final FAIL it returns the last
audit report with failure details.
"""

import json
import os
import subprocess
from pathlib import Path

from tools.registry import registry, tool_error, tool_result

PIPELINE_SCRIPT = Path.home() / "pipeline" / "pipeline.sh"

CODEX_PIPELINE_SCHEMA = {
    "name": "codex_pipeline",
    "description": (
        "Run a Plan→Execute→Audit pipeline for a coding task. "
        "Claude Opus 4.7 plans the work; Codex CLI executes each task serially "
        "inside the target directory; Codex audits the results. "
        "Use this for multi-step coding tasks that require writing, modifying, or "
        "testing code in a project directory. "
        "Returns the audit report (PASS/FAIL), a summary, any issues found, "
        "and the path to all run artifacts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "requirement": {
                "type": "string",
                "description": (
                    "Natural language description of what needs to be built or fixed. "
                    "Be specific: include file names, function names, expected behaviour, "
                    "and any constraints."
                ),
            },
            "target_dir": {
                "type": "string",
                "description": (
                    "Absolute path to the project directory where Codex will read/write files. "
                    "Defaults to the current working directory if omitted."
                ),
            },
        },
        "required": ["requirement"],
    },
}


def check_codex_pipeline_requirements() -> bool:
    """Return True when both claude and codex CLIs are on PATH and pipeline.sh exists."""
    import shutil
    return (
        PIPELINE_SCRIPT.exists()
        and shutil.which("claude") is not None
        and shutil.which("codex") is not None
    )


def _refresh_codex_auth() -> None:
    """Run codex login in the main process (has TTY/browser access) before shelling out."""
    try:
        subprocess.run(
            ["codex", "login"],
            timeout=60,
            check=False,
            capture_output=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # best-effort; codex exec will surface any real auth error


def _run_pipeline(requirement: str, target_dir: str) -> dict:
    _refresh_codex_auth()
    cmd = ["bash", str(PIPELINE_SCRIPT), requirement, target_dir]
    env = {**os.environ}

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )

    output = proc.stdout + proc.stderr

    # Locate the run directory from the log output
    run_dir = None
    for line in output.splitlines():
        if "Artifacts" in line and "/pipeline/runs/" in line:
            parts = line.split()
            for part in parts:
                if "/pipeline/runs/" in part:
                    run_dir = part.strip()
                    break
        if run_dir:
            break

    # Parse the audit report from the run directory
    audit_data = {}
    if run_dir:
        run_path = Path(run_dir)
        # Find the last extracted audit file (exclude audit_raw_*.json)
        audit_files = sorted(f for f in run_path.glob("audit_*.json") if "_raw_" not in f.name)
        if audit_files:
            try:
                audit_data = json.loads(audit_files[-1].read_text())
            except (json.JSONDecodeError, OSError):
                pass

    passed = proc.returncode == 0 and audit_data.get("status") == "PASS"

    return {
        "status": "PASS" if passed else "FAIL",
        "run_dir": run_dir,
        "audit": audit_data,
        "pipeline_log": output[-4000:] if len(output) > 4000 else output,
    }


def handle_codex_pipeline(args: dict, **_kw) -> str:
    requirement = (args.get("requirement") or "").strip()
    if not requirement:
        return tool_error("requirement is required and must not be empty")

    target_dir = (args.get("target_dir") or "").strip()
    if not target_dir:
        target_dir = str(Path.cwd())

    target_path = Path(target_dir)
    if not target_path.exists():
        return tool_error(f"target_dir does not exist: {target_dir}")

    if not check_codex_pipeline_requirements():
        return tool_error(
            "Pipeline prerequisites missing: ensure pipeline.sh exists at "
            f"{PIPELINE_SCRIPT} and both 'claude' and 'codex' are on PATH"
        )

    try:
        result = _run_pipeline(requirement, str(target_path.resolve()))
        return tool_result(result)
    except subprocess.TimeoutExpired:
        return tool_error("Pipeline timed out after 600 seconds")
    except Exception as exc:
        return tool_error(f"Pipeline failed with unexpected error: {exc}")


registry.register(
    name="codex_pipeline",
    toolset="codex-pipeline",
    schema=CODEX_PIPELINE_SCHEMA,
    handler=handle_codex_pipeline,
    check_fn=check_codex_pipeline_requirements,
    emoji="🔁",
)
