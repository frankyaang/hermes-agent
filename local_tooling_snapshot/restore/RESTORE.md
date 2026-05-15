# Restore Guide For Hermes Upgrade Failures

Snapshot generated: 2026-05-14T23:05:41

## GitHub Snapshot

- Repository: `https://github.com/frankyaang/hermes-agent`
- Branch: `snapshot/hermes-local-20260514-224006`
- Base code release: `v2026.5.14`
- Tooling snapshot tag: `v2026.5.14.1` (created after this commit is pushed)

## Fast Restore Hermes Code

```bash
cd /Users/frank/.hermes/hermes-agent-official
git fetch fork --tags
git switch snapshot/hermes-local-20260514-224006
git reset --hard fork/snapshot/hermes-local-20260514-224006
```

If the checkout is broken beyond repair:

```bash
mv /Users/frank/.hermes/hermes-agent-official /Users/frank/.hermes/hermes-agent-official.broken.$(date +%Y%m%d-%H%M%S)
git clone https://github.com/frankyaang/hermes-agent.git /Users/frank/.hermes/hermes-agent-official
cd /Users/frank/.hermes/hermes-agent-official
git switch snapshot/hermes-local-20260514-224006
```

## Restore Local Tooling Configs

These files are redacted snapshots for reference. They intentionally do not contain auth tokens.

- Claude settings: `local_tooling_snapshot/claude/*.redacted`
- Claude pipeline command: `local_tooling_snapshot/claude/commands/pipeline.md`
- Codex config reference: `local_tooling_snapshot/codex/config.redacted.toml`
- Codex inventory: `local_tooling_snapshot/codex/inventory.md`
- Codex Switcher inventory: `local_tooling_snapshot/switcher/inventory.md`
- npm global AI tools: `local_tooling_snapshot/npm/global-ai-tools.md`

Do not restore `~/.codex/auth.json`, Codex Switcher account stores, or Claude/Codex session caches from GitHub. Re-login locally if credentials break.

## Restart Gateway After Restore

```bash
hermes gateway restart
hermes gateway status
```

If launchd needs a direct nudge on macOS:

```bash
launchctl kickstart -k gui/$(id -u)/ai.hermes.gateway
```
