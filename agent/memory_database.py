"""
Memory Database - SQLite-backed structured memory storage.

Provides a structured, queryable alternative to plain text MEMORY.md/USER.md files.
Supports per-user isolation, tagging, metadata, and efficient retrieval.
"""

import sqlite3
import json
import hashlib
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple, Callable

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""
    enabled: bool = False
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    min_content_length: int = 10  # Minimum content length to embed

    @property
    def dimensions(self) -> int:
        models = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return models.get(self.model, 1536)


@dataclass
class Memory:
    """Structured memory entry."""
    memory_id: str
    user_id: str
    content: str
    memory_type: str  # 'user_profile' | 'preference' | 'experience' | 'fact' | 'project' | 'task' | 'session'
    scope: str = "user"  # 'user' | 'channel' | 'project' | 'global'
    channel_id: Optional[str] = None
    project_id: Optional[str] = None
    agent_id: Optional[str] = None
    source_session_id: Optional[str] = None
    source_message_id: Optional[str] = None
    source_turn: Optional[int] = None
    confidence: float = 1.0
    priority: int = 50
    importance: str = "normal"  # 'critical' | 'important' | 'normal' | 'low'
    status: str = "active"  # 'active' | 'archived' | 'deleted' | 'conflicted'
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: Optional[int] = None
    access_count: int = 0
    last_accessed_at: Optional[int] = None
    conflict_group_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        """Generate SHA256 hash of content for deduplication."""
        return hashlib.sha256(self.content.encode('utf-8')).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        data = asdict(self)
        # Serialize metadata as JSON
        data['metadata'] = json.dumps(data['metadata'])
        # Remove tags (stored in separate table)
        data.pop('tags', None)
        # Add content_hash
        data['content_hash'] = self.content_hash
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        """Create from dictionary (database row)."""
        # Deserialize metadata
        if isinstance(data.get('metadata'), str):
            data['metadata'] = json.loads(data['metadata'])
        # Remove content_hash (computed property)
        data.pop('content_hash', None)
        # Tags loaded separately
        data.setdefault('tags', [])
        return cls(**data)


@dataclass
class DecayStrategy:
    """
    Adaptive decay strategy based on memory importance.

    Different memory types require different decay rates:
    - Critical memories (user profiles, preferences) decay very slowly
    - Normal memories follow standard decay (90 day halflife)
    - Low importance memories decay quickly
    """

    importance: str = "normal"  # "critical" | "important" | "normal" | "low"

    # Halflife by importance level (days)
    HALFLIFE_MAP = {
        "critical": 365,    # 1 year - very stable
        "important": 180,   # 6 months - stable
        "normal": 90,        # 3 months - standard
        "low": 30,           # 1 month - quick decay
    }

    # Minimum priority floor by importance
    MIN_PRIORITY_MAP = {
        "critical": 30,
        "important": 20,
        "normal": 10,
        "low": 5,
    }

    # Access boost factor per sqrt(access_count)
    ACCESS_BOOST_MAP = {
        "critical": 0.15,
        "important": 0.12,
        "normal": 0.10,
        "low": 0.05,
    }

    @property
    def halflife_days(self) -> int:
        """Get halflife based on importance."""
        return self.HALFLIFE_MAP.get(self.importance, 90)

    @property
    def min_priority(self) -> int:
        """Get minimum priority floor."""
        return self.MIN_PRIORITY_MAP.get(self.importance, 10)

    @property
    def access_boost_factor(self) -> float:
        """Get access boost factor."""
        return self.ACCESS_BOOST_MAP.get(self.importance, 0.10)


