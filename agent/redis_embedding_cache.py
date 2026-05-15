"""
Redis-backed distributed embedding cache.

Provides a Redis layer for sharing embeddings across multiple instances,
reducing API calls and improving consistency.

Usage:
    cache = RedisEmbeddingCache("redis://localhost:6379")
    cache.set("hash123", [0.1, 0.2, 0.3])
    embedding = cache.get("hash123")
"""

import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class RedisEmbeddingCache:
    """
    Distributed embedding cache using Redis.

    Features:
    - TTL-based expiration (default 7 days)
    - Batch operations for efficiency
    - Statistics tracking
    - Connection health checks
    - Fallback support for unavailable Redis
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        ttl_seconds: int = 604800,  # 7 days
        key_prefix: str = "embed:",
        enable_fallback: bool = True
    ):
        """
        Initialize Redis embedding cache.

        Args:
            redis_url: Redis connection URL
            ttl_seconds: Time-to-live for cache entries
            key_prefix: Prefix for all cache keys
            enable_fallback: Enable in-memory fallback when Redis unavailable
        """
        self.redis_url = redis_url
        self.ttl = ttl_seconds
        self.key_prefix = key_prefix
        self.enable_fallback = enable_fallback
        self._redis = None
        self._fallback_cache: Dict[str, List[float]] = {}
        self._fallback_hits = 0
        self._fallback_misses = 0

    def _get_redis(self):
        """Lazily initialize Redis connection."""
        if self._redis is None:
            try:
                import redis
                self._redis = redis.from_url(
                    self.redis_url,
                    decode_responses=False,  # We need bytes for embeddings
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                self._redis.ping()
                logger.info(f"Redis connected: {self.redis_url}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Using fallback cache.")
                self._redis = None
        return self._redis

    @property
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self._get_redis() is not None

    def get(self, content_hash: str) -> Optional[List[float]]:
        """
        Get cached embedding by content hash.

        Args:
            content_hash: SHA256 hash of the content

        Returns:
            Embedding vector or None if not found/expired
        """
        key = f"{self.key_prefix}{content_hash}"

        # Try Redis first
        redis_client = self._get_redis()
        if redis_client:
            try:
                data = redis_client.get(key)
                if data:
                    # Reset TTL on access
                    redis_client.expire(key, self.ttl)
                    return self._deserialize(data)
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")

        # Fallback to memory cache
        if self.enable_fallback and content_hash in self._fallback_cache:
            self._fallback_hits += 1
            return self._fallback_cache[content_hash]

        self._fallback_misses += 1
        return None

    def set(self, content_hash: str, embedding: List[float]) -> bool:
        """
        Cache an embedding with TTL.

        Args:
            content_hash: SHA256 hash of the content
            embedding: The embedding vector

        Returns:
            True if cached successfully
        """
        key = f"{self.key_prefix}{content_hash}"

        # Try Redis first
        redis_client = self._get_redis()
        if redis_client:
            try:
                data = self._serialize(embedding)
                redis_client.setex(key, self.ttl, data)
                return True
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")

        # Fallback to memory cache
        if self.enable_fallback:
            self._fallback_cache[content_hash] = embedding
            return True

        return False

    def get_batch(self, content_hashes: List[str]) -> Dict[str, List[float]]:
        """
        Batch get multiple embeddings.

        Args:
            content_hashes: List of content hashes

        Returns:
            Dict mapping content_hash to embedding (only found entries)
        """
        if not content_hashes:
            return {}

        result = {}
        redis_client = self._get_redis()

        if redis_client:
            try:
                keys = [f"{self.key_prefix}{h}" for h in content_hashes]
                # Use pipeline for batch efficiency
                pipe = redis_client.pipeline()
                for key in keys:
                    pipe.get(key)
                values = pipe.execute()

                # Track which hashes were found
                found_hashes = []
                for i, value in enumerate(values):
                    if value:
                        result[content_hashes[i]] = self._deserialize(value)
                        found_hashes.append(content_hashes[i])

                # Batch reset TTL
                if found_hashes:
                    pipe = redis_client.pipeline()
                    for h in found_hashes:
                        pipe.expire(f"{self.key_prefix}{h}", self.ttl)
                    pipe.execute()

            except Exception as e:
                logger.warning(f"Redis batch get failed: {e}")

        # Fill missing from fallback
        if self.enable_fallback:
            for h in content_hashes:
                if h not in result and h in self._fallback_cache:
                    result[h] = self._fallback_cache[h]
                    self._fallback_hits += 1
                elif h not in result:
                    self._fallback_misses += 1

        return result

    def set_batch(self, items: Dict[str, List[float]]) -> int:
        """
        Batch set multiple embeddings.

        Args:
            items: Dict mapping content_hash to embedding

        Returns:
            Number of items cached successfully
        """
        if not items:
            return 0

        count = 0
        redis_client = self._get_redis()

        if redis_client:
            try:
                pipe = redis_client.pipeline()
                for content_hash, embedding in items.items():
                    key = f"{self.key_prefix}{content_hash}"
                    data = self._serialize(embedding)
                    pipe.setex(key, self.ttl, data)
                pipe.execute()
                count = len(items)
            except Exception as e:
                logger.warning(f"Redis batch set failed: {e}")

        # Fallback
        if self.enable_fallback:
            self._fallback_cache.update(items)
            count = len(items)

        return count

    def delete(self, content_hash: str) -> bool:
        """
        Delete a cached embedding.

        Args:
            content_hash: Content hash to delete

        Returns:
            True if deleted successfully
        """
        key = f"{self.key_prefix}{content_hash}"

        redis_client = self._get_redis()
        deleted = False

        if redis_client:
            try:
                deleted = redis_client.delete(key) > 0
            except Exception as e:
                logger.warning(f"Redis delete failed: {e}")

        # Also remove from fallback
        if content_hash in self._fallback_cache:
            del self._fallback_cache[content_hash]
            deleted = True

        return deleted

    def delete_batch(self, content_hashes: List[str]) -> int:
        """
        Batch delete multiple embeddings.

        Args:
            content_hashes: List of content hashes to delete

        Returns:
            Number of items deleted
        """
        if not content_hashes:
            return 0

        count = 0
        redis_client = self._get_redis()

        if redis_client:
            try:
                keys = [f"{self.key_prefix}{h}" for h in content_hashes]
                count = redis_client.delete(*keys)
            except Exception as e:
                logger.warning(f"Redis batch delete failed: {e}")

        # Also remove from fallback
        if self.enable_fallback:
            for h in content_hashes:
                if h in self._fallback_cache:
                    del self._fallback_cache[h]
                    count += 1

        return count

    def clear(self) -> int:
        """
        Clear all cached embeddings.

        Returns:
            Number of entries cleared
        """
        count = 0
        redis_client = self._get_redis()

        if redis_client:
            try:
                # Use SCAN for production safety (don't use KEYS)
                cursor = 0
                deleted_keys = []
                while True:
                    cursor, keys = redis_client.scan(
                        cursor=cursor,
                        match=f"{self.key_prefix}*",
                        count=100
                    )
                    if keys:
                        deleted_keys.extend(keys)
                    if cursor == 0:
                        break

                if deleted_keys:
                    count = redis_client.delete(*deleted_keys)
            except Exception as e:
                logger.warning(f"Redis clear failed: {e}")

        # Clear fallback
        if self.enable_fallback:
            count += len(self._fallback_cache)
            self._fallback_cache.clear()

        return count

    def clear_expired(self) -> int:
        """
        Clear all expired entries (Redis handles this via TTL).

        For fallback cache, removes entries older than TTL.
        """
        count = 0
        # Redis handles expiration automatically via TTL

        # For fallback, we don't track creation time
        # User can call clear() to reset if needed
        if self.enable_fallback and len(self._fallback_cache) > 10000:
            # Auto-evict if too large
            keys_to_remove = list(self._fallback_cache.keys())[:1000]
            for k in keys_to_remove:
                del self._fallback_cache[k]
            count = len(keys_to_remove)

        return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        stats = {
            "available": self.is_available,
            "redis_url": self.redis_url,
            "ttl_seconds": self.ttl,
            "key_prefix": self.key_prefix,
            "fallback_enabled": self.enable_fallback,
            "fallback_size": len(self._fallback_cache),
            "fallback_hits": self._fallback_hits,
            "fallback_misses": self._fallback_misses,
        }

        redis_client = self._get_redis()
        if redis_client:
            try:
                info = redis_client.info("stats")
                stats.update({
                    "redis_connected": True,
                    "redis_keyspace_hits": info.get("keyspace_hits", 0),
                    "redis_keyspace_misses": info.get("keyspace_misses", 0),
                })

                # Count matching keys
                cursor = 0
                count = 0
                while True:
                    cursor, keys = redis_client.scan(
                        cursor=cursor,
                        match=f"{self.key_prefix}*",
                        count=100
                    )
                    count += len(keys)
                    if cursor == 0:
                        break
                stats["redis_entries"] = count

            except Exception as e:
                stats["redis_connected"] = False
                stats["redis_error"] = str(e)

        return stats

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the cache.

        Returns:
            Dict with health status
        """
        result = {
            "healthy": False,
            "latency_ms": None,
            "error": None,
        }

        redis_client = self._get_redis()
        if not redis_client:
            result["error"] = "Redis not connected"
            return result

        try:
            import time
            start = time.time()
            redis_client.ping()
            result["latency_ms"] = int((time.time() - start) * 1000)
            result["healthy"] = True
        except Exception as e:
            result["error"] = str(e)

        return result

    def _serialize(self, embedding: List[float]) -> bytes:
        """Serialize embedding to bytes for Redis storage."""
        return json.dumps(embedding).encode('utf-8')

    def _deserialize(self, data: bytes) -> List[float]:
        """Deserialize bytes to embedding vector."""
        return json.loads(data.decode('utf-8'))

    def __enter__(self):
        """Context manager entry."""
        self._get_redis()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._redis:
            self._redis.close()
            self._redis = None


def create_redis_cache(
    redis_url: Optional[str] = None,
    ttl_seconds: int = 604800
) -> RedisEmbeddingCache:
    """
    Factory function to create Redis cache.

    Args:
        redis_url: Redis URL (reads from env if not provided)
        ttl_seconds: Cache TTL

    Returns:
        RedisEmbeddingCache instance
    """
    import os

    if not redis_url:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    return RedisEmbeddingCache(redis_url=redis_url, ttl_seconds=ttl_seconds)