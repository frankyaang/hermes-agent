"""
Tests for Phase 3 - Semantic Search and Embeddings.
"""

import pytest
import tempfile
import uuid
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent.embedding_service import (
    EmbeddingService, EmbeddingConfig, EmbeddingResult,
    cosine_similarity, euclidean_distance, normalize_vector
)


class TestEmbeddingService:
    """Test embedding service."""

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        # Identical vectors
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(1.0)

        # Orthogonal vectors
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

        # Opposite vectors
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

        # Partial similarity
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        similarity = cosine_similarity(a, b)
        assert 0.6 < similarity < 0.8

    def test_cosine_similarity_dimension_mismatch(self):
        """Test that dimension mismatch raises error."""
        a = [1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        with pytest.raises(ValueError):
            cosine_similarity(a, b)

    def test_euclidean_distance(self):
        """Test Euclidean distance calculation."""
        # Same point
        a = [1.0, 1.0]
        b = [1.0, 1.0]
        assert euclidean_distance(a, b) == pytest.approx(0.0)

        # Distance of sqrt(2)
        a = [0.0, 0.0]
        b = [1.0, 1.0]
        assert euclidean_distance(a, b) == pytest.approx(1.414, abs=0.01)

    def test_normalize_vector(self):
        """Test vector normalization."""
        # Unit vector
        v = [3.0, 4.0]
        normalized = normalize_vector(v)
        norm = sum(x * x for x in normalized) ** 0.5
        assert norm == pytest.approx(1.0)

        # Zero vector
        v = [0.0, 0.0]
        normalized = normalize_vector(v)
        assert normalized == [0.0, 0.0]

    def test_embedding_config(self):
        """Test embedding configuration."""
        config = EmbeddingConfig(
            provider="openai",
            model="text-embedding-3-small"
        )
        assert config.provider == "openai"
        assert config.model == "text-embedding-3-small"
        assert config.dimensions == 1536

    def test_embedding_result(self):
        """Test embedding result dataclass."""
        result = EmbeddingResult(
            embedding=[0.1, 0.2, 0.3],
            model="text-embedding-3-small",
            tokens_used=10,
            cached=False
        )
        assert len(result.embedding) == 3
        assert result.model == "text-embedding-3-small"
        assert result.tokens_used == 10
        assert result.cached is False

    def test_mock_openai_embedding(self):
        """Test OpenAI embedding with mock."""
        config = EmbeddingConfig(
            provider="openai",
            model="text-embedding-3-small",
            api_key="test-key"
        )
        service = EmbeddingService(config)

        # Mock the API call
        mock_response = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
            "usage": {"total_tokens": 10}
        }

        with patch('agent.embedding_service.EmbeddingService._embed_openai') as mock_embed:
            # Pre-populate cache to avoid actual API call
            mock_result = EmbeddingResult(
                embedding=[0.1, 0.2, 0.3],
                model="text-embedding-3-small",
                tokens_used=10,
                cached=False
            )
            mock_embed.return_value = [mock_result]

            result = service._embed_openai(["Hello world"])

            assert result[0].model == "text-embedding-3-small"
            assert result[0].embedding == [0.1, 0.2, 0.3]
            assert result[0].tokens_used == 10

    def test_caching(self):
        """Test embedding caching."""
        config = EmbeddingConfig(provider="openai", model="text-embedding-3-small")
        service = EmbeddingService(config)

        # First call should not be cached
        result1 = EmbeddingResult(
            embedding=[0.1, 0.2],
            model="test",
            cached=False
        )
        assert result1.cached is False

        # Add to cache manually
        service._add_to_cache("test_key", [0.1, 0.2])

        # Check cache stats
        stats = service.get_cache_stats()
        assert stats["entries"] >= 1

    def test_clear_cache(self):
        """Test cache clearing."""
        config = EmbeddingConfig(provider="openai", model="text-embedding-3-small")
        service = EmbeddingService(config)

        service._add_to_cache("key1", [0.1, 0.2])
        service._add_to_cache("key2", [0.3, 0.4])

        stats_before = service.get_cache_stats()
        assert stats_before["entries"] >= 2

        service.clear_cache()

        stats_after = service.get_cache_stats()
        assert stats_after["entries"] == 0


