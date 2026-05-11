"""
Tests for Memory Decay and Summarization modules.
"""

import pytest
import tempfile
import time
import uuid
from pathlib import Path
from agent.memory_database import MemoryDatabase, Memory, DecayStrategy


class TestDecayStrategy:
    """Test DecayStrategy dataclass."""

    def test_default_values(self):
        """Test default decay strategy."""
        strategy = DecayStrategy()
        assert strategy.importance == "normal"
        assert strategy.halflife_days == 90
        assert strategy.min_priority == 10
        assert strategy.access_boost_factor == 0.10

    def test_critical_importance(self):
        """Test critical importance strategy."""
        strategy = DecayStrategy(importance="critical")
        assert strategy.importance == "critical"
        assert strategy.halflife_days == 365  # 1 year
        assert strategy.min_priority == 30
        assert strategy.access_boost_factor == 0.15

    def test_important_importance(self):
        """Test important importance strategy."""
        strategy = DecayStrategy(importance="important")
        assert strategy.importance == "important"
        assert strategy.halflife_days == 180  # 6 months
        assert strategy.min_priority == 20
        assert strategy.access_boost_factor == 0.12

    def test_low_importance(self):
        """Test low importance strategy."""
        strategy = DecayStrategy(importance="low")
        assert strategy.importance == "low"
        assert strategy.halflife_days == 30  # 1 month
        assert strategy.min_priority == 5
        assert strategy.access_boost_factor == 0.05

    def test_invalid_importance(self):
        """Test invalid importance falls back to normal."""
        strategy = DecayStrategy(importance="invalid")
        assert strategy.importance == "invalid"  # Raw value stored
        assert strategy.halflife_days == 90  # Default
        assert strategy.min_priority == 10  # Default


class TestDecayCalculation:
    """Test effective priority calculation with decay."""

    def test_normal_decay_over_time(self):
        """Test that priority decays over time for normal importance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            # Create memory 60 days ago
            created_at = int(time.time()) - (60 * 86400)

            effective, reason = db.calculate_effective_priority(
                memory_id="test",
                created_at=created_at,
                access_count=0,
                last_accessed_at=None,
                base_priority=50,
                importance="normal"
            )

            # At 60 days with 90 day halflife, should be ~70% of original
            assert 30 < effective < 50
            assert reason == "stale"

            db.close()

    def test_critical_slow_decay(self):
        """Test critical importance decays slower."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            created_at = int(time.time()) - (60 * 86400)

            # Normal decay
            normal_priority, _ = db.calculate_effective_priority(
                memory_id="test",
                created_at=created_at,
                access_count=0,
                last_accessed_at=None,
                base_priority=50,
                importance="normal"
            )

            # Critical decay (should be higher)
            critical_priority, _ = db.calculate_effective_priority(
                memory_id="test",
                created_at=created_at,
                access_count=0,
                last_accessed_at=None,
                base_priority=50,
                importance="critical"
            )

            # Critical should have higher effective priority (slower decay)
            assert critical_priority > normal_priority

            db.close()

    def test_access_boost(self):
        """Test that frequent access boosts priority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            created_at = int(time.time()) - (30 * 86400)  # 30 days old

            # No access
            no_access, _ = db.calculate_effective_priority(
                memory_id="test",
                created_at=created_at,
                access_count=0,
                last_accessed_at=None,
                base_priority=50,
                importance="normal"
            )

            # High access
            high_access, _ = db.calculate_effective_priority(
                memory_id="test",
                created_at=created_at,
                access_count=25,  # 5 accesses
                last_accessed_at=int(time.time()),  # Just accessed
                base_priority=50,
                importance="normal"
            )

            # Recently accessed with high count should boost priority
            assert high_access > no_access

            db.close()

    def test_recency_boost(self):
        """Test that recent access provides 20% boost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            created_at = int(time.time()) - (30 * 86400)

            # Accessed 3 days ago
            recent_priority, recent_reason = db.calculate_effective_priority(
                memory_id="test",
                created_at=created_at,
                access_count=5,
                last_accessed_at=int(time.time()) - (3 * 86400),
                base_priority=50,
                importance="normal"
            )

            assert recent_reason == "recently_accessed"

            db.close()

    def test_min_priority_floor(self):
        """Test that priority doesn't go below min_priority for importance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            # Very old memory (2 years)
            created_at = int(time.time()) - (730 * 86400)

            for importance in ["critical", "important", "normal", "low"]:
                strategy = DecayStrategy(importance=importance)
                effective, _ = db.calculate_effective_priority(
                    memory_id="test",
                    created_at=created_at,
                    access_count=0,
                    last_accessed_at=None,
                    base_priority=50,
                    importance=importance
                )

                # Should not go below importance floor
                assert effective >= strategy.min_priority

            db.close()

    def test_priority_cap_at_100(self):
        """Test that priority is capped at 100."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            # Very new memory with high base priority
            created_at = int(time.time()) - 3600  # 1 hour ago

            effective, _ = db.calculate_effective_priority(
                memory_id="test",
                created_at=created_at,
                access_count=100,
                last_accessed_at=int(time.time()),
                base_priority=100,
                importance="critical"
            )

            # Should be capped at 100
            assert effective <= 100

            db.close()


