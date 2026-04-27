#!/usr/bin/env python3
"""Write filesystem file information into an Obsidian vault note."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


OBSIDIAN_CONFIG = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
DEFAULT_VAULT = Path.home() / "Documents" / "Obsidian Vault"
TEXT_EXTENSIONS = {
    ".csv",
    ".env",
    ".json",
    ".log",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update an Obsidian note with metadata and preview for a file or directory."
    )
    parser.add_argument("source", help="File or directory path to document")
    parser.add_argument(
        "--vault",
        default="",
        help="Obsidian vault path. Defaults to OBSIDIAN_VAULT_PATH, active Obsidian vault, then ~/Documents/Obsidian Vault.",
    )
    parser.add_argument("--folder", default="系统文件索引", help="Folder inside the vault for generated notes")
    parser.add_argument("--title", default="", help="Note title. Defaults to the source basename")
    parser.add_argument("--max-preview-chars", type=int, default=6000, help="Maximum text preview characters")
    parser.add_argument("--max-directory-items", type=int, default=80, help="Maximum directory children to list")
    parser.add_argument("--include-content", action="store_true", help="Include full text content when it fits the preview limit")
    parser.add_argument("--no-overwrite", action="store_true", help="Fail if the note already exists")
    parser.add_argument(
        "--write-method",
        choices=("auto", "cli", "direct"),
        default="auto",
        help="auto uses Obsidian CLI when available, otherwise writes Markdown directly.",
    )
    parser.add_argument("--open", action="store_true", help="Open the created note when writing through Obsidian CLI")
    parser.add_argument("--cli-name", default="obsidian", help="Obsidian CLI executable name or path")
    return parser.parse_args()


def active_obsidian_vault() -> Path | None:
    if not OBSIDIAN_CONFIG.exists():
        return None
    try:
        payload = json.loads(OBSIDIAN_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return None
    vaults = payload.get("vaults", {})
    if not isinstance(vaults, dict):
        return None
    for entry in vaults.values():
        if isinstance(entry, dict) and entry.get("open") and entry.get("path"):
            return Path(str(entry["path"])).expanduser()
    for entry in vaults.values():
        if isinstance(entry, dict) and entry.get("path"):
            return Path(str(entry["path"])).expanduser()
    return None


def resolve_vault(value: str) -> Path:
    candidates = [
        Path(value).expanduser() if value else None,
        Path(os.environ["OBSIDIAN_VAULT_PATH"]).expanduser() if os.environ.get("OBSIDIAN_VAULT_PATH") else None,
        active_obsidian_vault(),
        DEFAULT_VAULT,
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    raise SystemExit("No Obsidian vault found. Pass --vault or set OBSIDIAN_VAULT_PATH.")


def slug_note_name(value: str) -> str:
    text = re.sub(r'[\\/:*?"<>|#\^\[\]]+', " ", value).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:120] or "系统文件"


def safe_note_relative_path(folder: str, title: str) -> Path:
    folder = folder.strip().strip("/")
    relative = Path(folder) / f"{title}.md" if folder else Path(f"{title}.md")
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise SystemExit("Folder must be a relative path inside the Obsidian vault.")
    return relative


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    return f"{size} B"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(args: list[str]) -> str:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=5)
    except Exception:
        return ""
    return (result.stdout or result.stderr or "").strip()


def is_probably_text(path: Path) -> bool:
    mime, _encoding = mimetypes.guess_type(str(path))
    return path.suffix.lower() in TEXT_EXTENSIONS or bool(mime and mime.startswith("text/"))


def read_preview(path: Path, limit: int, include_content: bool) -> tuple[str, bool]:
    if not path.is_file() or not is_probably_text(path):
        return "", False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "", False
    if include_content and len(text) <= limit:
        return text, True
    return text[:limit], len(text) <= limit


def directory_listing(path: Path, limit: int) -> list[Path]:
    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError:
        return []
    return children[:limit]


def directory_child_count(path: Path) -> int | str:
    try:
        return sum(1 for _ in path.iterdir())
    except OSError:
        return "unknown"


def yaml_quote(value: object) -> str:
    text = str(value).replace('"', '\\"')
    return f'"{text}"'


def fenced_block(text: str) -> list[str]:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [fence, text, fence]


def build_note(source: Path, vault: Path, title: str, args: argparse.Namespace) -> str:
    stat = source.stat()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
    created = datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(timespec="seconds")
    source_type = "directory" if source.is_dir() else "file"
    file_cmd = command_output(["file", "-b", str(source)])
    mime, encoding = mimetypes.guess_type(str(source))

    lines = [
        "---",
        f"title: {yaml_quote(title)}",
        "source_type: " + yaml_quote(source_type),
        "source_path: " + yaml_quote(str(source)),
        "captured_at: " + yaml_quote(now),
        "tags:",
        "  - system-file-index",
        "  - hermes",
        "---",
        "",
        f"# {title}",
        "",
        "## 基本信息",
        "",
        f"- 类型：`{source_type}`",
        f"- 路径：`{source}`",
        f"- Obsidian Vault：`{vault}`",
        f"- 大小：`{human_size(stat.st_size)}`",
        f"- 修改时间：`{modified}`",
        f"- 创建/状态变更时间：`{created}`",
    ]
    if source.is_file():
        lines.extend(
            [
                f"- SHA256：`{file_sha256(source)}`",
                f"- MIME：`{mime or 'unknown'}`",
                f"- 编码推断：`{encoding or 'unknown'}`",
                f"- file：`{file_cmd or 'unknown'}`",
            ]
        )
    else:
        lines.append(f"- 子项数量：`{directory_child_count(source)}`")

    lines.extend(["", "## 来源说明", "", "由 Hermes Obsidian 文件索引脚本从本机文件系统生成。"])

    if source.is_dir():
        children = directory_listing(source, args.max_directory_items)
        lines.extend(["", "## 目录预览", ""])
        if children:
            for child in children:
                marker = "dir" if child.is_dir() else "file"
                try:
                    size = human_size(child.stat().st_size)
                except OSError:
                    size = "unknown"
                lines.append(f"- `{marker}` `{child.name}` ({size})")
        else:
            lines.append("- 无法读取或目录为空。")
    else:
        preview, complete = read_preview(source, args.max_preview_chars, args.include_content)
        lines.extend(["", "## 文本预览", ""])
        if preview:
            suffix = "" if complete else "\n\n...（已截断）"
            lines.extend(fenced_block(preview + suffix))
        else:
            lines.append("- 文件不是可安全读取的文本格式，未写入内容预览。")

    lines.extend(["", "## 后续动作", "", "- 可在此补充人工判断、关联项目或处理结论。", ""])
    return "\n".join(lines)


def obsidian_cli_available(cli_name: str) -> str | None:
    path = shutil.which(cli_name)
    if path:
        return path
    candidate = Path(cli_name).expanduser()
    if candidate.exists() and candidate.is_file():
        return str(candidate)
    return None


def write_note_direct(note_path: Path, content: str) -> None:
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")


def write_note_with_cli(cli_path: str, vault: Path, relative_path: Path, content: str, overwrite: bool, open_note: bool) -> None:
    args = [
        cli_path,
        "create",
        f"path={relative_path.as_posix()}",
        f"content={content}",
    ]
    if overwrite:
        args.append("overwrite")
    if open_note:
        args.append("open")
    result = subprocess.run(args, cwd=str(vault), capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or f"Obsidian CLI exited with code {result.returncode}")


def main() -> None:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Source path does not exist: {source}")
    vault = resolve_vault(args.vault)
    title = slug_note_name(args.title or source.name)
    relative_path = safe_note_relative_path(args.folder, title)
    note_path = vault / relative_path
    if args.no_overwrite and note_path.exists():
        raise SystemExit(f"Note already exists: {note_path}")
    content = build_note(source, vault, title, args)
    cli_path = obsidian_cli_available(args.cli_name)
    if args.write_method in {"auto", "cli"} and cli_path:
        try:
            write_note_with_cli(cli_path, vault, relative_path, content, not args.no_overwrite, args.open)
        except Exception as exc:
            if args.write_method == "cli":
                raise SystemExit(f"Obsidian CLI write failed: {exc}") from exc
            print(f"Obsidian CLI write failed, falling back to direct Markdown write: {exc}", file=sys.stderr)
            write_note_direct(note_path, content)
    elif args.write_method == "cli":
        raise SystemExit("Obsidian CLI not found. Enable it in Obsidian Settings > General or use --write-method direct.")
    else:
        write_note_direct(note_path, content)
    print(note_path)


if __name__ == "__main__":
    main()
