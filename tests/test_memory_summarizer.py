"""
Tests for Memory Summarization Module.
"""

import pytest
import tempfile
import json
import time
import uuid
from pathlib import Path
from agent.memory_summarizer import (
    MemorySummary,
    SummarizationConfig,
    MemorySummarizer,
)


class TestMemorySummary:
    """Test MemorySummary dataclass."""

    def test_create_summary(self):
        """Test creating a MemorySummary object."""
        summary = MemorySummary(
            summary_id="sum_123",
            memory_id="mem_456",
            user_id="ou_test",
            original_content="Original content here",
            summary="Summarized content",
            key_points=["Point 1", "Point 2"]
        )

        assert summary.summary_id == "sum_123"
        assert summary.memory_id == "mem_456"
        assert summary.summary == "Summarized content"
        assert len(summary.key_points) == 2
        assert summary.compressed_count == 1

    def test_content_hash(self):
        """Test content hash generation."""
        summary1 = MemorySummary(
            summary_id="sum_1",
            memory_id="mem_1",
            user_id="ou_test",
            original_content="Same content",
            summary="Summary 1"
        )
        summary2 = MemorySummary(
            summary_id="sum_2",
            memory_id="mem_2",
            user_id="ou_test",
            original_content="Same content",
            summary="Summary 2"
        )

        # Same content should produce same hash
        assert summary1.content_hash == summary2.content_hash

    def test_to_dict(self):
        """Test serialization to dict."""
        summary = MemorySummary(
            summary_id="sum_123",
            memory_id="mem_456",
            user_id="ou_test",
            original_content="Original",
            summary="Summarized",
            key_points=["Point 1", "Point 2"],
            metadata={"key": "value"}
        )

        data = summary.to_dict()

        assert data["summary_id"] == "sum_123"
        assert data["summary"] == "Summarized"
        assert isinstance(data["key_points"], str)  # JSON serialized
        assert isinstance(data["metadata"], str)  # JSON serialized

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "summary_id": "sum_123",
            "memory_id": "mem_456",
            "user_id": "ou_test",
            "original_content": "Original",
            "summary": "Summarized",
            "key_points": json.dumps(["Point 1", "Point 2"]),
            "memory_type": "general",
            "importance": "normal",
            "compressed_count": 1,
            "created_at": 1234567890,
            "expires_at": None,
            "metadata": json.dumps({"key": "value"})
        }

        summary = MemorySummary.from_dict(data)

        assert summary.summary_id == "sum_123"
        assert len(summary.key_points) == 2
        assert summary.metadata["key"] == "value"


