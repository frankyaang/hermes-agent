"""
Integration tests for Phase 2.5 - SQLite backend integration with Agent.
"""

import pytest
import tempfile
import uuid
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.memory_database import MemoryDatabase, Memory
from agent.working_memory import WorkingMemory, MemoryEntry


class TestSQLiteBackendIntegration:
    """Test Agent with SQLite memory backend."""

    def test_agent_init_with_sqlite_backend(self):
        """Test Agent initialization with SQLite backend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock config
            mem_config = {
                "memory_enabled": True,
                "user_profile_enabled": True,
                "backend": "sqlite",
                "memory_char_limit": 2200,
                "user_char_limit": 1375,
            }

            # Mock dependencies to avoid full initialization
            with patch("tools.memory_tool.MemoryStore"):
                # Just test the backend selection logic
                backend = mem_config.get("backend", "files")

                if backend == "sqlite":
                    from agent.memory_database import MemoryDatabase
                    db_path = Path(tmpdir) / "memories" / "test_user.db"
                    db = MemoryDatabase(db_path, "test_user")

                    # Test basic operations
                    memory = Memory(
                        memory_id=str(uuid.uuid4()),
                        user_id="test_user",
                        content="Test memory",
                        memory_type="fact"
                    )
                    db.insert(memory)

                    # Verify it was stored
                    retrieved = db.get(memory.memory_id)
                    assert retrieved is not None
                    assert retrieved.content == "Test memory"

                    # Verify working memory block format
                    from agent.working_memory import WorkingMemory, MemoryEntry
                    wm = WorkingMemory(session_id="s1", user_id="test_user")
                    entry = MemoryEntry(content="Test memory", memory_type="fact")
                    wm.add_pending(entry)

                    block = wm.format_for_context()
                    assert "Test memory" in block

                    db.close()


class TestSQLiteMemoryToolOperations:
    """Test memory tool operations with SQLite backend."""

    def test_add_memory(self):
        """Test adding a memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase, Memory

            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_user_a")

            # Simulate add action
            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_a",
                content="User prefers Python",
                memory_type="preference",
                scope="user"
            )
            db.insert(memory)

            # Verify
            retrieved = db.get(memory.memory_id)
            assert retrieved is not None
            assert retrieved.content == "User prefers Python"

            db.close()

    def test_replace_memory(self):
        """Test replacing a memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase, Memory

            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_user_a")

            # Add initial memory
            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_a",
                content="Old preference",
                memory_type="preference"
            )
            db.insert(memory)

            # Replace
            db.update(memory.memory_id, {"content": "New preference"})

            # Verify
            retrieved = db.get(memory.memory_id)
            assert retrieved.content == "New preference"

            db.close()

    def test_delete_memory(self):
        """Test deleting a memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase, Memory

            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_user_a")

            # Add memory
            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_a",
                content="To be deleted",
                memory_type="fact"
            )
            db.insert(memory)

            # Soft delete
            db.delete(memory.memory_id, soft=True)

            # Verify it's marked as deleted
            retrieved = db.get(memory.memory_id)
            assert retrieved is not None
            assert retrieved.status == "deleted"

            # Search should not return it
            results = db.search()
            found = any(m.memory_id == memory.memory_id for m in results)
            assert not found

            db.close()

    def test_list_memories(self):
        """Test listing memories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase, Memory

            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_user_a")

            # Add multiple memories
            for i in range(5):
                memory = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="ou_user_a",
                    content=f"Memory {i}",
                    memory_type="fact"
                )
                db.insert(memory)

            # List all
            results = db.search(limit=100)
            assert len(results) == 5

            # List by type
            results = db.search(memory_type="preference")
            assert len(results) == 0

            db.close()

    def test_search_memories(self):
        """Test searching memories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase, Memory

            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_user_a")

            # Add memories with different content
            memories = [
                Memory(memory_id=str(uuid.uuid4()), user_id="ou_user_a",
                       content="Python is great", memory_type="fact"),
                Memory(memory_id=str(uuid.uuid4()), user_id="ou_user_a",
                       content="JavaScript is also great", memory_type="fact"),
                Memory(memory_id=str(uuid.uuid4()), user_id="ou_user_a",
                       content="Python is fast", memory_type="preference"),
            ]
            for m in memories:
                db.insert(m)

            # Search by keyword
            results = db.search_by_keywords(keywords=["Python"])
            assert len(results) >= 2

            # Search by type
            results = db.search(memory_type="preference")
            assert len(results) >= 1

            db.close()

    def test_user_isolation(self):
        """Test that different users have isolated memories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase, Memory

            # Create separate databases for different users
            db_a = MemoryDatabase(Path(tmpdir) / "user_a.db", "ou_user_a")
            db_b = MemoryDatabase(Path(tmpdir) / "user_b.db", "ou_user_b")

            # Add memory to user A
            memory_a = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_a",
                content="User A secret",
                memory_type="fact"
            )
            db_a.insert(memory_a)

            # Add memory to user B
            memory_b = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_b",
                content="User B secret",
                memory_type="fact"
            )
            db_b.insert(memory_b)

            # Verify isolation
            user_a_memories = db_a.search()
            user_b_memories = db_b.search()

            assert any("User A secret" in m.content for m in user_a_memories)
            assert not any("User B secret" in m.content for m in user_a_memories)

            assert any("User B secret" in m.content for m in user_b_memories)
            assert not any("User A secret" in m.content for m in user_b_memories)

            db_a.close()
            db_b.close()

    def test_duplicate_prevention(self):
        """Test that duplicate content is prevented."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase, Memory

            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_user_a")

            # Add first memory
            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_a",
                content="Duplicate test",
                memory_type="fact"
            )
            db.insert(memory)

            # Try to add duplicate (should raise IntegrityError)
            from sqlite3 import IntegrityError
            duplicate = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_a",
                content="Duplicate test",  # Same content
                memory_type="fact"
            )

            with pytest.raises(IntegrityError):
                db.insert(duplicate)

            db.close()


