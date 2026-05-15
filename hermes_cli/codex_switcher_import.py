"""Codex Switcher takeover import helpers."""

from __future__ import annotations

import copy
import json
import os
import shutil
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from agent.credential_pool import AUTH_TYPE_OAUTH, PooledCredential, load_pool
from hermes_constants import get_hermes_home


TOKEN_KEYS = frozenset({
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "session_token",
    "authorization",
})

DEFAULT_CODEX_SWITCHER_PATHS = (
    Path.home() / ".codex-switcher" / "accounts.json",
)


@dataclass(frozen=True)
class CodexSwitcherAccount:
    source_file: Path
    source_account_id: str
    label: str
    auth_mode: str
    access_token: str
    refresh_token: str
    id_token: str | None
    account_id: str | None
    user_id: str | None
    expires_at: str | None
    expires_at_ms: int | None
    last_refresh: str | None
    last_used_at: str | None
    plan_type: str | None

    @property
    def has_access_token(self) -> bool:
        return bool(self.access_token)

    @property
    def has_refresh_token(self) -> bool:
        return bool(self.refresh_token)


@dataclass(frozen=True)
class CodexSwitcherImportPlan:
    source_file: Path
    accounts: list[CodexSwitcherAccount]
    existing_labels: set[str]


def _tokenish_key(key: str) -> bool:
    normalized = (key or "").strip().lower()
    return normalized in TOKEN_KEYS or "token" in normalized or normalized in {"authorization", "bearer"}


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items() if not _tokenish_key(str(k))}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def sanitize_switcher_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_value(copy.deepcopy(payload))
    if isinstance(sanitized, dict):
        sanitized["hermes_takeover_imported_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        sanitized["hermes_takeover_note"] = "token fields archived and removed after Hermes takeover import"
    return sanitized


def discover_switcher_files(extra_paths: Iterable[str | os.PathLike[str]] = ()) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for raw in [*DEFAULT_CODEX_SWITCHER_PATHS, *[Path(p) for p in extra_paths]]:
        path = raw.expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        result.append(path)
    return result


def _dict_get_nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _extract_token_bundle(account: dict[str, Any]) -> dict[str, Any]:
    auth_data = account.get("auth_data")
    if not isinstance(auth_data, dict):
        auth_data = {}
    tokens = auth_data.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
    merged = dict(tokens)
    merged.update(auth_data)
    return merged


def parse_switcher_file(path: Path) -> list[CodexSwitcherAccount]:
    payload = json.loads(path.read_text())
    raw_accounts = payload.get("accounts") if isinstance(payload, dict) else payload
    if not isinstance(raw_accounts, list):
        return []

    accounts: list[CodexSwitcherAccount] = []
    for index, raw in enumerate(raw_accounts, 1):
        if not isinstance(raw, dict):
            continue
        bundle = _extract_token_bundle(raw)
        access_token = str(bundle.get("access_token") or "").strip()
        refresh_token = str(bundle.get("refresh_token") or "").strip()
        if not access_token and not refresh_token:
            continue

        raw_label = raw.get("name") or raw.get("label") or raw.get("email") or f"codex-switcher-{index}"
        label = str(raw_label).strip() or f"codex-switcher-{index}"
        auth_mode = str(raw.get("auth_mode") or bundle.get("type") or "chatgpt").strip() or "chatgpt"
        expires_at_ms = bundle.get("expires_at_ms")
        if not isinstance(expires_at_ms, int):
            expires_at_ms = None
        account_id = bundle.get("account_id") or raw.get("id")
        user_id = bundle.get("user_id") or bundle.get("sub") or raw.get("user_id")

        accounts.append(
            CodexSwitcherAccount(
                source_file=path,
                source_account_id=str(raw.get("id") or index),
                label=label,
                auth_mode=auth_mode,
                access_token=access_token,
                refresh_token=refresh_token,
                id_token=str(bundle.get("id_token")).strip() if bundle.get("id_token") else None,
                account_id=str(account_id).strip() if account_id else None,
                user_id=str(user_id).strip() if user_id else None,
                expires_at=str(bundle.get("expires_at")).strip() if bundle.get("expires_at") else None,
                expires_at_ms=expires_at_ms,
                last_refresh=str(bundle.get("last_refresh") or raw.get("last_refresh") or "").strip() or None,
                last_used_at=str(raw.get("last_used_at") or "").strip() or None,
                plan_type=str(raw.get("plan_type") or "").strip() or None,
            )
        )
    return accounts


def build_import_plan(provider: str = "openai-codex", source: str | None = None) -> CodexSwitcherImportPlan:
    if provider != "openai-codex":
        raise ValueError("Codex Switcher import only supports provider openai-codex")
    if source:
        source_file = Path(source).expanduser()
        if not source_file.is_file():
            raise FileNotFoundError(f"Codex Switcher source file not found: {source_file}")
        files = [source_file]
    else:
        files = discover_switcher_files()
    if not files:
        raise FileNotFoundError("No Codex Switcher accounts.json file found")
    source_file = files[0]
    accounts = parse_switcher_file(source_file)
    pool = load_pool(provider)
    existing_labels = {entry.label for entry in pool.entries()}
    return CodexSwitcherImportPlan(source_file=source_file, accounts=accounts, existing_labels=existing_labels)


def account_action(account: CodexSwitcherAccount, existing_labels: set[str]) -> str:
    if not account.has_access_token or not account.has_refresh_token:
        return "skip_missing_token"
    if account.label in existing_labels:
        return "conflict"
    return "import"


def _auth_store_path() -> Path:
    return get_hermes_home() / "auth.json"


def backup_hermes_auth_store() -> Path | None:
    auth_path = _auth_store_path()
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        auth_path.parent.chmod(0o700)
    except OSError:
        pass
    if not auth_path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    backup = auth_path.with_name(f"{auth_path.name}.bak.{stamp}")
    shutil.copy2(auth_path, backup)
    try:
        auth_path.chmod(0o600)
        backup.chmod(0o600)
    except OSError:
        pass
    return backup


def _credential_from_account(account: CodexSwitcherAccount, priority: int) -> PooledCredential:
    extra = {
        "id_token": account.id_token,
        "account_id": account.account_id,
        "user_id": account.user_id,
        "auth_mode": account.auth_mode,
        "source_account_id": account.source_account_id,
        "plan_type": account.plan_type,
        "last_used_at": account.last_used_at,
    }
    return PooledCredential(
        provider="openai-codex",
        id=uuid.uuid4().hex[:8],
        label=account.label,
        auth_type=AUTH_TYPE_OAUTH,
        priority=priority,
        source="manual:codex_switcher_takeover",
        access_token=account.access_token,
        refresh_token=account.refresh_token,
        base_url="https://chatgpt.com/backend-api/codex",
        expires_at=account.expires_at,
        expires_at_ms=account.expires_at_ms,
        last_refresh=account.last_refresh,
        request_count=0,
        extra={k: v for k, v in extra.items() if v is not None},
    )


def import_switcher_accounts(plan: CodexSwitcherImportPlan) -> tuple[int, list[str], Path | None]:
    conflicts = [account.label for account in plan.accounts if account_action(account, plan.existing_labels) == "conflict"]
    if conflicts:
        raise RuntimeError("Label conflicts: " + ", ".join(conflicts))
    importable = [account for account in plan.accounts if account_action(account, plan.existing_labels) == "import"]
    if not importable:
        return 0, [], None

    backup = backup_hermes_auth_store()
    pool = load_pool("openai-codex")
    entries = pool.entries()
    next_priority = max((entry.priority for entry in entries), default=-1) + 1
    imported_labels: list[str] = []
    for offset, account in enumerate(importable):
        pool.add_entry(_credential_from_account(account, next_priority + offset))
        imported_labels.append(account.label)
    return len(imported_labels), imported_labels, backup


def archive_switcher_store(source_file: Path) -> Path:
    payload = json.loads(source_file.read_text())
    archive_dir = Path.home() / ".codex-switcher-archived"
    archive_dir.mkdir(parents=True, exist_ok=True)
    try:
        archive_dir.chmod(0o700)
    except OSError:
        pass
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    archive_path = archive_dir / f"{source_file.stem}.imported-to-hermes.{stamp}{source_file.suffix}"
    shutil.copy2(source_file, archive_path)
    sanitized = sanitize_switcher_payload(payload if isinstance(payload, dict) else {"accounts": payload})
    source_file.write_text(json.dumps(sanitized, indent=2) + "\n")
    try:
        archive_path.chmod(0o600)
        source_file.chmod(0o600)
    except OSError:
        pass
    return archive_path


def file_mode(path: Path) -> str:
    try:
        return stat.filemode(path.stat().st_mode)
    except OSError:
        return "missing"
