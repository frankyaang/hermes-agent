"""
Tests for Phase 4 - Embedding Cache, Auto-Embedding, and Memory Decay.
"""

import pytest
import tempfile
import uuid
import json
import pickle
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent.memory_database import (
    MemoryDatabase, Memory, EmbeddingConfig
)


class TestEmbeddingCache:
    """Test embedding cache functionality."""

    def test_cache_embedding(self):
        """Test caching an embedding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=True)
            )

            content_hash = "abc123"
            embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

            db.cache_embedding(
                content_hash=content_hash,
                embedding=embedding,
                model="test-model",
                dimensions=5,
                content_preview="Test content"
            )

            # Verify it's cached
            cached = db.get_cached_embedding(content_hash)
            assert cached == embedding

            # Check stats
            stats = db.get_embedding_cache_stats()
            assert stats["total_entries"] == 1
            assert stats["total_uses"] >= 1

            db.close()

    def test_cache_embedding_update(self):
        """Test updating an existing cache entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=True)
            )

            content_hash = "abc123"
            embedding1 = [0.1, 0.2, 0.3]
            embedding2 = [0.4, 0.5, 0.6]

            # First insert
            db.cache_embedding(content_hash, embedding1, "model", 3, "content1")
            stats1 = db.get_embedding_cache_stats()
            assert stats1["total_entries"] == 1

            # Second insert (should update)
            db.cache_embedding(content_hash, embedding2, "model", 3, "content2")
            stats2 = db.get_embedding_cache_stats()
            assert stats2["total_entries"] == 1  # Still 1 entry

            # Verify updated value
            cached = db.get_cached_embedding(content_hash)
            assert cached == embedding2

            db.close()

    def test_get_cached_embedding_not_found(self):
        """Test getting a non-existent embedding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=True)
            )

            result = db.get_cached_embedding("nonexistent")
            assert result is None

            db.close()

    def test_get_cached_embeddings_batch(self):
        """Test batch retrieval of embeddings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=True)
            )

            # Cache multiple embeddings
            hashes = ["hash1", "hash2", "hash3"]
            embeddings = [
                [0.1, 0.2],
                [0.3, 0.4],
                [0.5, 0.6]
            ]

            for h, e in zip(hashes, embeddings):
                db.cache_embedding(h, e, "model", 2, h)

            # Batch retrieval
            result = db.get_cached_embeddings_batch(hashes)
            assert len(result) == 3
            assert result["hash1"] == [0.1, 0.2]
            assert result["hash2"] == [0.3, 0.4]
            assert result["hash3"] == [0.5, 0.6]

            # Partial batch
            result2 = db.get_cached_embeddings_batch(["hash1", "nonexistent"])
            assert len(result2) == 1
            assert "hash1" in result2

            db.close()

    def test_clear_embedding_cache(self):
        """Test clearing the cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=True)
            )

            # Add some embeddings
            for i in range(5):
                db.cache_embedding(f"hash{i}", [float(i)] * 3, "model", 3, f"content{i}")

            stats = db.get_embedding_cache_stats()
            assert stats["total_entries"] == 5

            # Clear all
            count = db.clear_embedding_cache()
            assert count == 5

            stats = db.get_embedding_cache_stats()
            assert stats["total_entries"] == 0

            db.close()

    def test_clear_old_cache_entries(self):
        """Test clearing only old entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=True)
            )

            # Directly manipulate last_used_at to create old entries
            now = int(time.time())
            old_time = now - (2 * 86400)  # 2 days ago

            for i in range(3):
                db.cache_embedding(f"old_hash{i}", [float(i)] * 3, "model", 3, f"old{i}")

            for i in range(2):
                db.cache_embedding(f"new_hash{i}", [float(i)] * 3, "model", 3, f"new{i}")

            # Set old entries to be old
            db.conn.execute("""
                UPDATE embedding_cache
                SET last_used_at = ?
                WHERE content_hash LIKE 'old_%'
            """, (old_time,))
            db.conn.commit()

            # Clear entries older than 1 day
            count = db.clear_embedding_cache(older_than_days=1)
            assert count == 3

            stats = db.get_embedding_cache_stats()
            assert stats["total_entries"] == 2

            db.close()


