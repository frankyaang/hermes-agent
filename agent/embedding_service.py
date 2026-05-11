"""
Embedding Service - Provides text vectorization for semantic search.

Supports multiple embedding providers:
- OpenAI (text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002)
- Anthropic (via API)
- Custom/OpenRouter compatible endpoints

The embedding service is used by MemoryRetriever to create vector representations
of memory content for semantic similarity search.
"""

import json
import time
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class EmbeddingModel(Enum):
    """Supported embedding models."""
    TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"
    TEXT_EMBEDDING_3_LARGE = "text-embedding-3-large"
    TEXT_EMBEDDING_ADA_002 = "text-embedding-ada-002"

    # Dimensions
    @property
    def dimensions(self) -> int:
        models = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return models.get(self.value, 1536)


@dataclass
class EmbeddingResult:
    """Result of embedding operation."""
    embedding: List[float]
    model: str
    tokens_used: int = 0
    cached: bool = False


@dataclass
class EmbeddingConfig:
    """Configuration for embedding service."""
    provider: str = "openai"  # 'openai', 'anthropic', 'custom'
    model: str = "text-embedding-3-small"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    batch_size: int = 100
    max_retries: int = 3
    timeout: int = 60
    # Redis cache settings
    redis_url: Optional[str] = None
    redis_ttl: int = 604800  # 7 days default

    @property
    def dimensions(self) -> int:
        return EmbeddingModel(self.model).dimensions


