"""
GStack CLI adapter with graceful fallback.

CONTRACT:
- detect_gstack() uses shutil.which; never installs or downloads gstack
- run_gstack_* functions never raise; failures → GstackResult(available=False)
- All stdout/stderr pass through metrics_redaction.redact_string()
- No reads from ~/ .gstack; no writes to ~/ .gstack
- Timeout enforced via subprocess timeout parameter
- gstack CLI not found → blocked_reason set, never raises
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field

from .metrics_redaction import redact_string

GSTACK_KNOWN_COMMANDS: list[str] = [
    "plan-eng-review",
    "plan-ceo-review",
    "plan-design-review",
    "design-consultation",
    "review",
    "qa",
    "retro",
    "document-release",
    "office-hours",
]

_BLOCKED_CLI_NOT_FOUND = "gstack CLI not found at PATH — install gstack to enable real execution"


@dataclass
class GstackResult:
    available: bool
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    blocked_reason: str
    duration_ms: int
    evidence: dict = field(default_factory=dict)


def detect_gstack() -> bool:
    return shutil.which("gstack") is not None


def _gstack_command_for(phase_id: str) -> str:
    """Map phase_id to gstack CLI command."""
    try:
        from .phase_registry import get_phase
        spec = get_phase(phase_id)
        if spec and spec.gstack_command:
            return spec.gstack_command
    except Exception:  # noqa: BLE001
        pass
    # fallback: strip prefix
    return phase_id.split(".")[-1].replace("_", "-")


def _run(
    args: list[str],
    timeout: int,
    command_label: str,
) -> GstackResult:
    start = time.monotonic()
    if not detect_gstack():
        return GstackResult(
            available=False,
            command=command_label,
            exit_code=None,
            stdout="",
            stderr="",
            blocked_reason=_BLOCKED_CLI_NOT_FOUND,
            duration_ms=0,
        )
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return GstackResult(
            available=True,
            command=command_label,
            exit_code=proc.returncode,
            stdout=redact_string(proc.stdout),
            stderr=redact_string(proc.stderr),
            blocked_reason="" if proc.returncode == 0 else f"exit_code={proc.returncode}",
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        return GstackResult(
            available=True,
            command=command_label,
            exit_code=None,
            stdout="",
            stderr="",
            blocked_reason=f"timeout after {timeout}s",
            duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        return GstackResult(
            available=detect_gstack(),
            command=command_label,
            exit_code=None,
            stdout="",
            stderr="",
            blocked_reason=f"adapter error: {redact_string(str(exc))}",
            duration_ms=duration_ms,
        )


def run_gstack_dry_run(phase_id: str, timeout: int = 10) -> GstackResult:
    """Validate the command exists via --help (no side effects)."""
    cmd = _gstack_command_for(phase_id)
    return _run(["gstack", cmd, "--help"], timeout=timeout, command_label=f"gstack {cmd} --help")


def run_gstack_shadow(phase_id: str, context: dict, timeout: int = 30) -> GstackResult:
    """Shadow mode: observe only, no user-visible output change."""
    cmd = _gstack_command_for(phase_id)
    return _run(["gstack", cmd, "--dry-run"], timeout=timeout, command_label=f"gstack {cmd} --dry-run")


def run_gstack_advisory(phase_id: str, context: dict, timeout: int = 30) -> GstackResult:
    """Advisory mode: run and return suggestion text."""
    cmd = _gstack_command_for(phase_id)
    return _run(["gstack", cmd, "--advisory"], timeout=timeout, command_label=f"gstack {cmd} --advisory")


def run_gstack_controlled_execution(
    phase_id: str,
    context: dict,
    dry_run_only: bool = True,
    timeout: int = 30,
) -> GstackResult:
    """Controlled mode: MVP always uses dry_run_only=True."""
    cmd = _gstack_command_for(phase_id)
    args = ["gstack", cmd, "--dry-run"] if dry_run_only else ["gstack", cmd]
    label = f"gstack {cmd} {'--dry-run' if dry_run_only else '(controlled)'}"
    return _run(args, timeout=timeout, command_label=label)