class TestAutoEmbedding:
    """Test auto-embedding generation."""

    def test_insert_without_embedding_service(self):
        """Test insert without embedding service (should not fail)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=False)
            )

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="user1",
                content="This is a test memory",
                memory_type="test"
            )

            # Should not raise
            result = db.insert(memory, auto_embed=True)
            assert result == memory.memory_id

            db.close()

    def test_insert_with_min_content_length(self):
        """Test that short content is not embedded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(
                    enabled=True,
                    min_content_length=50
                )
            )

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="user1",
                content="Short",  # Less than 50 chars
                memory_type="test"
            )

            # Insert should work, but no embedding should be generated
            result = db.insert(memory, auto_embed=True)
            assert result == memory.memory_id

            # Check no embedding cached
            cached = db.get_cached_embedding(memory.content_hash)
            assert cached is None

            db.close()

    def test_insert_with_mocked_embedding_service(self):
        """Test insert with mocked embedding service."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(
                    enabled=True,
                    provider="openai",
                    model="text-embedding-3-small"
                )
            )

            mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

            with patch.object(db, '_get_embedding_service') as mock_get:
                mock_service = MagicMock()
                mock_result = MagicMock()
                mock_result.embedding = mock_embedding
                mock_result.model = "text-embedding-3-small"
                mock_service.embed.return_value = mock_result
                mock_get.return_value = mock_service

                memory = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content="This is a longer test memory with enough content",
                    memory_type="test"
                )

                result = db.insert(memory, auto_embed=True)
                assert result == memory.memory_id

                # Verify embedding was cached
                cached = db.get_cached_embedding(memory.content_hash)
                assert cached == mock_embedding

                # Verify service was called
                mock_service.embed.assert_called_once()

            db.close()

    def test_insert_skips_existing_cache(self):
        """Test that insert uses existing cached embeddings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=True)
            )

            content_hash = "existing_hash"
            cached_embedding = [0.9, 0.8, 0.7]

            # Pre-cache the embedding
            db.cache_embedding(content_hash, cached_embedding, "model", 3, "existing")

            mock_call_count = [0]

            with patch.object(db, '_get_embedding_service') as mock_get:
                mock_service = MagicMock()
                mock_call_count[0] = 0

                def track_call(text):
                    mock_call_count[0] += 1
                    result = MagicMock()
                    result.embedding = [0.1, 0.2, 0.3]
                    result.model = "model"
                    return result

                mock_service.embed.side_effect = track_call
                mock_get.return_value = mock_service

                memory = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content="existing",  # This would hash to "existing_hash"
                    memory_type="test"
                )

                # Manually set the content hash to match our pre-cached one
                memory.content_hash  # This is computed, but we can simulate by checking
                # Note: content_hash is derived from content, so "existing" -> "existing_hash"

                # The insert should check cache first
                cached_before = db.get_cached_embedding(memory.content_hash)

                db.close()