class EmbeddingService:
    """
    Unified embedding service supporting multiple providers.

    Features:
    - Memory LRU cache
    - Optional Redis distributed cache
    - Batch embedding support

    Usage:
        service = EmbeddingService(config)
        result = service.embed("Hello world")
        results = service.embed_batch(["Hello", "World"])
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self._cache: Dict[str, List[float]] = {}
        self._cache_size = 0
        self._max_cache_size = 10000
        self._redis_cache = None

        # Initialize Redis cache if configured
        if self.config.redis_url:
            try:
                from agent.redis_embedding_cache import RedisEmbeddingCache
                self._redis_cache = RedisEmbeddingCache(
                    redis_url=self.config.redis_url,
                    ttl_seconds=self.config.redis_ttl
                )
                logger.info(f"Redis cache enabled: {self.config.redis_url}")
            except ImportError:
                logger.warning("redis package not installed, skipping Redis cache")

    def embed(self, text: str) -> EmbeddingResult:
        """
        Embed a single text.

        Args:
            text: Text to embed

        Returns:
            EmbeddingResult with embedding vector
        """
        # Check cache (memory first, then Redis)
        cache_key = self._make_cache_key(text)
        cached = self._check_cache(cache_key)
        if cached is not None:
            return EmbeddingResult(
                embedding=cached,
                model=self.config.model,
                cached=True
            )

        # Generate embedding
        if self.config.provider == "openai":
            result = self._embed_openai([text])[0]
        elif self.config.provider == "anthropic":
            result = self._embed_anthropic([text])[0]
        elif self.config.provider == "custom":
            result = self._embed_custom([text])[0]
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")

        # Cache the result
        self._add_to_cache(cache_key, result.embedding)

        return result

    def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """
        Embed multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResult
        """
        if not texts:
            return []

        # Check cache for all texts
        uncached_indices = []
        uncached_texts = []
        results = [None] * len(texts)

        for i, text in enumerate(texts):
            cache_key = self._make_cache_key(text)
            cached = self._check_cache(cache_key)
            if cached is not None:
                results[i] = EmbeddingResult(
                    embedding=cached,
                    model=self.config.model,
                    cached=True
                )
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Embed uncached in batch
        if uncached_texts:
            new_results = self._embed_batch(uncached_texts)

            # Cache and fill results
            for i, text in enumerate(uncached_texts):
                cache_key = self._make_cache_key(text)
                self._add_to_cache(cache_key, new_results[i].embedding)
                results[uncached_indices[i]] = new_results[i]

        return results

    def _embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed batch using appropriate provider."""
        if self.config.provider == "openai":
            return self._embed_openai(texts)
        elif self.config.provider == "anthropic":
            return self._embed_anthropic(texts)
        elif self.config.provider == "custom":
            return self._embed_custom(texts)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")

    def _embed_openai(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed using OpenAI API."""
        import urllib.request
        import urllib.error

        api_key = self.config.api_key or self._get_api_key("OPENAI_API_KEY")
        base_url = self.config.base_url or "https://api.openai.com/v1"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        body = {
            "model": self.config.model,
            "input": texts,
        }

        url = f"{base_url.rstrip('/')}/embeddings"
        data = json.dumps(body).encode("utf-8")

        for attempt in range(self.config.max_retries):
            try:
                req = urllib.request.Request(
                    url, data=data, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                    result = json.loads(resp.read().decode("utf-8"))

                results = []
                for item in result["data"]:
                    results.append(EmbeddingResult(
                        embedding=item["embedding"],
                        model=self.config.model,
                        tokens_used=result.get("usage", {}).get("total_tokens", 0)
                    ))
                return results

            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise

        raise RuntimeError("Failed to embed after retries")

    def _embed_anthropic(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed using Anthropic API (via OpenAI-compatible endpoint or custom)."""
        # Anthropic doesn't have a native embeddings API, use custom endpoint
        # or OpenRouter which supports Anthropic embeddings
        if self.config.base_url:
            return self._embed_custom(texts)

        # Fallback to OpenAI for Anthropic (for demo)
        return self._embed_openai(texts)

    def _embed_custom(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed using custom/OpenRouter compatible endpoint."""
        import urllib.request
        import urllib.error

        api_key = self.config.api_key or self._get_api_key("OPENROUTER_API_KEY")
        base_url = self.config.base_url or "https://openrouter.ai/api/v1"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        body = {
            "model": self.config.model,
            "input": texts,
        }

        url = f"{base_url.rstrip('/')}/embeddings"
        data = json.dumps(body).encode("utf-8")

        for attempt in range(self.config.max_retries):
            try:
                req = urllib.request.Request(
                    url, data=data, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                    result = json.loads(resp.read().decode("utf-8"))

                results = []
                for item in result["data"]:
                    results.append(EmbeddingResult(
                        embedding=item["embedding"],
                        model=item.get("model", self.config.model),
                        tokens_used=result.get("usage", {}).get("total_tokens", 0)
                    ))
                return results

            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < self.config.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

        raise RuntimeError("Failed to embed after retries")

    def _get_api_key(self, env_var: str) -> str:
        """Get API key from environment."""
        import os
        key = os.environ.get(env_var)
        if not key:
            raise ValueError(f"API key not found: {env_var}")
        return key

    def _make_cache_key(self, text: str) -> str:
        """Create cache key for text."""
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    def _check_cache(self, cache_key: str) -> Optional[List[float]]:
        """
        Check all cache layers for embedding.

        Order: Memory cache -> Redis cache

        Args:
            cache_key: Cache key (content hash)

        Returns:
            Embedding if found, None otherwise
        """
        # Check memory cache first (fastest)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check Redis cache
        if self._redis_cache is not None:
            redis_result = self._redis_cache.get(cache_key)
            if redis_result is not None:
                # Promote to memory cache
                self._add_to_cache(cache_key, redis_result)
                return redis_result

        return None

    def _add_to_cache(self, key: str, embedding: List[float]) -> None:
        """Add embedding to all cache layers."""
        # Add to memory cache
        if self._cache_size >= self._max_cache_size:
            # Remove oldest entries (simple FIFO for now)
            keys_to_remove = list(self._cache.keys())[:1000]
            for k in keys_to_remove:
                del self._cache[k]
            self._cache_size -= len(keys_to_remove)

        self._cache[key] = embedding
        self._cache_size += 1

        # Add to Redis cache if available
        if self._redis_cache is not None:
            self._redis_cache.set(key, embedding)

    def clear_cache(self) -> None:
        """Clear all cache layers."""
        self._cache.clear()
        self._cache_size = 0

        if self._redis_cache is not None:
            self._redis_cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics from all layers."""
        stats = {
            "memory": {
                "entries": self._cache_size,
                "max_size": self._max_cache_size
            }
        }

        if self._redis_cache is not None:
            stats["redis"] = self._redis_cache.get_stats()

        return stats


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        a: First vector
        b: Second vector

    Returns:
        Cosine similarity score (-1 to 1)
    """
    if len(a) != len(b):
        raise ValueError("Vectors must have same dimension")

    dot_product = sum(a_i * b_i for a_i, b_i in zip(a, b))
    norm_a = sum(a_i * a_i for a_i in a) ** 0.5
    norm_b = sum(b_i * b_i for b_i in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def euclidean_distance(a: List[float], b: List[float]) -> float:
    """
    Calculate Euclidean distance between two vectors.

    Args:
        a: First vector
        b: Second vector

    Returns:
        Euclidean distance
    """
    if len(a) != len(b):
        raise ValueError("Vectors must have same dimension")

    return sum((a_i - b_i) ** 2 for a_i, b_i in zip(a, b)) ** 0.5


def normalize_vector(v: List[float]) -> List[float]:
    """
    Normalize a vector to unit length.

    Args:
        v: Vector to normalize

    Returns:
        Normalized vector
    """
    norm = sum(x * x for x in v) ** 0.5
    if norm == 0:
        return v
    return [x / norm for x in v]