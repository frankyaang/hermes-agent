"""
Tests for Working Memory - session-scoped immediate memory.
"""

import pytest
from agent.working_memory import WorkingMemory, MemoryEntry


class TestMemoryEntry:
    """Test MemoryEntry dataclass."""

    def test_create_entry(self):
        """Test creating a memory entry."""
        entry = MemoryEntry(
            content="User prefers Python",
            memory_type="preference",
            confidence=0.95
        )
        assert entry.content == "User prefers Python"
        assert entry.memory_type == "preference"
        assert entry.confidence == 0.95

    def test_entry_to_dict(self):
        """Test serialization to dict."""
        entry = MemoryEntry(
            content="Test content",
            memory_type="fact",
            confidence=1.0,
            metadata={"source": "test"}
        )
        data = entry.to_dict()
        assert data["content"] == "Test content"
        assert data["memory_type"] == "fact"
        assert data["confidence"] == 1.0
        assert data["metadata"]["source"] == "test"

    def test_entry_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "content": "Test content",
            "memory_type": "fact",
            "confidence": 0.8,
            "created_at": 1234567890.0,
            "metadata": {"key": "value"}
        }
        entry = MemoryEntry.from_dict(data)
        assert entry.content == "Test content"
        assert entry.memory_type == "fact"
        assert entry.confidence == 0.8
        assert entry.created_at == 1234567890.0
        assert entry.metadata["key"] == "value"


class TestWorkingMemory:
    """Test WorkingMemory class."""

    def test_create_working_memory(self):
        """Test creating a working memory instance."""
        wm = WorkingMemory(
            session_id="test_session",
            user_id="test_user",
            channel_id="test_channel"
        )
        assert wm.session_id == "test_session"
        assert wm.user_id == "test_user"
        assert wm.channel_id == "test_channel"
        assert len(wm) == 0

    def test_add_pending_entry(self):
        """Test adding entries to working memory."""
        wm = WorkingMemory(session_id="s1", user_id="u1")

        entry1 = MemoryEntry(content="First memory", memory_type="fact")
        wm.add_pending(entry1)
        assert len(wm) == 1

        entry2 = MemoryEntry(content="Second memory", memory_type="preference")
        wm.add_pending(entry2)
        assert len(wm) == 2

    def test_get_visible_memories(self):
        """Test retrieving visible memories."""
        wm = WorkingMemory(session_id="s1", user_id="u1")

        entry1 = MemoryEntry(content="Memory 1", memory_type="fact")
        entry2 = MemoryEntry(content="Memory 2", memory_type="preference")

        wm.add_pending(entry1)
        wm.add_pending(entry2)

        memories = wm.get_visible_memories()
        assert len(memories) == 2
        assert memories[0].content == "Memory 1"
        assert memories[1].content == "Memory 2"

    def test_format_for_context_empty(self):
        """Test formatting empty working memory."""
        wm = WorkingMemory(session_id="s1", user_id="u1")
        formatted = wm.format_for_context()
        assert formatted == ""

    def test_format_for_context_with_entries(self):
        """Test formatting working memory with entries."""
        wm = WorkingMemory(session_id="s1", user_id="u1")

        wm.add_pending(MemoryEntry(content="User likes Python", memory_type="preference"))
        wm.add_pending(MemoryEntry(content="Project is Hermes", memory_type="project"))

        formatted = wm.format_for_context()
        assert "# Working Memory (Current Session)" in formatted
        assert "[preference] User likes Python" in formatted
        assert "[project] Project is Hermes" in formatted

    def test_format_for_context_with_low_confidence(self):
        """Test formatting includes confidence for low-confidence entries."""
        wm = WorkingMemory(session_id="s1", user_id="u1")

        wm.add_pending(MemoryEntry(
            content="Uncertain fact",
            memory_type="fact",
            confidence=0.6
        ))

        formatted = wm.format_for_context()
        assert "confidence: 0.60" in formatted

    def test_max_entries_enforcement(self):
        """Test that max_entries limit is enforced (FIFO eviction)."""
        wm = WorkingMemory(session_id="s1", user_id="u1", max_entries=3)

        wm.add_pending(MemoryEntry(content="Entry 1", memory_type="fact"))
        wm.add_pending(MemoryEntry(content="Entry 2", memory_type="fact"))
        wm.add_pending(MemoryEntry(content="Entry 3", memory_type="fact"))
        assert len(wm) == 3

        # Adding 4th entry should evict the first
        wm.add_pending(MemoryEntry(content="Entry 4", memory_type="fact"))
        assert len(wm) == 3

        memories = wm.get_visible_memories()
        assert memories[0].content == "Entry 2"  # Entry 1 was evicted
        assert memories[1].content == "Entry 3"
        assert memories[2].content == "Entry 4"

    def test_clear(self):
        """Test clearing working memory."""
        wm = WorkingMemory(session_id="s1", user_id="u1")

        wm.add_pending(MemoryEntry(content="Memory 1", memory_type="fact"))
        wm.add_pending(MemoryEntry(content="Memory 2", memory_type="fact"))
        assert len(wm) == 2

        wm.clear()
        assert len(wm) == 0

    def test_increment_turn(self):
        """Test turn counter increment."""
        wm = WorkingMemory(session_id="s1", user_id="u1")
        assert wm.current_turn == 0

        wm.increment_turn()
        assert wm.current_turn == 1

        wm.increment_turn()
        assert wm.current_turn == 2

    def test_serialization(self):
        """Test serialization and deserialization."""
        wm = WorkingMemory(session_id="s1", user_id="u1", channel_id="c1")
        wm.add_pending(MemoryEntry(content="Test memory", memory_type="fact"))
        wm.increment_turn()

        # Serialize
        data = wm.to_dict()
        assert data["session_id"] == "s1"
        assert data["user_id"] == "u1"
        assert data["channel_id"] == "c1"
        assert data["current_turn"] == 1
        assert len(data["pending_writes"]) == 1

        # Deserialize
        wm2 = WorkingMemory.from_dict(data)
        assert wm2.session_id == "s1"
        assert wm2.user_id == "u1"
        assert wm2.channel_id == "c1"
        assert wm2.current_turn == 1
        assert len(wm2) == 1
        assert wm2.pending_writes[0].content == "Test memory"

    def test_bool_conversion(self):
        """Test boolean conversion."""
        wm = WorkingMemory(session_id="s1", user_id="u1")
        assert not wm  # Empty working memory is falsy

        wm.add_pending(MemoryEntry(content="Memory", memory_type="fact"))
        assert wm  # Non-empty working memory is truthy