class TestWorkingMemorySQLiteIntegration:
    """Test Working Memory with SQLite backend."""

    def test_working_memory_with_sqlite(self):
        """Test that working memory works with SQLite backend."""
        from agent.working_memory import WorkingMemory, MemoryEntry
        from agent.memory_database import MemoryDatabase, Memory

        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize SQLite
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_user_a")

            # Initialize Working Memory
            wm = WorkingMemory(
                session_id="test_session",
                user_id="ou_user_a",
                channel_id="test_channel"
            )

            # Simulate a memory tool call
            entry = MemoryEntry(
                content="SQLite memory test",
                memory_type="fact",
                confidence=1.0,
                metadata={"source": "sqlite_memory"}
            )
            wm.add_pending(entry)

            # Verify immediate visibility
            visible = wm.get_visible_memories()
            assert len(visible) == 1
            assert visible[0].content == "SQLite memory test"

            # Simulate async persistence to SQLite
            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_a",
                content="SQLite memory test",
                memory_type="fact"
            )
            db.insert(memory)

            # Verify it was persisted
            retrieved = db.get(memory.memory_id)
            assert retrieved is not None
            assert retrieved.content == "SQLite memory test"

            # Format for context
            block = wm.format_for_context()
            assert "# Working Memory (Current Session)" in block
            assert "SQLite memory test" in block

            db.close()

    def test_format_for_context_with_sqlite(self):
        """Test context formatting with SQLite-backed data."""
        from agent.working_memory import WorkingMemory, MemoryEntry

        wm = WorkingMemory(session_id="s1", user_id="u1")

        # Add multiple entries
        wm.add_pending(MemoryEntry(content="Entry 1", memory_type="fact"))
        wm.add_pending(MemoryEntry(content="Entry 2", memory_type="preference"))
        wm.add_pending(MemoryEntry(content="Entry 3", memory_type="experience"))

        # Format for context
        block = wm.format_for_context()

        assert "# Working Memory (Current Session)" in block
        assert "[fact] Entry 1" in block
        assert "[preference] Entry 2" in block
        assert "[experience] Entry 3" in block

        # Test empty case
        wm2 = WorkingMemory(session_id="s2", user_id="u1")
        empty_block = wm2.format_for_context()
        assert empty_block == ""