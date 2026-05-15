"""
Memory Retriever - Semantic search for memories.

Provides multi-stage retrieval:
1. Keyword search (exact match)
2. Semantic search (vector similarity)
3. Tag-based search

Results are merged, ranked, and returned with relevance scores.
"""

import json
import time
import logging
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set
from dataclasses import dataclass, field

from agent.memory_database import MemoryDatabase, Memory
from agent.embedding_service import (
    EmbeddingService, EmbeddingConfig, EmbeddingResult,
    cosine_similarity, normalize_vector
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievedMemory:
    """A memory retrieved from search, with relevance scoring."""
    memory: Memory
    relevance_score: float = 0.0
    match_type: str = ""  # 'keyword' | 'semantic' | 'tag' | 'combined'
    highlights: List[str] = field(default_factory=list)


@dataclass
class RetrievalConfig:
    """Configuration for memory retrieval."""
    # Semantic search
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"  # 'openai', 'anthropic', 'custom'
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None
    min_similarity: float = 0.5  # Minimum cosine similarity threshold

    # Search limits
    keyword_limit: int = 10
    semantic_limit: int = 10
    tag_limit: int = 10
    final_limit: int = 5  # Final results to return

    # Scoring weights
    keyword_weight: float = 0.3
    semantic_weight: float = 0.5
    tag_weight: float = 0.2

    # Auto-tagging
    auto_tag_enabled: bool = True
    auto_tag_threshold: float = 0.8


class MemoryRetriever:
    """
    Multi-stage memory retrieval with semantic search.

    Features:
    - Keyword search with exact matching
    - Semantic search with vector embeddings
    - Tag-based filtering
    - Configurable relevance scoring
    - Auto-tagging on insert

    Usage:
        retriever = MemoryRetriever(db, config)
        results = retriever.retrieve("What does user prefer?", user_id="ou_user")
        for result in results:
            print(f"{result.memory.content} (score: {result.relevance_score})")
    """

    def __init__(
        self,
        db: MemoryDatabase,
        config: Optional[RetrievalConfig] = None
    ):
        self.db = db
        self.config = config or RetrievalConfig()
        self._embedding_service: Optional[EmbeddingService] = None
        self._initialized = False

    def _ensure_embedding_service(self) -> EmbeddingService:
        """Lazily initialize embedding service."""
        if self._embedding_service is None:
            emb_config = EmbeddingConfig(
                provider=self.config.embedding_provider,
                model=self.config.embedding_model,
                api_key=self.config.embedding_api_key,
                base_url=self.config.embedding_base_url,
            )
            self._embedding_service = EmbeddingService(emb_config)
        return self._embedding_service

    def retrieve(
        self,
        query: str,
        user_id: str,
        scope: Optional[List[str]] = None,
        memory_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[RetrievedMemory]:
        """
        Retrieve relevant memories for a query.

        Args:
            query: User query text
            user_id: User ID for isolation
            scope: Filter by scope (default: ['user', 'project', 'global'])
            memory_type: Filter by memory type
            tags: Filter by tags (AND logic)
            limit: Maximum results (default: config.final_limit)

        Returns:
            List of RetrievedMemory sorted by relevance score
        """
        if not query or not query.strip():
            return []

        limit = limit or self.config.final_limit
        scope = scope or ["user", "project", "global"]

        # Extract keywords from query
        keywords = self._extract_keywords(query)

        # Stage 1: Keyword search
        keyword_results = self._search_by_keywords(
            keywords=keywords,
            user_id=user_id,
            scope=scope,
            memory_type=memory_type,
            tags=tags,
            limit=self.config.keyword_limit
        )

        # Stage 2: Semantic search (if embedding service available)
        semantic_results = []
        try:
            semantic_results = self._search_by_semantic(
                query=query,
                user_id=user_id,
                scope=scope,
                memory_type=memory_type,
                limit=self.config.semantic_limit
            )
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")

        # Stage 3: Tag-based search
        tag_results = []
        if tags or self.config.auto_tag_enabled:
            search_tags = tags or keywords
            tag_results = self._search_by_tags(
                tags=search_tags,
                user_id=user_id,
                scope=scope,
                memory_type=memory_type,
                limit=self.config.tag_limit
            )

        # Merge and rank results
        merged = self._merge_and_rank(
            keyword_results,
            semantic_results,
            tag_results,
            keywords=keywords
        )

        # Apply limit and filter by minimum similarity
        final_results = [
            r for r in merged
            if r.relevance_score >= self.config.min_similarity
        ][:limit]

        # Update access statistics
        for result in final_results:
            self.db.increment_access_count(result.memory.memory_id)

        return final_results

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from query text."""
        import re

        # Simple keyword extraction
        # Remove punctuation and split
        words = re.findall(r'\b[a-zA-Z一-鿿]+\b', text.lower())

        # Filter short words and common stop words
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'can',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she',
            'it', 'we', 'they', 'what', 'which', 'who', 'whom', 'whose',
            'where', 'when', 'why', 'how', '的', '了', '是', '在', '和',
            '有', '我', '你', '他', '她', '它', '们', '这', '那', '什么',
            '怎么', '如何', '为什么'
        }

        keywords = [w for w in words if len(w) >= 2 and w not in stop_words]
        return list(set(keywords))  # Deduplicate

    def _search_by_keywords(
        self,
        keywords: List[str],
        user_id: str,
        scope: List[str],
        memory_type: Optional[str],
        tags: Optional[List[str]],
        limit: int
    ) -> List[RetrievedMemory]:
        """Stage 1: Keyword search."""
        if not keywords:
            return []

        results = self.db.search_by_keywords(
            keywords=keywords,
            user_id=user_id,
            scope=scope,
            limit=limit
        )

        retrieved = []
        for memory in results:
            # Calculate keyword match score
            content_lower = memory.content.lower()
            matches = sum(1 for kw in keywords if kw.lower() in content_lower)
            score = matches / len(keywords) if keywords else 0

            retrieved.append(RetrievedMemory(
                memory=memory,
                relevance_score=score * self.config.keyword_weight,
                match_type="keyword",
                highlights=[kw for kw in keywords if kw.lower() in content_lower]
            ))

        return retrieved

    def _search_by_semantic(
        self,
        query: str,
        user_id: str,
        scope: List[str],
        memory_type: Optional[str],
        limit: int
    ) -> List[RetrievedMemory]:
        """Stage 2: Semantic search using embeddings."""
        service = self._ensure_embedding_service()

        # Embed query
        query_embedding_result = service.embed(query)
        query_embedding = query_embedding_result.embedding

        # Get all memories (for now, we fetch and filter)
        # TODO: Implement SQL-based similarity search for efficiency
        memories = self.db.search(
            user_id=user_id,
            scope=scope,
            memory_type=memory_type,
            limit=500  # Limit for demo
        )

        # Get embeddings for memory contents
        contents = [m.content for m in memories]
        if not contents:
            return []

        # Batch embed (with caching)
        embedding_results = service.embed_batch(contents)

        # Calculate similarities
        retrieved = []
        for i, memory in enumerate(memories):
            embedding = embedding_results[i].embedding
            similarity = cosine_similarity(query_embedding, embedding)

            if similarity >= self.config.min_similarity:
                retrieved.append(RetrievedMemory(
                    memory=memory,
                    relevance_score=similarity * self.config.semantic_weight,
                    match_type="semantic",
                    highlights=[f"similarity: {similarity:.2f}"]
                ))

        # Sort by similarity
        retrieved.sort(key=lambda x: x.relevance_score, reverse=True)

        return retrieved[:limit]

    def _search_by_tags(
        self,
        tags: List[str],
        user_id: str,
        scope: List[str],
        memory_type: Optional[str],
        limit: int
    ) -> List[RetrievedMemory]:
        """Stage 3: Tag-based search."""
        if not tags:
            return []

        memories = self.db.search(
            user_id=user_id,
            scope=scope,
            memory_type=memory_type,
            tags=tags,
            limit=limit
        )

        retrieved = []
        for memory in memories:
            # Calculate tag match score
            memory_tags = set(memory.tags)
            matches = len(memory_tags.intersection(set(tags)))
            score = matches / len(tags) if tags else 0

            if score > 0:
                retrieved.append(RetrievedMemory(
                    memory=memory,
                    relevance_score=score * self.config.tag_weight,
                    match_type="tag",
                    highlights=[t for t in tags if t in memory_tags]
                ))

        return retrieved

    def _merge_and_rank(
        self,
        keyword_results: List[RetrievedMemory],
        semantic_results: List[RetrievedMemory],
        tag_results: List[RetrievedMemory],
        keywords: List[str]
    ) -> List[RetrievedMemory]:
        """Merge results from all stages and re-rank."""
        seen: Dict[str, RetrievedMemory] = {}

        # Add all results, combining scores for same memory
        for results in [keyword_results, semantic_results, tag_results]:
            for result in results:
                mem_id = result.memory.memory_id
                if mem_id in seen:
                    # Combine scores
                    seen[mem_id].relevance_score += result.relevance_score
                    # Combine match types
                    if result.match_type not in seen[mem_id].match_type:
                        seen[mem_id].match_type += f"+{result.match_type}"
                    # Combine highlights
                    for h in result.highlights:
                        if h not in seen[mem_id].highlights:
                            seen[mem_id].highlights.append(h)
                else:
                    seen[mem_id] = result

        # Sort by combined score
        merged = sorted(seen.values(), key=lambda x: x.relevance_score, reverse=True)

        # Re-score to 0-1 range
        if merged:
            max_score = merged[0].relevance_score
            if max_score > 0:
                for result in merged:
                    result.relevance_score = result.relevance_score / max_score

        return merged

    def auto_tag_memory(self, content: str) -> List[str]:
        """
        Automatically generate tags for memory content.

        Args:
            content: Memory content text

        Returns:
            List of suggested tags
        """
        if not self.config.auto_tag_enabled:
            return []

        # Simple tag extraction based on keywords
        keywords = self._extract_keywords(content)

        # Filter for likely tags (nouns, important terms)
        # This is a simplified version - could use NER or LLM
        potential_tags = [kw for kw in keywords if len(kw) >= 3]

        return potential_tags[:5]  # Limit to 5 tags


def format_retrieved_memories(
    results: List[RetrievedMemory],
    include_scores: bool = True,
    include_source: bool = True
) -> str:
    """
    Format retrieved memories as a text block for LLM context injection.

    Args:
        results: List of RetrievedMemory
        include_scores: Include relevance scores
        include_source: Include source metadata

    Returns:
        Formatted text block
    """
    if not results:
        return "No relevant memories found."

    lines = ["# Retrieved Memories"]
    lines.append("")

    for i, result in enumerate(results, 1):
        memory = result.memory
        lines.append(f"## {i}. {memory.content}")
        lines.append("")

        if include_scores:
            lines.append(f"- **Relevance**: {result.relevance_score:.2f}")
            lines.append(f"- **Match Type**: {result.match_type}")

        if result.highlights:
            lines.append(f"- **Matched**: {', '.join(result.highlights)}")

        if include_source:
            from datetime import datetime
            created = datetime.fromtimestamp(memory.created_at).strftime("%Y-%m-%d")
            lines.append(f"- **Type**: {memory.memory_type}")
            lines.append(f"- **Created**: {created}")

        if memory.tags:
            lines.append(f"- **Tags**: {', '.join(memory.tags)}")

        lines.append("")

    return "\n".join(lines)