class TestDecayStats:
    """Test decay statistics collection."""

    def test_decay_stats_structure(self):
        """Test that decay stats has correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            stats = db.get_decay_stats()

            assert "total" in stats
            assert "by_importance" in stats
            assert "critical" in stats["by_importance"]
            assert "important" in stats["by_importance"]
            assert "normal" in stats["by_importance"]
            assert "low" in stats["by_importance"]

            db.close()

    def test_decay_stats_tracking(self):
        """Test that decay stats track importance levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            # Insert memories with different importance
            for imp in ["critical", "important", "normal", "low"]:
                memory = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="ou_test",
                    content=f"Memory with {imp} importance",
                    memory_type="fact",
                    importance=imp
                )
                db.insert(memory)

            stats = db.get_decay_stats()

            # Should track count per importance
            assert stats["by_importance"]["critical"]["count"] == 1
            assert stats["by_importance"]["important"]["count"] == 1
            assert stats["by_importance"]["normal"]["count"] == 1
            assert stats["by_importance"]["low"]["count"] == 1

            db.close()


class TestImportanceUpdate:
    """Test updating memory importance."""

    def test_update_importance(self):
        """Test updating memory importance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Test memory",
                memory_type="fact",
                importance="normal"
            )
            db.insert(memory)

            # Update importance
            success = db.update(memory.memory_id, {"importance": "critical"})
            assert success

            # Verify
            retrieved = db.get(memory.memory_id)
            assert retrieved.importance == "critical"

            db.close()

    def test_update_importance_and_priority(self):
        """Test updating both importance and priority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Test memory",
                memory_type="fact",
                importance="normal",
                priority=50
            )
            db.insert(memory)

            # Update both
            success = db.update(memory.memory_id, {
                "importance": "important",
                "priority": 80
            })
            assert success

            retrieved = db.get(memory.memory_id)
            assert retrieved.importance == "important"
            assert retrieved.priority == 80

            db.close()


class TestDecayByImportance:
    """Test applying decay based on importance levels."""

    def test_apply_decay_by_importance(self):
        """Test applying decay with importance awareness."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = MemoryDatabase(db_path, "ou_test")

            # Insert old memories with different importance
            created_at = int(time.time()) - (60 * 86400)  # 60 days old

            for imp in ["critical", "important", "normal", "low"]:
                memory = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="ou_test",
                    content=f"Old {imp} memory",
                    memory_type="fact",
                    importance=imp,
                    priority=50
                )
                db.insert(memory)

            # Apply decay
            updated = db.apply_decay_by_importance()

            # Should track updates by importance
            assert "critical" in updated
            assert "important" in updated

            db.close()