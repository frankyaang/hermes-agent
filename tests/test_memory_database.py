"""
Tests for MemoryDatabase - SQLite-backed memory storage.
"""

import pytest
import tempfile
import time
import uuid
from pathlib import Path
from agent.memory_database import MemoryDatabase, Memory


class TestMemory:
    """Test Memory dataclass."""

    def test_create_memory(self):
        """Test creating a Memory object."""
        memory = Memory(
            memory_id="test_id",
            user_id="ou_test",
            content="Test memory",
            memory_type="fact"
        )
        assert memory.memory_id == "test_id"
        assert memory.user_id == "ou_test"
        assert memory.content == "Test memory"
        assert memory.memory_type == "fact"
        assert memory.scope == "user"
        assert memory.confidence == 1.0

    def test_content_hash(self):
        """Test content hash generation."""
        memory1 = Memory(
            memory_id="id1",
            user_id="user1",
            content="Same content",
            memory_type="fact"
        )
        memory2 = Memory(
            memory_id="id2",
            user_id="user2",
            content="Same content",
            memory_type="fact"
        )
        # Same content should produce same hash
        assert memory1.content_hash == memory2.content_hash

        memory3 = Memory(
            memory_id="id3",
            user_id="user1",
            content="Different content",
            memory_type="fact"
        )
        # Different content should produce different hash
        assert memory1.content_hash != memory3.content_hash

    def test_to_dict(self):
        """Test serialization to dict."""
        memory = Memory(
            memory_id="test_id",
            user_id="ou_test",
            content="Test",
            memory_type="fact",
            tags=["tag1", "tag2"],
            metadata={"key": "value"}
        )
        data = memory.to_dict()
        assert data["memory_id"] == "test_id"
        assert data["content"] == "Test"
        assert "content_hash" in data
        assert "tags" not in data  # Tags stored separately
        assert '"key": "value"' in data["metadata"]  # JSON serialized

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "memory_id": "test_id",
            "user_id": "ou_test",
            "content": "Test",
            "memory_type": "fact",
            "scope": "user",
            "confidence": 0.9,
            "priority": 60,
            "status": "active",
            "created_at": 1234567890,
            "updated_at": 1234567890,
            "metadata": '{"key": "value"}',
            "tags": ["tag1"]
        }
        memory = Memory.from_dict(data)
        assert memory.memory_id == "test_id"
        assert memory.content == "Test"
        assert memory.metadata["key"] == "value"
        assert memory.tags == ["tag1"]