class MemoryDatabase:
    """
    SQLite-backed memory storage with structured queries and metadata.

    Features:
    - Per-user isolation via user_id
    - Structured queries (by type, scope, tags, etc.)
    - Metadata support
    - Deduplication via content hash
    - Access tracking
    - Soft deletion (status='archived')
    - Embedding cache (persistent)
    - Memory decay with priority adjustment
    """

    def __init__(
        self,
        db_path: Path,
        user_id: str,
        embedding_config: Optional[EmbeddingConfig] = None,
        embedding_service: Optional[Any] = None
    ):
        """
        Initialize memory database.

        Args:
            db_path: Path to SQLite database file
            user_id: User identifier for isolation
            embedding_config: Configuration for auto-embedding
            embedding_service: Pre-configured embedding service instance
        """
        self.db_path = db_path
        self.user_id = user_id
        self.embedding_config = embedding_config or EmbeddingConfig()
        self._embedding_service = embedding_service
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        self.conn.executescript("""
            -- Main memories table
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                agent_id TEXT,
                channel_id TEXT,
                project_id TEXT,
                scope TEXT NOT NULL DEFAULT 'user',
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                source_message_id TEXT,
                source_session_id TEXT,
                source_turn INTEGER,
                confidence REAL DEFAULT 1.0,
                priority INTEGER DEFAULT 50,
                importance TEXT DEFAULT 'normal',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                expires_at INTEGER,
                status TEXT DEFAULT 'active',
                conflict_group_id TEXT,
                access_count INTEGER DEFAULT 0,
                last_accessed_at INTEGER,
                metadata TEXT,

                UNIQUE(user_id, content_hash, scope)
            );

            CREATE INDEX IF NOT EXISTS idx_memories_user_scope
                ON memories(user_id, scope, status);
            CREATE INDEX IF NOT EXISTS idx_memories_type
                ON memories(memory_type, status);
            CREATE INDEX IF NOT EXISTS idx_memories_channel
                ON memories(channel_id, status);
            CREATE INDEX IF NOT EXISTS idx_memories_project
                ON memories(project_id, status);
            CREATE INDEX IF NOT EXISTS idx_memories_expires
                ON memories(expires_at) WHERE expires_at IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_memories_priority
                ON memories(priority DESC, created_at DESC);

            -- Tags table (many-to-many)
            CREATE TABLE IF NOT EXISTS memory_tags (
                memory_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY(memory_id, tag),
                FOREIGN KEY(memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags(tag);

            -- Audit log table
            CREATE TABLE IF NOT EXISTS memory_audit_log (
                log_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                action TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT,
                timestamp INTEGER NOT NULL,
                details TEXT,
                FOREIGN KEY(memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_audit_log_memory
                ON memory_audit_log(memory_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_log_user
                ON memory_audit_log(user_id, timestamp DESC);

            -- Embedding cache table (persistent)
            CREATE TABLE IF NOT EXISTS embedding_cache (
                content_hash TEXT PRIMARY KEY,
                content_preview TEXT,  -- First 100 chars for debugging
                embedding BLOB NOT NULL,  -- Stored as pickle blob
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                last_used_at INTEGER NOT NULL,
                use_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_embedding_cache_last_used
                ON embedding_cache(last_used_at);

            -- Memory decay tracking table
            CREATE TABLE IF NOT EXISTS memory_decay (
                memory_id TEXT PRIMARY KEY,
                base_priority INTEGER NOT NULL,
                decay_factor REAL DEFAULT 1.0,
                last_decay_at INTEGER,
                decay_schedule TEXT,  -- JSON schedule for decay
                FOREIGN KEY(memory_id) REFERENCES memories(memory_id) ON DELETE CASCADE
            );
        """)
        self.conn.commit()

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def insert(
        self,
        memory: Memory,
        auto_embed: bool = True,
        embed_callback: Optional[Callable[[str, List[float]], None]] = None
    ) -> str:
        """
        Insert a new memory.

        Args:
            memory: Memory object to insert
            auto_embed: Whether to auto-generate embedding (default: True)
            embed_callback: Optional callback when embedding is generated (hash, embedding)

        Returns:
            memory_id of inserted memory

        Raises:
            sqlite3.IntegrityError: If duplicate (user_id, content_hash, scope)
        """
        with self.transaction():
            data = memory.to_dict()

            # Insert memory
            placeholders = ', '.join(['?'] * len(data))
            columns = ', '.join(data.keys())
            self.conn.execute(
                f"INSERT INTO memories ({columns}) VALUES ({placeholders})",
                list(data.values())
            )

            # Insert tags
            if memory.tags:
                self.conn.executemany(
                    "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                    [(memory.memory_id, tag) for tag in memory.tags]
                )

            # Auto-generate embedding
            if auto_embed and self.embedding_config.enabled:
                self._auto_generate_embedding(memory, embed_callback)

            # Initialize decay tracking
            self.init_memory_decay(memory.memory_id, memory.priority)

            # Audit log
            self._log_action(memory.memory_id, "create", memory.user_id, memory.source_session_id)

        return memory.memory_id

    def _auto_generate_embedding(
        self,
        memory: Memory,
        callback: Optional[Callable[[str, List[float]], None]] = None
    ) -> Optional[List[float]]:
        """
        Automatically generate embedding for a memory.

        Args:
            memory: Memory to embed
            callback: Optional callback (content_hash, embedding)

        Returns:
            Generated embedding or None
        """
        if len(memory.content) < self.embedding_config.min_content_length:
            logger.debug(f"Content too short for embedding: {memory.memory_id}")
            return None

        content_hash = memory.content_hash

        # Check if already cached
        cached = self.get_cached_embedding(content_hash)
        if cached is not None:
            logger.debug(f"Using cached embedding for {memory.memory_id}")
            return cached

        # Generate embedding if service available
        service = self._get_embedding_service()
        if service is None:
            logger.warning("No embedding service available")
            return None

        try:
            # Use cached service method for batch (which has caching)
            result = service.embed(memory.content)

            # Cache the embedding
            self.cache_embedding(
                content_hash=content_hash,
                embedding=result.embedding,
                model=result.model,
                dimensions=len(result.embedding),
                content_preview=memory.content[:100]
            )

            if callback:
                callback(content_hash, result.embedding)

            return result.embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    def _get_embedding_service(self):
        """Get or initialize embedding service."""
        if self._embedding_service is not None:
            return self._embedding_service

        if not self.embedding_config.enabled:
            return None

        # Lazy import to avoid circular dependencies
        from agent.embedding_service import EmbeddingService, EmbeddingConfig

        config = EmbeddingConfig(
            provider=self.embedding_config.provider,
            model=self.embedding_config.model,
            api_key=self.embedding_config.api_key,
            base_url=self.embedding_config.base_url,
        )

        self._embedding_service = EmbeddingService(config)
        return self._embedding_service

    def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing memory.

        Args:
            memory_id: ID of memory to update
            updates: Dictionary of fields to update

        Returns:
            True if updated, False if not found
        """
        if not updates:
            return False

        # Whitelist allowed fields
        allowed = {
            'content', 'priority', 'importance', 'status', 'confidence',
            'expires_at', 'channel_id', 'project_id', 'agent_id', 'metadata',
            'tags', 'conflict_group_id'
        }
        updates = {k: v for k, v in updates.items() if k in allowed}

        if not updates:
            return False

        # Always update updated_at
        updates['updated_at'] = int(time.time())

        # Serialize metadata if present
        if 'metadata' in updates and isinstance(updates['metadata'], dict):
            updates['metadata'] = json.dumps(updates['metadata'])

        with self.transaction():
            set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [memory_id]

            cursor = self.conn.execute(
                f"UPDATE memories SET {set_clause} WHERE memory_id = ?",
                values
            )

            # Handle tags update
            if 'tags' in updates:
                tags = updates.pop('tags')
                self.conn.execute(
                    "DELETE FROM memory_tags WHERE memory_id = ?",
                    (memory_id,)
                )
                if tags:
                    self.conn.executemany(
                        "INSERT OR IGNORE INTO memory_tags VALUES (?, ?)",
                        [(memory_id, tag) for tag in tags]
                    )

            if cursor.rowcount > 0:
                # Get user_id for audit log
                row = self.conn.execute(
                    "SELECT user_id, source_session_id FROM memories WHERE memory_id = ?",
                    (memory_id,)
                ).fetchone()
                if row:
                    self._log_action(memory_id, "update", row['user_id'], row['source_session_id'])
                return True

        return False

    def delete(self, memory_id: str, soft: bool = True) -> bool:
        """
        Delete a memory.

        Args:
            memory_id: ID of memory to delete
            soft: If True, set status='deleted'; if False, hard delete

        Returns:
            True if deleted, False if not found
        """
        if soft:
            return self.update(memory_id, {'status': 'deleted'})
        else:
            with self.transaction():
                cursor = self.conn.execute(
                    "DELETE FROM memories WHERE memory_id = ?",
                    (memory_id,)
                )
                return cursor.rowcount > 0

    def get(self, memory_id: str) -> Optional[Memory]:
        """
        Get a memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory object or None if not found
        """
        row = self.conn.execute(
            "SELECT * FROM memories WHERE memory_id = ?",
            (memory_id,)
        ).fetchone()

        if not row:
            return None

        # Load tags
        tags = [
            tag_row['tag'] for tag_row in self.conn.execute(
                "SELECT tag FROM memory_tags WHERE memory_id = ?",
                (memory_id,)
            ).fetchall()
        ]

        data = dict(row)
        data['tags'] = tags
        return Memory.from_dict(data)

    def search(
        self,
        user_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        scope: Optional[List[str]] = None,
        status: str = "active",
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Memory]:
        """
        Search memories with filters.

        Args:
            user_id: Filter by user (defaults to self.user_id)
            memory_type: Filter by type
            scope: Filter by scope (list of scopes)
            status: Filter by status (default: 'active')
            tags: Filter by tags (AND logic)
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of Memory objects
        """
        user_id = user_id or self.user_id

        # Build tag JOIN and collect tag parameters first (they come first in SQL)
        tag_params = []
        if tags:
            tag_params = tags.copy()

        # Build WHERE conditions and parameters
        conditions = ["user_id = ?"]
        where_params = [user_id]

        if memory_type:
            conditions.append("memory_type = ?")
            where_params.append(memory_type)

        if scope:
            placeholders = ','.join(['?'] * len(scope))
            conditions.append(f"scope IN ({placeholders})")
            where_params.extend(scope)

        if status:
            conditions.append("status = ?")
            where_params.append(status)

        query = f"""
            SELECT DISTINCT m.* FROM memories m
            {self._build_tag_join(tags)}
            WHERE {' AND '.join(conditions)}
            ORDER BY m.priority DESC, m.created_at DESC
            LIMIT ? OFFSET ?
        """

        # Combine parameters in correct order: tag params (for JOIN) + where params + limit/offset
        all_params = tag_params + where_params + [limit, offset]

        rows = self.conn.execute(query, all_params).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def search_by_keywords(
        self,
        keywords: List[str],
        user_id: Optional[str] = None,
        scope: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Memory]:
        """
        Search memories by keywords (LIKE query).

        Args:
            keywords: List of keywords to search for
            user_id: Filter by user (defaults to self.user_id)
            scope: Filter by scope
            limit: Maximum results

        Returns:
            List of Memory objects
        """
        user_id = user_id or self.user_id
        conditions = ["user_id = ?", "status = 'active'"]
        params = [user_id]

        if scope:
            placeholders = ','.join(['?'] * len(scope))
            conditions.append(f"scope IN ({placeholders})")
            params.extend(scope)

        # Build LIKE conditions for keywords
        keyword_conditions = []
        for keyword in keywords:
            keyword_conditions.append("content LIKE ?")
            params.append(f"%{keyword}%")

        if keyword_conditions:
            conditions.append(f"({' OR '.join(keyword_conditions)})")

        query = f"""
            SELECT * FROM memories
            WHERE {' AND '.join(conditions)}
            ORDER BY priority DESC, created_at DESC
            LIMIT ?
        """
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def increment_access_count(self, memory_id: str):
        """Increment access count and update last_accessed_at."""
        self.conn.execute("""
            UPDATE memories
            SET access_count = access_count + 1,
                last_accessed_at = ?
            WHERE memory_id = ?
        """, (int(time.time()), memory_id))
        self.conn.commit()

    def count_active_memories(self, user_id: Optional[str] = None) -> int:
        """Count active memories for a user."""
        user_id = user_id or self.user_id
        row = self.conn.execute(
            "SELECT COUNT(*) as count FROM memories WHERE user_id = ? AND status = 'active'",
            (user_id,)
        ).fetchone()
        return row['count'] if row else 0

    def _build_tag_join(self, tags: Optional[List[str]]) -> str:
        """Build JOIN clause for tag filtering."""
        if not tags:
            return ""

        joins = []
        for i, _ in enumerate(tags):
            joins.append(f"JOIN memory_tags mt{i} ON m.memory_id = mt{i}.memory_id AND mt{i}.tag = ?")
        return ' '.join(joins)

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """Convert database row to Memory object."""
        # Load tags
        tags = [
            tag_row['tag'] for tag_row in self.conn.execute(
                "SELECT tag FROM memory_tags WHERE memory_id = ?",
                (row['memory_id'],)
            ).fetchall()
        ]

        data = dict(row)
        data['tags'] = tags
        return Memory.from_dict(data)

    def _log_action(self, memory_id: str, action: str, user_id: str, session_id: Optional[str]):
        """Log an action to audit log."""
        import uuid
        self.conn.execute("""
            INSERT INTO memory_audit_log (log_id, memory_id, action, user_id, session_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), memory_id, action, user_id, session_id, int(time.time())))

    def close(self):
        """Close database connection."""
        self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # ==================== Embedding Cache Methods ====================

    def cache_embedding(
        self,
        content_hash: str,
        embedding: List[float],
        model: str,
        dimensions: int,
        content_preview: str = ""
    ) -> None:
        """
        Cache an embedding for a content hash.

        Args:
            content_hash: SHA256 hash of content
            embedding: The embedding vector
            model: Embedding model used
            dimensions: Embedding dimensions
            content_preview: First 100 chars for debugging
        """
        import pickle

        embedding_blob = pickle.dumps(embedding)
        now = int(time.time())

        # First check if exists to get existing use_count
        existing = self.conn.execute(
            "SELECT use_count FROM embedding_cache WHERE content_hash = ?",
            (content_hash,)
        ).fetchone()
        existing_count = existing['use_count'] if existing else 0

        self.conn.execute("""
            INSERT OR REPLACE INTO embedding_cache
            (content_hash, content_preview, embedding, model, dimensions, created_at, last_used_at, use_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (content_hash, content_preview[:100] if content_preview else "", embedding_blob, model,
              dimensions, now, now, existing_count + 1))
        self.conn.commit()

    def get_cached_embedding(self, content_hash: str) -> Optional[List[float]]:
        """
        Get a cached embedding by content hash.

        Args:
            content_hash: SHA256 hash of content

        Returns:
            Embedding vector or None if not cached
        """
        import pickle

        row = self.conn.execute("""
            SELECT embedding, last_used_at, use_count
            FROM embedding_cache
            WHERE content_hash = ?
        """, (content_hash,)).fetchone()

        if not row:
            return None

        # Update last_used_at and use_count
        now = int(time.time())
        self.conn.execute("""
            UPDATE embedding_cache
            SET last_used_at = ?, use_count = use_count + 1
            WHERE content_hash = ?
        """, (now, content_hash))
        self.conn.commit()

        return pickle.loads(row['embedding'])

    def get_cached_embeddings_batch(
        self,
        content_hashes: List[str]
    ) -> Dict[str, List[float]]:
        """
        Get multiple cached embeddings at once.

        Args:
            content_hashes: List of content hashes

        Returns:
            Dict mapping content_hash to embedding
        """
        if not content_hashes:
            return {}

        import pickle

        placeholders = ','.join(['?'] * len(content_hashes))
        rows = self.conn.execute(f"""
            SELECT content_hash, embedding, last_used_at
            FROM embedding_cache
            WHERE content_hash IN ({placeholders})
        """, content_hashes).fetchall()

        result = {}
        now = int(time.time())

        for row in rows:
            result[row['content_hash']] = pickle.loads(row['embedding'])

        # Batch update last_used_at
        if rows:
            for row in rows:
                self.conn.execute("""
                    UPDATE embedding_cache
                    SET last_used_at = ?, use_count = use_count + 1
                    WHERE content_hash = ?
                """, (now, row['content_hash']))
            self.conn.commit()

        return result

    def clear_embedding_cache(self, older_than_days: Optional[int] = None) -> int:
        """
        Clear embedding cache, optionally only old entries.

        Args:
            older_than_days: Only clear entries older than this many days

        Returns:
            Number of entries cleared
        """
        if older_than_days:
            cutoff = int(time.time()) - (older_than_days * 86400)
            cursor = self.conn.execute(
                "DELETE FROM embedding_cache WHERE last_used_at < ?",
                (cutoff,)
            )
        else:
            cursor = self.conn.execute("DELETE FROM embedding_cache")

        self.conn.commit()
        return cursor.rowcount

    def get_embedding_cache_stats(self) -> Dict[str, Any]:
        """Get embedding cache statistics."""
        row = self.conn.execute("""
            SELECT
                COUNT(*) as total_entries,
                SUM(use_count) as total_uses,
                AVG(use_count) as avg_uses,
                MIN(last_used_at) as oldest,
                MAX(last_used_at) as newest
            FROM embedding_cache
        """).fetchone()

        return {
            "total_entries": row['total_entries'] or 0,
            "total_uses": row['total_uses'] or 0,
            "avg_uses": row['avg_uses'] or 0,
            "oldest_entry": row['oldest'],
            "newest_entry": row['newest'],
        }

    # ==================== Memory Decay Methods ====================

    def init_memory_decay(self, memory_id: str, base_priority: int) -> None:
        """
        Initialize decay tracking for a memory.

        Args:
            memory_id: Memory ID
            base_priority: Initial priority (decay base)
        """
        self.conn.execute("""
            INSERT OR IGNORE INTO memory_decay
            (memory_id, base_priority, decay_factor, last_decay_at)
            VALUES (?, ?, 1.0, ?)
        """, (memory_id, base_priority, int(time.time())))
        self.conn.commit()

    def calculate_effective_priority(
        self,
        memory_id: str,
        created_at: int,
        access_count: int,
        last_accessed_at: Optional[int],
        base_priority: int = 50,
        importance: str = "normal"
    ) -> Tuple[int, str]:
        """
        Calculate effective priority with decay using importance-based strategy.

        Args:
            memory_id: Memory ID
            created_at: Creation timestamp
            access_count: Number of accesses
            last_accessed_at: Last access timestamp
            base_priority: Base priority to start from
            importance: Memory importance level

        Returns:
            Tuple of (effective_priority, decay_reason)
        """
        strategy = DecayStrategy(importance=importance)
        now = int(time.time())
        age_days = (now - created_at) / 86400

        # Time decay: lose 50% over importance-based halflife
        time_decay = 0.5 ** (age_days / strategy.halflife_days)

        # Access boost: sqrt of access count, capped at 2x, scaled by importance
        access_boost = min(1.0 + (access_count ** 0.5) * strategy.access_boost_factor, 2.0)

        # Recency boost: if accessed in last 7 days, add 20%
        recency_boost = 1.0
        decay_reason = "normal"

        if last_accessed_at:
            days_since_access = (now - last_accessed_at) / 86400
            if days_since_access < 7:
                recency_boost = 1.2
                decay_reason = "recently_accessed"
            elif days_since_access > 30:
                decay_reason = "stale"
        elif age_days > 30:
            # Never accessed but old enough to be stale
            decay_reason = "stale"

        # Combined calculation
        effective = int(base_priority * time_decay * access_boost * recency_boost)
        effective = max(strategy.min_priority, min(100, effective))  # Clamp with importance floor

        return effective, decay_reason

    def apply_decay_by_importance(self, batch_size: int = 100) -> Dict[str, int]:
        """
        Apply importance-based decay to all memories.

        Args:
            batch_size: Number of memories to process per batch

        Returns:
            Dict mapping importance level to count of updated memories
        """
        rows = self.conn.execute("""
            SELECT
                memory_id,
                created_at,
                access_count,
                last_accessed_at,
                priority,
                COALESCE(importance, 'normal') as importance
            FROM memories
            WHERE status = 'active'
            LIMIT ?
        """, (batch_size,)).fetchall()

        updated_counts = {"critical": 0, "important": 0, "normal": 0, "low": 0}

        for row in rows:
            new_priority, reason = self.calculate_effective_priority(
                memory_id=row['memory_id'],
                created_at=row['created_at'],
                access_count=row['access_count'],
                last_accessed_at=row['last_accessed_at'],
                base_priority=row['priority'],
                importance=row['importance']
            )

            # Only update if changed significantly (> 5 points)
            if abs(new_priority - row['priority']) > 5:
                self.conn.execute("""
                    UPDATE memories SET priority = ?, updated_at = ?
                    WHERE memory_id = ?
                """, (new_priority, int(time.time()), row['memory_id']))
                updated_counts[row['importance']] += 1

        self.conn.commit()
        return updated_counts

    def apply_decay_to_all(self, batch_size: int = 100) -> int:
        """
        Apply decay to all memories and update their priorities.

        Args:
            batch_size: Number of memories to process per batch

        Returns:
            Number of memories updated
        """
        rows = self.conn.execute("""
            SELECT memory_id, created_at, access_count, last_accessed_at, priority
            FROM memories
            WHERE status = 'active'
            LIMIT ?
        """, (batch_size,)).fetchall()

        updated_count = 0
        for row in rows:
            new_priority, reason = self.calculate_effective_priority(
                memory_id=row['memory_id'],
                created_at=row['created_at'],
                access_count=row['access_count'],
                last_accessed_at=row['last_accessed_at'],
                base_priority=row['priority']
            )

            # Only update if changed significantly (> 5 points)
            if abs(new_priority - row['priority']) > 5:
                self.conn.execute("""
                    UPDATE memories SET priority = ?, updated_at = ?
                    WHERE memory_id = ?
                """, (new_priority, int(time.time()), row['memory_id']))
                updated_count += 1

        self.conn.commit()
        return updated_count

    def get_decay_stats(self) -> Dict[str, Any]:
        """Get decay statistics for all memories, including importance distribution."""
        rows = self.conn.execute("""
            SELECT
                priority,
                access_count,
                created_at,
                last_accessed_at,
                importance,
                (strftime('%s', 'now') - created_at) / 86400 as age_days,
                CASE
                    WHEN last_accessed_at IS NULL THEN 'never'
                    WHEN (strftime('%s', 'now') - last_accessed_at) / 86400 < 7 THEN 'recent'
                    WHEN (strftime('%s', 'now') - last_accessed_at) / 86400 < 30 THEN 'active'
                    ELSE 'stale'
                END as recency_status
            FROM memories
            WHERE status = 'active'
        """).fetchall()

        stats = {
            "total": len(rows),
            "high_priority": 0,  # priority >= 70
            "medium_priority": 0,  # 30 <= priority < 70
            "low_priority": 0,  # priority < 30
            "never_accessed": 0,
            "stale": 0,
            "avg_age_days": 0,
            "avg_access_count": 0,
            "by_importance": {
                "critical": {"count": 0, "avg_priority": 0, "total_priority": 0},
                "important": {"count": 0, "avg_priority": 0, "total_priority": 0},
                "normal": {"count": 0, "avg_priority": 0, "total_priority": 0},
                "low": {"count": 0, "avg_priority": 0, "total_priority": 0},
            },
        }

        if not rows:
            return stats

        total_age = 0
        total_access = 0

        for row in rows:
            row_dict = dict(row)
            if row_dict['priority'] >= 70:
                stats['high_priority'] += 1
            elif row_dict['priority'] >= 30:
                stats['medium_priority'] += 1
            else:
                stats['low_priority'] += 1

            if row_dict['last_accessed_at'] is None:
                stats['never_accessed'] += 1
            elif row_dict['recency_status'] == 'stale':
                stats['stale'] += 1

            total_age += row_dict['age_days']
            total_access += row_dict['access_count']

            # Track by importance
            imp = row_dict.get('importance') or 'normal'
            if imp in stats['by_importance']:
                stats['by_importance'][imp]['count'] += 1
                stats['by_importance'][imp]['total_priority'] += row_dict['priority']

        stats['avg_age_days'] = total_age / len(rows)
        stats['avg_access_count'] = total_access / len(rows)

        # Calculate avg priority per importance
        for imp in stats['by_importance']:
            info = stats['by_importance'][imp]
            if info['count'] > 0:
                info['avg_priority'] = info['total_priority'] / info['count']

        return stats

    def schedule_memory_decay(
        self,
        memory_id: str,
        decay_schedule: Dict[str, Any]
    ) -> None:
        """
        Schedule a custom decay pattern for a memory.

        Args:
            memory_id: Memory ID
            decay_schedule: Dict with decay configuration
                {
                    "type": "linear" | "exponential" | "step",
                    "halflife_days": 90,
                    "min_priority": 10,
                    "boost_on_access": true
                }
        """
        import json

        # Get existing base_priority if it exists
        existing = self.conn.execute(
            "SELECT base_priority FROM memory_decay WHERE memory_id = ?",
            (memory_id,)
        ).fetchone()

        if existing:
            base_priority = existing['base_priority']
        else:
            # Get from memories table
            row = self.conn.execute(
                "SELECT priority FROM memories WHERE memory_id = ?",
                (memory_id,)
            ).fetchone()
            base_priority = row['priority'] if row else 50

        self.conn.execute("""
            INSERT OR REPLACE INTO memory_decay
            (memory_id, base_priority, decay_schedule, last_decay_at)
            VALUES (?, ?, ?, ?)
        """, (memory_id, base_priority, json.dumps(decay_schedule), int(time.time())))
        self.conn.commit()