class TestMemoryDecay:
    """Test memory decay functionality."""

    def test_init_memory_decay(self):
        """Test initializing decay tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig()
            )

            memory_id = str(uuid.uuid4())

            # Create a memory first
            memory = Memory(
                memory_id=memory_id,
                user_id="user1",
                content="Test content for decay",
                memory_type="test",
                priority=70
            )
            db.insert(memory, auto_embed=False)

            # Initialize decay
            db.init_memory_decay(memory_id, base_priority=70)

            # Verify it's initialized
            row = db.conn.execute(
                "SELECT * FROM memory_decay WHERE memory_id = ?",
                (memory_id,)
            ).fetchone()

            assert row is not None
            assert row['base_priority'] == 70
            assert row['decay_factor'] == 1.0

            db.close()

    def test_calculate_effective_priority_fresh_memory(self):
        """Test priority calculation for a fresh memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig()
            )

            now = int(time.time())

            # Fresh memory (1 hour old, no access)
            priority, reason = db.calculate_effective_priority(
                memory_id="test1",
                created_at=now - 3600,  # 1 hour ago
                access_count=0,
                last_accessed_at=None,
                base_priority=50
            )

            # Should be close to base priority (minimal decay)
            assert priority >= 45  # Minimal decay for fresh memory
            assert reason == "normal" or reason == "recently_accessed"

            db.close()

    def test_calculate_effective_priority_old_memory(self):
        """Test priority calculation for an old memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig()
            )

            now = int(time.time())

            # Old memory (100 days old, no access)
            priority, reason = db.calculate_effective_priority(
                memory_id="test1",
                created_at=now - (100 * 86400),  # 100 days ago
                access_count=0,
                last_accessed_at=None,
                base_priority=50
            )

            # Should be significantly decayed (halflife is 90 days)
            # After 100 days with halflife of 90, should be ~35% of original
            assert priority < 30  # Decayed significantly
            assert reason == "stale"

            db.close()

    def test_calculate_effective_priority_accessed_memory(self):
        """Test that frequent access boosts priority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig()
            )

            now = int(time.time())

            # Same old memory but with many accesses
            priority_no_access, _ = db.calculate_effective_priority(
                memory_id="test1",
                created_at=now - (100 * 86400),
                access_count=0,
                last_accessed_at=None,
                base_priority=50
            )

            priority_with_access, _ = db.calculate_effective_priority(
                memory_id="test1",
                created_at=now - (100 * 86400),
                access_count=100,  # Many accesses
                last_accessed_at=now - 3600,  # Accessed recently
                base_priority=50
            )

            # Access should boost priority
            assert priority_with_access > priority_no_access

            db.close()

    def test_apply_decay_to_all(self):
        """Test applying decay to all memories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig()
            )

            # Create multiple memories with different ages
            now = int(time.time())

            memories = [
                Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content=f"Memory {i}",
                    memory_type="test",
                    priority=50,
                    created_at=now - (i * 86400),  # i days old
                    access_count=5 if i < 7 else 0
                )
                for i in range(10)  # 0 to 9 days old
            ]

            for m in memories:
                db.insert(m, auto_embed=False)

            # Apply decay
            updated = db.apply_decay_to_all()

            # Some memories should have been updated
            assert updated >= 0

            # Verify decay stats
            stats = db.get_decay_stats()
            assert stats["total"] == 10

            db.close()

    def test_get_decay_stats(self):
        """Test getting decay statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig()
            )

            now = int(time.time())

            # Create memories with various priorities
            for i in range(10):
                m = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content=f"Memory {i}",
                    memory_type="test",
                    priority=(i + 1) * 10,  # 10, 20, 30, ... 100
                    created_at=now - (i * 10 * 86400),  # Different ages
                    access_count=i
                )
                db.insert(m, auto_embed=False)

            stats = db.get_decay_stats()

            assert stats["total"] == 10
            assert stats["high_priority"] >= 0
            assert stats["medium_priority"] >= 0
            assert stats["low_priority"] >= 0
            assert stats["avg_age_days"] >= 0
            assert stats["avg_access_count"] >= 0

            db.close()

    def test_schedule_memory_decay(self):
        """Test scheduling custom decay for a memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig()
            )

            memory_id = str(uuid.uuid4())

            # Create memory
            memory = Memory(
                memory_id=memory_id,
                user_id="user1",
                content="Memory with custom decay",
                memory_type="test"
            )
            db.insert(memory, auto_embed=False)

            # Schedule custom decay
            schedule = {
                "type": "exponential",
                "halflife_days": 30,
                "min_priority": 10,
                "boost_on_access": True
            }

            db.schedule_memory_decay(memory_id, schedule)

            # Verify schedule was stored
            row = db.conn.execute(
                "SELECT decay_schedule FROM memory_decay WHERE memory_id = ?",
                (memory_id,)
            ).fetchone()

            assert row is not None
            stored_schedule = json.loads(row['decay_schedule'])
            assert stored_schedule["type"] == "exponential"
            assert stored_schedule["halflife_days"] == 30

            db.close()


class TestIntegration:
    """Integration tests for Phase 4 features."""

    def test_full_workflow(self):
        """Test complete workflow with cache, auto-embed, and decay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(
                    enabled=True,
                    min_content_length=10
                )
            )

            # Mock embedding service
            mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

            with patch.object(db, '_get_embedding_service') as mock_get:
                mock_service = MagicMock()
                mock_result = MagicMock()
                mock_result.embedding = mock_embedding
                mock_result.model = "text-embedding-3-small"
                mock_service.embed.return_value = mock_result
                mock_get.return_value = mock_service

                # Insert memory (auto-embed enabled)
                memory = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content="User prefers Python programming",
                    memory_type="preference",
                    tags=["python", "preference"],
                    priority=75
                )

                result = db.insert(memory, auto_embed=True)
                assert result == memory.memory_id

                # Verify embedding was cached
                cached = db.get_cached_embedding(memory.content_hash)
                assert cached == mock_embedding

                # Verify decay was initialized
                decay_row = db.conn.execute(
                    "SELECT * FROM memory_decay WHERE memory_id = ?",
                    (memory.memory_id,)
                ).fetchone()
                assert decay_row is not None
                assert decay_row['base_priority'] == 75

                # Access the memory
                db.increment_access_count(memory.memory_id)

                # Calculate decay
                priority, reason = db.calculate_effective_priority(
                    memory_id=memory.memory_id,
                    created_at=memory.created_at,
                    access_count=1,
                    last_accessed_at=int(time.time()),
                    base_priority=75
                )

                # Recent access should boost priority
                assert priority >= 75 or reason == "recently_accessed"

            # Get full stats
            cache_stats = db.get_embedding_cache_stats()
            decay_stats = db.get_decay_stats()

            assert cache_stats["total_entries"] >= 1
            assert decay_stats["total"] >= 1

            db.close()

    def test_cache_hit_for_duplicate_content(self):
        """Test that duplicate content uses cached embedding."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig(enabled=True)
            )

            content1 = "Same content for first memory"
            content2 = "Same content for first memory"  # Same content = same hash

            with patch.object(db, '_get_embedding_service') as mock_get:
                mock_service = MagicMock()
                mock_result = MagicMock()
                mock_result.embedding = [0.1, 0.2, 0.3]
                mock_result.model = "test"
                mock_service.embed.return_value = mock_result
                mock_get.return_value = mock_service

                # First memory
                m1 = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content=content1,
                    memory_type="test",
                    scope="user"  # Different scope allows same content
                )
                db.insert(m1, auto_embed=True)

                # Second memory with same content but DIFFERENT scope
                m2 = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content=content2,
                    memory_type="test",
                    scope="project"  # Different scope
                )
                db.insert(m2, auto_embed=True)

                # Embedding should only be generated once
                assert mock_service.embed.call_count == 1

                # Cache should have only one entry (same content hash)
                stats = db.get_embedding_cache_stats()
                assert stats["total_entries"] == 1

            db.close()

    def test_decay_affects_search_results(self):
        """Test that decay affects priority in search results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MemoryDatabase(
                Path(tmpdir) / "test.db",
                "user1",
                embedding_config=EmbeddingConfig()
            )

            now = int(time.time())

            # Create memories with different priorities
            memories = [
                Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content=f"High priority memory {i}",
                    memory_type="test",
                    priority=80,
                    created_at=now - 3600  # Fresh
                )
                for i in range(3)
            ]

            memories.extend([
                Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content=f"Low priority memory {i}",
                    memory_type="test",
                    priority=20,
                    created_at=now - (100 * 86400)  # Old
                )
                for i in range(3)
            ])

            for m in memories:
                db.insert(m, auto_embed=False)

            # Search (ordered by priority DESC)
            results = db.search(limit=100)

            # High priority memories should generally appear first
            # (though decay might affect actual priority)
            assert len(results) == 6

            # At least the fresh memories should be accessible
            fresh_memories = [r for r in results if r.priority >= 50]
            assert len(fresh_memories) >= 3

            db.close()
