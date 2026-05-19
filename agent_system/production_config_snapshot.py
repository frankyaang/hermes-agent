from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent_system.failure_taxonomy import CONFIG_SECRET_DETECTED
from agent_system.run_evidence import evidence_dir, redact


CONFIG_SNAPSHOT_FILENAME = "production_config_snapshot.json"

_SECRET_KEYS = {
    "api_key",
    "access_token",
    "refresh_token",
    "id_token",
    "authorization",
    "bearer",
    "password",
    "secret",
    "token",
}

_SECRET_KEY_MARKERS = (
    "api",
    "auth",
    "private",
    "client",
    "access",
    "refresh",
    "session",
)

_SECRET_VALUE_MARKERS = (
    "sk-",
    "bearer ",
    "access_token",
    "refresh_token",
    "authorization:",
)


def config_snapshot_path(hermes_home: Path) -> Path:
    return evidence_dir(hermes_home) / CONFIG_SNAPSHOT_FILENAME


def build_production_config_snapshot(
    *,
    hermes_home: Path,
    repo_root: Path,
    config_path: Path | None = None,
) -> dict[str, Any]:
    hermes_home = Path(hermes_home).expanduser()
    repo_root = Path(repo_root)
    config_path = Path(config_path).expanduser() if config_path else hermes_home / "config.yaml"
    raw = _read_yaml(config_path)
    detected_paths = _detect_secret_paths(raw)
    snapshot = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hermes_home": str(hermes_home),
        "config_path": str(config_path),
        "git": _git_info(repo_root),
        "model": redact(raw.get("model") or {}),
        "agent": redact(_pick(raw.get("agent") or {}, ["reasoning_effort", "max_turns", "api_max_retries"])),
        "delegation": redact(_pick(raw.get("delegation") or {}, [
            "provider", "model", "base_url", "max_iterations",
            "reasoning_effort", "max_concurrent_children", "max_spawn_depth",
        ])),
        "agent_system": redact(raw.get("agent_system") or {}),
        "fallback_providers": redact(raw.get("fallback_providers") or []),
        "credential_pool_strategies": redact(raw.get("credential_pool_strategies") or {}),
        "providers": _provider_summary(raw.get("providers") or {}),
        "gateway": {
            "configured_platforms": _configured_platforms(raw),
            "observed_env_platforms": _observed_env_platforms(),
        },
        "sedimentation_flags": {
            "SESSION_CAPTURE_AUTO_ENABLED": os.getenv("SESSION_CAPTURE_AUTO_ENABLED", ""),
            "USAGE_HINT_INJECTION_ENABLED": os.getenv("USAGE_HINT_INJECTION_ENABLED", ""),
            "GSTACK_SEDIMENTATION_ENABLED": os.getenv("GSTACK_SEDIMENTATION_ENABLED", ""),
        },
        "secret_hygiene": {
            "config_secret_detected": bool(detected_paths),
            "failure_code": CONFIG_SECRET_DETECTED if detected_paths else "",
            "detected_paths": detected_paths,
            "policy": "snapshot redacts values; do not migrate automatically",
        },
    }
    return snapshot


def write_production_config_snapshot(
    *,
    hermes_home: Path,
    repo_root: Path,
    config_path: Path | None = None,
) -> Path:
    snapshot = build_production_config_snapshot(
        hermes_home=hermes_home,
        repo_root=repo_root,
        config_path=config_path,
    )
    path = config_snapshot_path(hermes_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_production_config_snapshot(hermes_home: Path) -> dict[str, Any] | None:
    path = config_snapshot_path(hermes_home)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _pick(payload: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: payload.get(key) for key in keys if key in payload}


def _provider_summary(providers: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, payload in providers.items():
        if not isinstance(payload, dict):
            continue
        summary[str(name)] = {
            "base_url": payload.get("base_url", ""),
            "api_mode": payload.get("api_mode", ""),
            "has_api_key": bool(payload.get("api_key")),
        }
    return redact(summary)


def _configured_platforms(raw: dict[str, Any]) -> list[str]:
    platform_names = [
        "telegram", "discord", "slack", "whatsapp", "mattermost",
        "feishu", "wecom", "dingtalk", "qqbot", "webhook", "api_server",
    ]
    configured = []
    for name in platform_names:
        value = raw.get(name)
        if isinstance(value, dict) and any(bool(v) for v in value.values()):
            configured.append(name)
    return configured


def _observed_env_platforms() -> list[str]:
    enabled = []
    for name, env_name in {
        "feishu": "FEISHU_APP_ID",
        "telegram": "TELEGRAM_BOT_TOKEN",
        "slack": "SLACK_BOT_TOKEN",
        "discord": "DISCORD_BOT_TOKEN",
    }.items():
        if os.getenv(env_name):
            enabled.append(name)
    return enabled


def _detect_secret_paths(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            key_lower = str(key).lower()
            if _is_secret_key(key_lower) and _has_secret_value(item):
                findings.append(child_path)
            findings.extend(_detect_secret_paths(item, child_path))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            findings.extend(_detect_secret_paths(item, f"{path}[{idx}]"))
    elif isinstance(value, str) and _string_has_secret_marker(value):
        findings.append(path or "<string>")
    return list(dict.fromkeys(findings))


def _is_secret_key(key: str) -> bool:
    if key in _SECRET_KEYS:
        return True
    if "secret" in key or "password" in key or "authorization" in key:
        return True
    if key.endswith("_token"):
        return True
    if key.endswith("_key") and any(marker in key for marker in _SECRET_KEY_MARKERS):
        return True
    return False


def _has_secret_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_has_secret_marker(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in _SECRET_VALUE_MARKERS)


def _git_info(repo_root: Path) -> dict[str, str]:
    return {
        "branch": _git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": _git(repo_root, ["rev-parse", "HEAD"]),
    }


def _git(repo_root: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""
