# Local Hermes Install Snapshot

Captured on 2026-05-14 before upgrading the local Hermes installation.

## Installed Project

- Project checkout: `/Users/frank/.hermes/hermes-agent-official`
- Hermes CLI symlink: `/Users/frank/.local/bin/hermes -> /Users/frank/.hermes/hermes-agent-official/venv/bin/hermes`
- Active gateway service: `ai.hermes.gateway`
- Gateway LaunchAgent: `/Users/frank/Library/LaunchAgents/ai.hermes.gateway.plist`
- Gateway command:

```text
/Users/frank/.hermes/hermes-agent-official/venv/bin/python -m hermes_cli.main gateway run --replace
```

## Included Invocation Scripts

- `bin/claude-pipeline`: copy of `/Users/frank/.local/bin/claude-pipeline`
- `pipeline/pipeline.sh`: copy of `/Users/frank/pipeline/pipeline.sh`
- `pipeline/config.env`: copy of `/Users/frank/pipeline/config.env`
- `pipeline/audit_schema.json`: copy of `/Users/frank/pipeline/audit_schema.json`
- `launchd/ai.hermes.gateway.plist`: copy of the Hermes Gateway LaunchAgent

## Usage Notes

`claude-pipeline` routes work through:

```text
Plan  = claude-opus-4-7
Exec  = gpt-5.5
Audit = gpt-5.5
```

The copied pipeline config contains model names and routing settings only. Runtime auth stores, API keys, OAuth token files, and Hermes `.env` files are intentionally not copied here.