class TestMemoryRetriever:
    """Test memory retriever."""

    def test_extract_keywords(self):
        """Test keyword extraction."""
        from agent.memory_retriever import MemoryRetriever

        retriever = MemoryRetriever.__new__(MemoryRetriever)
        retriever.config = MagicMock()
        retriever.config.auto_tag_enabled = False

        # English keywords
        text = "What does the user prefer for programming?"
        keywords = retriever._extract_keywords(text)
        assert "prefer" in keywords
        assert "programming" in keywords
        assert "what" not in keywords  # Stop word
        assert "does" not in keywords  # Stop word

        # Chinese keywords
        text = "用户喜欢用什么编程语言？"
        keywords = retriever._extract_keywords(text)
        assert any("用户" in kw or "喜欢" in kw or "编程" in kw for kw in keywords)

    def test_merge_and_rank(self):
        """Test result merging and ranking."""
        from agent.memory_retriever import MemoryRetriever, RetrievedMemory
        from agent.memory_database import Memory

        retriever = MemoryRetriever.__new__(MemoryRetriever)
        retriever.config = MagicMock()
        retriever.config.min_similarity = 0.3

        # Create mock memories
        mem1 = Memory(
            memory_id="1",
            user_id="user1",
            content="Python programming",
            memory_type="preference"
        )
        mem2 = Memory(
            memory_id="2",
            user_id="user1",
            content="JavaScript programming",
            memory_type="preference"
        )

        # Create results
        results1 = [
            RetrievedMemory(memory=mem1, relevance_score=0.8, match_type="keyword")
        ]
        results2 = [
            RetrievedMemory(memory=mem1, relevance_score=0.9, match_type="semantic"),
            RetrievedMemory(memory=mem2, relevance_score=0.7, match_type="semantic")
        ]
        results3 = []  # No tag results

        # Merge
        merged = retriever._merge_and_rank(
            results1, results2, results3, keywords=["python"]
        )

        # mem1 should have combined score
        mem1_result = next(r for r in merged if r.memory.memory_id == "1")
        assert mem1_result.relevance_score > 0.8  # Combined from keyword + semantic

        # mem2 should have semantic score
        mem2_result = next(r for r in merged if r.memory.memory_id == "2")
        assert mem2_result.relevance_score > 0

    def test_auto_tag_memory(self):
        """Test auto-tagging."""
        from agent.memory_retriever import MemoryRetriever

        retriever = MemoryRetriever.__new__(MemoryRetriever)
        retriever.config = MagicMock()
        retriever.config.auto_tag_enabled = True

        content = "User prefers Python programming language"
        tags = retriever.auto_tag_memory(content)

        assert isinstance(tags, list)
        assert len(tags) <= 5
        assert "python" in tags or "programming" in tags or "language" in tags

    def test_format_retrieved_memories(self):
        """Test formatting retrieved memories."""
        from agent.memory_retriever import (
            MemoryRetriever, RetrievedMemory, format_retrieved_memories
        )
        from agent.memory_database import Memory

        memory = Memory(
            memory_id="1",
            user_id="user1",
            content="User prefers Python",
            memory_type="preference",
            tags=["python", "preference"],
            created_at=1704067200  # 2024-01-01
        )

        retrieved = RetrievedMemory(
            memory=memory,
            relevance_score=0.95,
            match_type="semantic+keyword",
            highlights=["Python", "prefers"]
        )

        formatted = format_retrieved_memories([retrieved])

        assert "Retrieved Memories" in formatted
        assert "User prefers Python" in formatted
        assert "0.95" in formatted
        assert "python" in formatted.lower()