class TestSummarizationConfig:
    """Test SummarizationConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = SummarizationConfig()

        assert config.age_threshold_days == 60
        assert config.priority_threshold == 30
        assert config.min_memories_for_batching == 3
        assert config.max_batch_size == 10
        assert config.use_llm is True
        assert config.max_summary_length == 500
        assert config.max_key_points == 5

    def test_custom_config(self):
        """Test custom configuration."""
        config = SummarizationConfig(
            age_threshold_days=30,
            priority_threshold=20,
            use_llm=False,
            llm_model="claude-3-haiku"
        )

        assert config.age_threshold_days == 30
        assert config.priority_threshold == 20
        assert config.use_llm is False


class TestMemorySummarizer:
    """Test MemorySummarizer class."""

    def test_init_schema(self):
        """Test database schema initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            summarizer = MemorySummarizer(db_path)

            # Schema should be created
            assert db_path.exists()

            summarizer.close()

    def test_find_memories_to_summarize(self):
        """Test finding memories eligible for summarization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            summarizer = MemorySummarizer(db_path)

            # Create test memories
            from agent.memory_database import MemoryDatabase, Memory

            db = MemoryDatabase(db_path, "ou_test")

            # Insert old, low-priority memories
            old_time = int(time.time()) - (90 * 86400)  # 90 days old
            for i in range(3):
                memory = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="ou_test",
                    content=f"Old memory {i}",
                    memory_type="fact",
                    priority=20,  # Below threshold
                    created_at=old_time
                )
                db.insert(memory)

            # Insert recent, high-priority memory (should not be found)
            recent_time = int(time.time()) - (30 * 86400)  # 30 days old
            memory = Memory(
                memory_id=str(uuid.uuid4()),
                user_id="ou_test",
                content="Recent priority memory",
                memory_type="fact",
                priority=80,  # Above threshold
                created_at=recent_time
            )
            db.insert(memory)

            db.close()

            # Find memories to summarize
            to_summarize = summarizer.find_memories_to_summarize("ou_test")

            # Should find 3 old, low-priority memories
            assert len(to_summarize) == 3
            assert all(m['priority'] < 30 for m in to_summarize)

            summarizer.close()

    def test_heuristic_summarization(self):
        """Test heuristic (fallback) summarization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = SummarizationConfig(use_llm=False)
            summarizer = MemorySummarizer(db_path, config=config)

            contents = [
                "This is the first memory about Python programming. It contains useful information.",
                "Second memory discusses JavaScript frameworks. Important for web development.",
            ]
            types = ["fact", "fact"]

            summary, key_points = summarizer.summarize_with_heuristics(contents, types)

            assert len(summary) > 0
            assert isinstance(summary, str)

            summarizer.close()

    def test_create_summary(self):
        """Test creating a summary from memories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = SummarizationConfig(use_llm=False)  # Use heuristics
            summarizer = MemorySummarizer(db_path, config=config)

            memory_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
            contents = [
                "First memory content",
                "Second memory content"
            ]
            types = ["fact", "preference"]

            summary = summarizer.create_summary(
                memory_ids=memory_ids,
                user_id="ou_test",
                original_contents=contents,
                memory_types=types,
                importance="normal"
            )

            assert summary.summary_id.startswith("sum_")
            assert summary.user_id == "ou_test"
            assert summary.compressed_count == 2
            assert len(summary.original_content) > 0

            summarizer.close()

    def test_get_summaries(self):
        """Test retrieving summaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = SummarizationConfig(use_llm=False)
            summarizer = MemorySummarizer(db_path, config=config)

            # Create summaries
            memory_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
            contents = ["Content 1", "Content 2"]
            summarizer.create_summary(
                memory_ids=memory_ids,
                user_id="ou_test",
                original_contents=contents,
                memory_types=["fact", "fact"],
            )

            # Retrieve summaries
            summaries = summarizer.get_summaries("ou_test")

            assert len(summaries) >= 1
            assert all(s.user_id == "ou_test" for s in summaries)

            summarizer.close()

    def test_compress_old_memories(self):
        """Test compressing old memories into summaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = SummarizationConfig(
                use_llm=False,
                min_memories_for_batching=2,
                age_threshold_days=30,
                priority_threshold=40
            )
            summarizer = MemorySummarizer(db_path, config=config)

            # Create test memories
            from agent.memory_database import MemoryDatabase, Memory

            db = MemoryDatabase(db_path, "ou_test")

            old_time = int(time.time()) - (60 * 86400)  # 60 days old
            for i in range(3):
                memory = Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="ou_test",
                    content=f"Old memory {i} with some content",
                    memory_type="fact",
                    priority=20,
                    created_at=old_time
                )
                db.insert(memory)

            db.close()

            # Compress memories
            result = summarizer.compress_old_memories("ou_test")

            assert result["status"] == "success"
            assert result["memories_processed"] == 3
            assert result["summaries_created"] >= 1

            summarizer.close()

    def test_expand_summary(self):
        """Test expanding a summary back to original form."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = SummarizationConfig(use_llm=False)
            summarizer = MemorySummarizer(db_path, config=config)

            # Create a summary
            original_content = "This is the original memory content that was summarized."
            memory_ids = [str(uuid.uuid4())]

            summary = summarizer.create_summary(
                memory_ids=memory_ids,
                user_id="ou_test",
                original_contents=[original_content],
                memory_types=["fact"],
            )

            # Expand summary
            expanded = summarizer.expand_summary(summary.summary_id)

            assert expanded is not None
            assert original_content in expanded["original_content"]
            assert "summary" in expanded

            summarizer.close()

    def test_close(self):
        """Test closing the summarizer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            summarizer = MemorySummarizer(db_path)
            summarizer.close()
            # Should not raise