class TestMemoryDatabase:
    """Test MemoryDatabase class."""

    def test_init_database(self):
        """Test database initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")
            assert db.db_path == db_path
            assert db.user_id == "ou_test"
            assert db_path.exists()
            db.close()

    def test_insert_memory(self):
        """Test inserting a memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Test memory",
                memory_type="fact"
            )

            memory_id = db.insert(memory)
            assert memory_id == memory.memory_id

            # Verify insertion
            retrieved = db.get(memory_id)
            assert retrieved is not None
            assert retrieved.content == "Test memory"
            assert retrieved.memory_type == "fact"

            db.close()

    def test_insert_duplicate_content(self):
        """Test that duplicate content is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            memory1 = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Duplicate content",
                memory_type="fact",
                scope="user"
            )
            db.insert(memory1)

            # Try to insert duplicate
            memory2 = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Duplicate content",
                memory_type="fact",
                scope="user"
            )

            with pytest.raises(Exception):  # Should raise IntegrityError
                db.insert(memory2)

            db.close()

    def test_update_memory(self):
        """Test updating a memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Original content",
                memory_type="fact",
                priority=50
            )
            db.insert(memory)

            # Update
            success = db.update(memory.memory_id, {
                "content": "Updated content",
                "priority": 80
            })
            assert success

            # Verify update
            retrieved = db.get(memory.memory_id)
            assert retrieved.content == "Updated content"
            assert retrieved.priority == 80

            db.close()

    def test_soft_delete(self):
        """Test soft deletion (status='deleted')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="To be deleted",
                memory_type="fact"
            )
            db.insert(memory)

            # Soft delete
            success = db.delete(memory.memory_id, soft=True)
            assert success

            # Memory still exists but status is 'deleted'
            retrieved = db.get(memory.memory_id)
            assert retrieved is not None
            assert retrieved.status == "deleted"

            db.close()

    def test_hard_delete(self):
        """Test hard deletion (permanent removal)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="To be deleted",
                memory_type="fact"
            )
            db.insert(memory)

            # Hard delete
            success = db.delete(memory.memory_id, soft=False)
            assert success

            # Memory should not exist
            retrieved = db.get(memory.memory_id)
            assert retrieved is None

            db.close()

    def test_search_by_type(self):
        """Test searching by memory type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            # Insert different types
            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Fact 1",
                memory_type="fact"
            ))
            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Preference 1",
                memory_type="preference"
            ))
            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Fact 2",
                memory_type="fact"
            ))

            # Search for facts
            facts = db.search(memory_type="fact")
            assert len(facts) == 2
            assert all(m.memory_type == "fact" for m in facts)

            # Search for preferences
            prefs = db.search(memory_type="preference")
            assert len(prefs) == 1
            assert prefs[0].memory_type == "preference"

            db.close()

    def test_search_by_scope(self):
        """Test searching by scope."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="User scope",
                memory_type="fact",
                scope="user"
            ))
            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Project scope",
                memory_type="fact",
                scope="project",
                project_id="proj1"
            ))

            # Search user scope
            user_memories = db.search(scope=["user"])
            assert len(user_memories) == 1
            assert user_memories[0].scope == "user"

            # Search project scope
            project_memories = db.search(scope=["project"])
            assert len(project_memories) == 1
            assert project_memories[0].scope == "project"

            # Search both
            all_memories = db.search(scope=["user", "project"])
            assert len(all_memories) == 2

            db.close()

    def test_search_by_tags(self):
        """Test searching by tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Python memory",
                memory_type="fact",
                tags=["python", "programming"]
            ))
            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="JavaScript memory",
                memory_type="fact",
                tags=["javascript", "programming"]
            ))
            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Cooking memory",
                memory_type="fact",
                tags=["cooking"]
            ))

            # Search by single tag
            programming = db.search(tags=["programming"])
            assert len(programming) == 2

            # Search by multiple tags (AND logic)
            python_prog = db.search(tags=["python", "programming"])
            assert len(python_prog) == 1
            assert "Python" in python_prog[0].content

            db.close()

    def test_search_by_keywords(self):
        """Test keyword search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="User prefers Python for scripting",
                memory_type="preference"
            ))
            db.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Project uses JavaScript and TypeScript",
                memory_type="fact"
            ))

            # Search for "Python"
            results = db.search_by_keywords(["Python"])
            assert len(results) == 1
            assert "Python" in results[0].content

            # Search for "JavaScript" OR "TypeScript"
            results = db.search_by_keywords(["JavaScript", "TypeScript"])
            assert len(results) == 1

            db.close()

    def test_access_tracking(self):
        """Test access count and last_accessed_at tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Test memory",
                memory_type="fact"
            )
            db.insert(memory)

            # Initial state
            retrieved = db.get(memory.memory_id)
            assert retrieved.access_count == 0
            assert retrieved.last_accessed_at is None

            # Increment access
            db.increment_access_count(memory.memory_id)

            # Verify increment
            retrieved = db.get(memory.memory_id)
            assert retrieved.access_count == 1
            assert retrieved.last_accessed_at is not None

            # Increment again
            db.increment_access_count(memory.memory_id)
            retrieved = db.get(memory.memory_id)
            assert retrieved.access_count == 2

            db.close()

    def test_count_active_memories(self):
        """Test counting active memories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            # Insert active memories
            for i in range(3):
                db.insert(Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="ou_test",
                    content=f"Memory {i}",
                    memory_type="fact"
                ))

            # Insert archived memory
            archived = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Archived",
                memory_type="fact",
                status="archived"
            )
            db.insert(archived)

            # Count should only include active
            count = db.count_active_memories()
            assert count == 3

            db.close()

    def test_user_isolation(self):
        """Test that users can't see each other's memories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # User A
            db_a = MemoryDatabase(db_path, "ou_user_a")
            db_a.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_a",
                content="User A's memory",
                memory_type="fact"
            ))
            db_a.close()

            # User B
            db_b = MemoryDatabase(db_path, "ou_user_b")
            db_b.insert(Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_user_b",
                content="User B's memory",
                memory_type="fact"
            ))

            # User B should only see their own memories
            memories = db_b.search()
            assert len(memories) == 1
            assert memories[0].content == "User B's memory"

            db_b.close()
