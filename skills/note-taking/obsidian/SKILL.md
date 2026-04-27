---
name: obsidian
description: Read, search, and create notes in the Obsidian vault.
---

# Obsidian Vault

Use this skill when the user wants Hermes to read, search, or write Markdown notes in an Obsidian vault, including turning filesystem file or directory metadata into an Obsidian note.

## Vault Resolution

Resolve the vault in this order:

1. Explicit path supplied by the user.
2. `OBSIDIAN_VAULT_PATH` environment variable, for example in `~/.hermes/.env`.
3. The currently open vault recorded by Obsidian Desktop on macOS.
4. `~/Documents/Obsidian Vault`.

Vault paths may contain spaces. Always quote shell variables and paths.

## Obsidian CLI

Official CLI docs: https://obsidian.md/help/cli

Obsidian CLI is available only after Obsidian Desktop 1.12+ is installed and the CLI is enabled in Obsidian settings. The command name is normally `obsidian`.

Useful official patterns:

```bash
obsidian open
obsidian create path="Folder/Note.md" content="Markdown content" overwrite
obsidian create path="Folder/Note.md" content="Markdown content" overwrite open
```

When running from inside a vault directory, Obsidian CLI targets that vault by default. If the CLI is not installed or enabled, operate on the vault as normal Markdown files.

## Read a note

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
cat "$VAULT/Note Name.md"
```

## List notes

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

# All notes
find "$VAULT" -name "*.md" -type f

# In a specific folder
ls "$VAULT/Subfolder/"
```

## Search

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

# By filename
find "$VAULT" -name "*.md" -iname "*keyword*"

# By content
grep -rli "keyword" "$VAULT" --include="*.md"
```

## Write System File Information

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
python3 "$HERMES_HOME/skills/note-taking/obsidian/scripts/file_to_obsidian.py" "/path/to/file-or-directory"
```

The helper creates a Markdown note in the vault folder `系统文件索引` by default. It records:

- Source path, type, size, timestamps, MIME/file detection, and SHA256 for files.
- Text preview for safe text files.
- Directory child preview for directories.
- YAML frontmatter with `system-file-index` and `hermes` tags.

The helper writes by `--write-method auto`:

- If official `obsidian` CLI is available, it uses `obsidian create`.
- If CLI is unavailable, it writes the Markdown note directly into the vault.

Common options:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

python3 "$HERMES_HOME/skills/note-taking/obsidian/scripts/file_to_obsidian.py" "/path/to/file" \
  --title "Readable Note Title" \
  --folder "系统文件索引" \
  --open

python3 "$HERMES_HOME/skills/note-taking/obsidian/scripts/file_to_obsidian.py" "/path/to/dir" \
  --max-directory-items 120 \
  --write-method direct
```

Use `--vault "/path/to/vault"` when the target vault is not the active Obsidian vault or `OBSIDIAN_VAULT_PATH`.

## Create Or Append Notes Directly

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
printf '%s\n' '# Title' '' 'Content here.' > "$VAULT/New Note.md"
printf '%s\n' '' 'New content here.' >> "$VAULT/Existing Note.md"
```

## Wikilinks

Obsidian links notes with `[[Note Name]]` syntax. When creating notes, use these to link related content.
