import json
from types import SimpleNamespace

from agent.credential_pool import load_pool
from hermes_cli.auth_commands import auth_import_codex_switcher_command
from hermes_cli.codex_switcher_import import (
    archive_switcher_store,
    build_import_plan,
    import_switcher_accounts,
    sanitize_switcher_payload,
)


def _write_switcher(path):
    payload = {
        "version": 1,
        "accounts": [
            {
                "id": "acct-1",
                "name": "codex-main",
                "email": "main@example.com",
                "auth_mode": "chatgpt",
                "plan_type": "plus",
                "last_used_at": "2026-05-06T00:00:00Z",
                "auth_data": {
                    "type": "chatgpt",
                    "account_id": "chatgpt-account-1",
                    "access_token": "access.secret.one",
                    "refresh_token": "refresh.secret.one",
                    "id_token": "id.secret.one",
                },
            },
            {
                "id": "acct-2",
                "name": "codex-backup",
                "auth_mode": "chatgpt",
                "auth_data": {
                    "access_token": "access.secret.two",
                    "refresh_token": "refresh.secret.two",
                },
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return payload


def test_sanitize_switcher_payload_removes_token_fields():
    payload = {
        "accounts": [
            {
                "name": "codex-main",
                "auth_data": {
                    "access_token": "access.secret",
                    "refresh_token": "refresh.secret",
                    "id_token": "id.secret",
                    "account_id": "acct",
                },
            }
        ]
    }

    sanitized = sanitize_switcher_payload(payload)
    text = json.dumps(sanitized)

    assert "access.secret" not in text
    assert "refresh.secret" not in text
    assert "id.secret" not in text
    assert "codex-main" in text
    assert "acct" in text


def test_import_switcher_accounts_rebuilds_hermes_metadata(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    source = tmp_path / ".codex-switcher" / "accounts.json"
    _write_switcher(source)

    plan = build_import_plan(source=str(source))
    count, labels, backup = import_switcher_accounts(plan)

    assert count == 2
    assert labels == ["codex-main", "codex-backup"]
    assert backup is None
    pool = load_pool("openai-codex")
    entries = pool.entries()
    assert [entry.label for entry in entries] == labels
    assert all(entry.auth_type == "oauth" for entry in entries)
    assert all(entry.source == "manual:codex_switcher_takeover" for entry in entries)
    assert all(entry.request_count == 0 for entry in entries)
    assert all(entry.last_status is None for entry in entries)
    assert entries[0].id_token == "id.secret.one"
    assert entries[0].account_id == "chatgpt-account-1"


def test_archive_switcher_store_keeps_metadata_but_removes_source_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    source = tmp_path / ".codex-switcher" / "accounts.json"
    _write_switcher(source)

    archive = archive_switcher_store(source)

    archived_text = archive.read_text()
    source_text = source.read_text()
    assert "access.secret.one" in archived_text
    assert "refresh.secret.one" in archived_text
    assert "access.secret.one" not in source_text
    assert "refresh.secret.one" not in source_text
    assert "codex-main" in source_text


def test_dry_run_output_never_prints_tokens(tmp_path, monkeypatch, capsys):
    hermes_home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    source = tmp_path / ".codex-switcher" / "accounts.json"
    _write_switcher(source)

    auth_import_codex_switcher_command(
        SimpleNamespace(
            provider="openai-codex",
            mode="takeover",
            dry_run=True,
            source=str(source),
        )
    )
    output = capsys.readouterr().out

    assert "codex-main" in output
    assert "has_access_token: true" in output
    assert "has_refresh_token: true" in output
    assert "access.secret" not in output
    assert "refresh.secret" not in output
    assert "id.secret" not in output
