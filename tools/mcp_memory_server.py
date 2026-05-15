"""
Hermes Memory MCP Server (stdio).

Exposes Hermes' file-based memory (MEMORY.md / USER.md) to Claude Code over MCP
as three read-only tools:

  - search_memory: keyword search over MEMORY.md + USER.md entries
  - list_recent_memory: list the most recent N entries from a target file
  - get_user_profile: return the full USER.md content

Backend: reads `~/.hermes/memories/{MEMORY,USER}.md`, where entries are separated
by a single `§` line. SQLite-backed retrieval can be added later by swapping the
`_load_entries` implementation.

Run: python3 tools/mcp_memory_server.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

MEMORY_DIR = Path(os.environ.get("HERMES_MEMORY_DIR", str(Path.home() / ".hermes" / "memories")))

server = Server("hermes-memory")


def _load_entries(target: str) -> List[str]:
    """Load entries from MEMORY.md or USER.md, split on `§`."""
    name = "USER.md" if target == "user" else "MEMORY.md"
    path = MEMORY_DIR / name
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    parts = [p.strip() for p in raw.split("\n§\n")]
    return [p for p in parts if p]


def _format_hits(hits: List[tuple[int, str, str]]) -> str:
    """Format (idx, target, content) hits as a numbered list."""
    if not hits:
        return "No matching memory entries found."
    lines = [f"Found {len(hits)} matching entries:\n"]
    for i, (idx, target, content) in enumerate(hits, 1):
        lines.append(f"### {i}. [{target}#{idx}]")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_memory",
            description=(
                "Search Hermes long-term memory (MEMORY.md + USER.md) for entries "
                "containing all of the given keywords (case-insensitive substring match). "
                "Use this to recall prior conversations, user preferences, project facts, "
                "or operational decisions persisted by the Hermes agent system."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms; whitespace-separated keywords are AND-combined.",
                    },
                    "target": {
                        "type": "string",
                        "enum": ["all", "memory", "user"],
                        "description": "Which file to search. 'memory'=MEMORY.md, 'user'=USER.md, 'all'=both.",
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of entries to return (default 10).",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_recent_memory",
            description=(
                "List the most recent N entries from MEMORY.md or USER.md without filtering. "
                "Useful for getting a quick overview of what Hermes recently remembered."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["memory", "user"],
                        "description": "Which file to list from.",
                        "default": "memory",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of entries to return (default 10).",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
            },
        ),
        Tool(
            name="get_user_profile",
            description=(
                "Return the full USER.md content — Hermes' compact user profile "
                "(preferences, role, communication style)."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "search_memory":
        query = (arguments.get("query") or "").strip()
        target = arguments.get("target", "all")
        limit = int(arguments.get("limit", 10))
        if not query:
            return [TextContent(type="text", text="Empty query.")]
        keywords = [k.lower() for k in query.split() if k]
        sources: list[tuple[str, list[str]]] = []
        if target in ("all", "memory"):
            sources.append(("memory", _load_entries("memory")))
        if target in ("all", "user"):
            sources.append(("user", _load_entries("user")))

        hits: list[tuple[int, str, str]] = []
        for tgt, entries in sources:
            for idx, entry in enumerate(entries):
                lower = entry.lower()
                if all(k in lower for k in keywords):
                    hits.append((idx, tgt, entry))
                    if len(hits) >= limit:
                        break
            if len(hits) >= limit:
                break
        return [TextContent(type="text", text=_format_hits(hits))]

    if name == "list_recent_memory":
        target = arguments.get("target", "memory")
        limit = int(arguments.get("limit", 10))
        entries = _load_entries(target)
        recent = list(enumerate(entries))[-limit:]
        recent.reverse()
        hits = [(idx, target, content) for idx, content in recent]
        return [TextContent(type="text", text=_format_hits(hits))]

    if name == "get_user_profile":
        entries = _load_entries("user")
        if not entries:
            return [TextContent(type="text", text="USER.md is empty or missing.")]
        body = "\n\n§\n\n".join(entries)
        return [TextContent(type="text", text=f"# Hermes USER profile\n\n{body}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