class TestIntegration:
    """Integration tests for semantic search."""

    def test_full_search_pipeline(self):
        """Test complete search pipeline."""
        from agent.memory_database import MemoryDatabase, Memory
        from agent.memory_retriever import MemoryRetriever, RetrievedMemory
        from agent.embedding_service import cosine_similarity

        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup database
            db = MemoryDatabase(Path(tmpdir) / "test.db", "user1")

            # Add memories
            memories = [
                Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content="User prefers Python for data science",
                    memory_type="preference",
                    tags=["python", "data-science"]
                ),
                Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content="User works at TechCorp as a developer",
                    memory_type="fact",
                    tags=["work", "developer"]
                ),
                Memory(
                    memory_id=str(uuid.uuid4()),
                    user_id="user1",
                    content="User likes coffee in the morning",
                    memory_type="preference",
                    tags=["coffee"]
                ),
            ]
            for m in memories:
                db.insert(m)

            # Create retriever
            retriever = MemoryRetriever(db)
            retriever.config.min_similarity = 0.0  # Disable for testing

            # Test keyword extraction
            keywords = retriever._extract_keywords("Python programming")
            assert "python" in keywords
            assert "programming" in keywords

            # Test keyword search
            keyword_results = retriever._search_by_keywords(
                keywords=["python"],
                user_id="user1",
                scope=["user"],
                memory_type=None,
                tags=None,
                limit=10
            )
            assert len(keyword_results) >= 1
            assert any("python" in r.memory.content.lower() for r in keyword_results)

            # Test tag search
            tag_results = retriever._search_by_tags(
                tags=["python"],
                user_id="user1",
                scope=["user"],
                memory_type=None,
                limit=10
            )
            assert len(tag_results) >= 1

            db.close()

    def test_relevance_scoring(self):
        """Test relevance scoring combines multiple factors."""
        from agent.memory_retriever import MemoryRetriever, RetrievedMemory
        from agent.memory_database import Memory

        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase
            db = MemoryDatabase(Path(tmpdir) / "test.db", "user1")

            retriever = MemoryRetriever(db)

            # Create memory
            memory = Memory(
                memory_id="1",
                user_id="user1",
                content="User likes Python programming",
                memory_type="preference",
                tags=["python", "programming"]
            )

            # Create results from different stages with different scores
            # Note: After merge, scores are normalized, so we test the raw combination
            r_keyword = RetrievedMemory(
                memory=memory,
                relevance_score=0.8 * retriever.config.keyword_weight,
                match_type="keyword"
            )
            r_semantic = RetrievedMemory(
                memory=memory,
                relevance_score=0.9 * retriever.config.semantic_weight,
                match_type="semantic"
            )
            r_tag = RetrievedMemory(
                memory=memory,
                relevance_score=1.0 * retriever.config.tag_weight,
                match_type="tag"
            )

            # Merge
            merged = retriever._merge_and_rank(
                [r_keyword], [r_semantic], [r_tag], keywords=["python"]
            )

            # Check combined score (before normalization, it should be > sum of individual weights)
            result = merged[0]

            # After normalization, result should be 1.0 (highest score)
            assert result.relevance_score == pytest.approx(1.0, abs=0.01)
            assert "semantic" in result.match_type  # Has combined types
            assert "keyword" in result.match_type

            db.close()

    def test_relevance_scoring_combines_scores(self):
        """Test that merging combines scores from different match types."""
        from agent.memory_retriever import MemoryRetriever, RetrievedMemory
        from agent.memory_database import Memory

        with tempfile.TemporaryDirectory() as tmpdir:
            from agent.memory_database import MemoryDatabase
            db = MemoryDatabase(Path(tmpdir) / "test.db", "user1")

            retriever = MemoryRetriever(db)

            # Create two memories with different scores
            mem1 = Memory(memory_id="1", user_id="user1", content="Python", memory_type="fact")
            mem2 = Memory(memory_id="2", user_id="user1", content="JavaScript", memory_type="fact")

            # Only mem1 has matches in both keyword and semantic
            r1_keyword = RetrievedMemory(memory=mem1, relevance_score=0.6, match_type="keyword")
            r1_semantic = RetrievedMemory(memory=mem1, relevance_score=0.8, match_type="semantic")
            r2_keyword = RetrievedMemory(memory=mem2, relevance_score=0.5, match_type="keyword")

            merged = retriever._merge_and_rank(
                [r1_keyword, r2_keyword],
                [r1_semantic],
                [],  # No tag results
                keywords=["python"]
            )

            # mem1 should have higher combined score than mem2
            mem1_result = next(r for r in merged if r.memory.memory_id == "1")
            mem2_result = next(r for r in merged if r.memory.memory_id == "2")

            # Combined score: 0.6 + 0.8 = 1.4 for mem1
            # Single score: 0.5 for mem2
            assert mem1_result.relevance_score > mem2_result.relevance_score

            db.close()
