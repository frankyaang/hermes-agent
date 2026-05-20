"""Tests for preflight_agent_system_upgrade.py — upgrade hard gate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_SCRIPT = ROOT / "scripts" / "preflight_agent_system_upgrade.py"


def _run_preflight(*extra_args: str, hermes_home: str | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(PREFLIGHT_SCRIPT)]
    if hermes_home:
        cmd += ["--hermes-home", hermes_home]
    cmd += list(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


def _blocked_report(missing_codes: list[str] | None = None) -> dict:
    """Build a minimal report where upgrade_allowed=False."""
    missing = [
        {"failure_code": code, "reason": f"reason for {code}", "detail": "detail"}
        for code in (missing_codes or ["gateway_smoke_missing"])
    ]
    return {
        "overall_status": "local_ready_not_operationally_verified",
        "primary_blocker_status": "gateway_smoke_incomplete",
        "upgrade_allowed": False,
        "missing_evidence": missing,
        "next_required_actions": ["Run gateway smoke"],
        "gateway_smoke": {"completed_count": 0, "required_count": 7},
        "run_evidence": {"count": 0},
        "operational_evidence": {"event_count": 5},
        "gstack": {"adapter_available": False},
    }


def _passing_report() -> dict:
    """Build a minimal report where upgrade_allowed=True."""
    return {
        "overall_status": "production_ready",
        "primary_blocker_status": "",
        "upgrade_allowed": True,
        "missing_evidence": [],
        "next_required_actions": [],
        "gateway_smoke": {"completed_count": 7, "required_count": 7},
        "run_evidence": {"count": 10},
        "operational_evidence": {"event_count": 55},
        "gstack": {"adapter_available": True},
    }


# ---------------------------------------------------------------------------
# Import-level tests
# ---------------------------------------------------------------------------

def test_preflight_exits_nonzero_when_upgrade_blocked(tmp_path: Path) -> None:
    """upgrade_allowed=false must cause exit code 1."""
    result = _run_preflight(
        "--hermes-home", str(tmp_path),
        "--repo-root", str(ROOT),
    )
    assert result.returncode == 1, (
        f"Expected exit 1 when upgrade_allowed=false, got {result.returncode}. "
        f"stdout={result.stdout[:300]}"
    )


def test_preflight_prints_upgrade_allowed_false(tmp_path: Path) -> None:
    """Output must explicitly state upgrade_allowed=False."""
    result = _run_preflight("--hermes-home", str(tmp_path), "--repo-root", str(ROOT))
    combined = result.stdout + result.stderr
    assert "upgrade_allowed" in combined.lower() or "PREFLIGHT FAILED" in combined


def test_preflight_no_secrets_in_output(tmp_path: Path) -> None:
    """Preflight output must never contain token/key/Bearer patterns."""
    result = _run_preflight("--hermes-home", str(tmp_path), "--repo-root", str(ROOT))
    combined = result.stdout + result.stderr
    for marker in ("Bearer ", "access_token=", "api_key=", "sk-", "Authorization:"):
        assert marker not in combined, f"Secret marker '{marker}' found in preflight output"


def test_preflight_json_mode_contains_required_fields(tmp_path: Path) -> None:
    """--json mode must output parseable JSON with upgrade_allowed field."""
    result = _run_preflight(
        "--hermes-home", str(tmp_path),
        "--repo-root", str(ROOT),
        "--json",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "upgrade_allowed" in payload
    assert payload["upgrade_allowed"] is False
    assert "overall_status" in payload
    assert "primary_blocker_status" in payload
    assert "missing_evidence" in payload
    assert "next_required_actions" in payload


# ---------------------------------------------------------------------------
# Unit-level tests using mocked build_status_report
# ---------------------------------------------------------------------------

def test_preflight_returns_zero_when_upgrade_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """upgrade_allowed=true must cause exit code 0."""
    import scripts.preflight_agent_system_upgrade as mod
    monkeypatch.setattr(
        "agent_system.status_report.build_status_report",
        lambda **_kw: _passing_report(),
    )
    monkeypatch.setattr(mod, "build_status_report", lambda **_kw: _passing_report())
    result = mod.main.__func__ if hasattr(mod.main, "__func__") else None
    # Call via the main() function after patching
    sys.argv = [
        str(PREFLIGHT_SCRIPT),
        "--hermes-home", str(tmp_path),
        "--repo-root", str(ROOT),
    ]
    with patch.object(
        sys.modules.get("agent_system.status_report", MagicMock()),
        "build_status_report",
        return_value=_passing_report(),
    ):
        import importlib
        import scripts.preflight_agent_system_upgrade as fresh
        importlib.reload(fresh)
        with patch.object(fresh, "build_status_report", return_value=_passing_report()):
            code = fresh.main()
    assert code == 0, f"Expected 0 when upgrade_allowed=true, got {code}"


def test_preflight_returns_one_when_upgrade_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """upgrade_allowed=false must cause main() to return 1."""
    import importlib
    import scripts.preflight_agent_system_upgrade as fresh
    importlib.reload(fresh)
    sys.argv = [
        str(PREFLIGHT_SCRIPT),
        "--hermes-home", str(tmp_path),
        "--repo-root", str(ROOT),
    ]
    with patch.object(fresh, "build_status_report", return_value=_blocked_report()):
        code = fresh.main()
    assert code == 1, f"Expected 1 when upgrade_allowed=false, got {code}"


def test_preflight_lists_missing_evidence_codes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """Output must include the failure codes from missing_evidence."""
    import importlib
    import scripts.preflight_agent_system_upgrade as fresh
    importlib.reload(fresh)
    codes = ["gateway_smoke_missing", "insufficient_memory_events"]
    sys.argv = [
        str(PREFLIGHT_SCRIPT),
        "--hermes-home", str(tmp_path),
        "--repo-root", str(ROOT),
    ]
    with patch.object(fresh, "build_status_report", return_value=_blocked_report(codes)):
        fresh.main()
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    for code in codes:
        assert code in combined, f"Missing failure_code '{code}' in preflight output"


def test_preflight_handles_build_error_gracefully(tmp_path: Path) -> None:
    """If build_status_report raises, preflight exits with code 2."""
    import importlib
    import scripts.preflight_agent_system_upgrade as fresh
    importlib.reload(fresh)
    sys.argv = [
        str(PREFLIGHT_SCRIPT),
        "--hermes-home", str(tmp_path),
        "--repo-root", str(ROOT),
    ]

    def _raise(**_kw):
        raise RuntimeError("simulated build failure")

    with patch.object(fresh, "build_status_report", side_effect=_raise):
        code = fresh.main()
    assert code == 2, f"Expected exit 2 on build error, got {code}"
