"""
Working Memory - Session-scoped mutable memory overlay.

This module provides immediate memory visibility within a session without
invalidating the cached system prompt. Memories written during a session
are immediately available in subsequent turns via dynamic context injection.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import time
import json


@dataclass
class MemoryEntry:
    """A single memory entry in working memory."""
    content: str
    memory_type: str  # 'user_profile' | 'preference' | 'fact' | 'experience' | 'project' | 'task' | 'session'
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "memory_type": self.memory_type,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """Create from dictionary."""
        return cls(
            content=data["content"],
            memory_type=data["memory_type"],
            confidence=data.get("confidence", 1.0),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {})
        )


@dataclass
class WorkingMemory:
    """
    Session-scoped mutable memory overlay.

    Provides immediate visibility of memories written during the current session
    without requiring system prompt regeneration. Memories are injected dynamically
    into each LLM call as an ephemeral context block.

    Lifecycle:
    - Created at session start
    - Accumulates memories during session
    - Cleared at session end (after optional persistence)
    """

    session_id: str
    user_id: str
    channel_id: Optional[str] = None

    # Memories written during this session (immediately visible)
    pending_writes: List[MemoryEntry] = field(default_factory=list)

    # Current turn number (for temporal context)
    current_turn: int = 0

    # Maximum entries to keep in working memory
    max_entries: int = 20

    def add_pending(self, entry: MemoryEntry):
        """
        Add a memory to working memory.

        The memory becomes immediately visible in subsequent turns within
        this session, without waiting for system prompt regeneration.

        Args:
            entry: The memory entry to add
        """
        self.pending_writes.append(entry)

        # Enforce max entries (FIFO eviction)
        if len(self.pending_writes) > self.max_entries:
            self.pending_writes.pop(0)

    def get_visible_memories(self) -> List[MemoryEntry]:
        """
        Get all memories visible in the current session.

        Returns:
            List of memory entries, ordered by creation time (oldest first)
        """
        return self.pending_writes.copy()

    def format_for_context(self) -> str:
        """
        Format working memory as a text block for LLM context injection.

        Returns:
            Formatted string suitable for system message, or empty string if no memories
        """
        if not self.pending_writes:
            return ""

        lines = [
            "# Working Memory (Current Session)",
            "",
            "The following information was learned during this session:",
            ""
        ]

        for entry in self.pending_writes:
            # Format: [type] content
            lines.append(f"- [{entry.memory_type}] {entry.content}")

            # Add confidence indicator for low-confidence memories
            if entry.confidence < 1.0:
                lines.append(f"  (confidence: {entry.confidence:.2f})")

        return "\n".join(lines)

    def clear(self):
        """Clear all working memory entries."""
        self.pending_writes.clear()

    def increment_turn(self):
        """Increment the current turn counter."""
        self.current_turn += 1

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for persistence."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "pending_writes": [e.to_dict() for e in self.pending_writes],
            "current_turn": self.current_turn,
            "max_entries": self.max_entries
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkingMemory":
        """Deserialize from dictionary."""
        wm = cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            channel_id=data.get("channel_id"),
            current_turn=data.get("current_turn", 0),
            max_entries=data.get("max_entries", 20)
        )
        wm.pending_writes = [
            MemoryEntry.from_dict(e) for e in data.get("pending_writes", [])
        ]
        return wm

    def __len__(self) -> int:
        """Return number of entries in working memory."""
        return len(self.pending_writes)

    def __bool__(self) -> bool:
        """Return True if working memory has entries."""
        return bool(self.pending_writes)
