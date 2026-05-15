# Local Tooling Snapshot

This directory captures non-secret restore information for external tooling used around Hermes.

Included:

- Claude Code settings and `/pipeline` slash command, redacted
- Codex config and inventory, redacted
- Codex Switcher / cc-switch inventory, no account database contents
- Global Claude/Codex npm package versions
- Restore guide for upgrade failures

Excluded by design:

- `~/.codex/auth.json`
- `~/.codex` sessions, state DBs, caches, and logs
- `~/.claude` sessions, projects, paste cache, and session env
- `~/.cc-switch/cc-switch.db` contents
- `~/.codex-switcher` account JSON contents
- Any API keys, OAuth tokens, cookies, private keys, or bearer tokens
