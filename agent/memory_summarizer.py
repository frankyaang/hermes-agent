"""
Memory Summarization Module - Compress and summarize old memories.

Features:
- Automatic summarization of old, low-priority memories
- Key information extraction
- Progressive compression (never lose data completely)
- LLM-powered summarization with fallback heuristics
"""

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MemorySummary:
    """A summarized version of a memory."""
    summary_id: str
    memory_id: str
    user_id: str
    original_content: str
    summary: str
    key_points: List[str] = field(default_factory=list)
    memory_type: str = "general"
    importance: str = "normal"
    compressed_count: int = 1  # Number of memories compressed into this
    created_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Generate hash of original content."""
        return hashlib.sha256(self.original_content.encode('utf-8')).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['metadata'] = json.dumps(data['metadata'])
        data['key_points'] = json.dumps(data['key_points'])
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemorySummary":
        """Create from dictionary."""
        if isinstance(data.get('metadata'), str):
            data['metadata'] = json.loads(data['metadata'])
        if isinstance(data.get('key_points'), str):
            data['key_points'] = json.loads(data['key_points'])
        return cls(**data)


@dataclass
class SummarizationConfig:
    """Configuration for memory summarization."""
    # Threshold: memories older than this (in days) are considered for summarization
    age_threshold_days: int = 60

    # Priority threshold: memories with priority below this are considered
    priority_threshold: int = 30

    # Minimum memories needed before summarization
    min_memories_for_batching: int = 3

    # Maximum memories to batch into one summary
    max_batch_size: int = 10

    # How often to run summarization (in seconds)
    run_interval_seconds: int = 3600  # 1 hour

    # Enable LLM summarization (if available)
    use_llm: bool = True

    # LLM model for summarization
    llm_model: str = "claude-3-haiku"

    # Fallback: simple extraction if LLM unavailable
    use_fallback: bool = True

    # Max summary length in characters
    max_summary_length: int = 500

    # Max key points to extract
    max_key_points: int = 5


class MemorySummarizer:
    """
    Memory summarization service.

    Summarizes old, low-priority memories to free up space while preserving
    key information. Uses a two-tier approach:
    1. LLM summarization (if available and enabled)
    2. Heuristic extraction (fallback)
    """

    def __init__(
        self,
        db_path: Path,
        llm_client: Optional[Any] = None,
        config: Optional[SummarizationConfig] = None
    ):
        """
        Initialize memory summarizer.

        Args:
            db_path: Path to SQLite database
            llm_client: Optional LLM client for summarization
            config: Summarization configuration
        """
        self.db_path = db_path
        self.llm_client = llm_client
        self.config = config or SummarizationConfig()
        self._conn = None  # Lazy connection
        self._init_schema()

    def _get_conn(self):
        """Get database connection (lazy initialization)."""
        if self._conn is None:
            import sqlite3
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self):
        """Initialize database schema for summaries."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_summaries (
                summary_id TEXT PRIMARY KEY,
                memory_id TEXT,  -- Can reference original or be standalone
                user_id TEXT NOT NULL,
                original_content TEXT,
                summary TEXT NOT NULL,
                key_points TEXT,  -- JSON array
                memory_type TEXT DEFAULT 'general',
                importance TEXT DEFAULT 'normal',
                compressed_count INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL,
                expires_at INTEGER,
                metadata TEXT,  -- JSON

                UNIQUE(memory_id)
            );

            CREATE INDEX IF NOT EXISTS idx_summaries_user
                ON memory_summaries(user_id);
            CREATE INDEX IF NOT EXISTS idx_summaries_type
                ON memory_summaries(memory_type);
            CREATE INDEX IF NOT EXISTS idx_summaries_created
                ON memory_summaries(created_at DESC);
        """)
        conn.commit()

    def find_memories_to_summarize(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Find memories eligible for summarization.

        Args:
            user_id: User ID
            limit: Maximum memories to return

        Returns:
            List of memory dictionaries
        """
        conn = self._get_conn()

        age_threshold = int(time.time()) - (self.config.age_threshold_days * 86400)

        rows = conn.execute("""
            SELECT
                memory_id,
                user_id,
                content,
                memory_type,
                COALESCE(importance, 'normal') as importance,
                priority,
                created_at,
                access_count,
                last_accessed_at
            FROM memories
            WHERE user_id = ?
                AND status = 'active'
                AND created_at < ?
                AND priority < ?
                AND memory_id NOT IN (
                    SELECT memory_id FROM memory_summaries WHERE memory_id IS NOT NULL
                )
            ORDER BY priority ASC, created_at ASC
            LIMIT ?
        """, (user_id, age_threshold, self.config.priority_threshold, limit)).fetchall()

        return [dict(row) for row in rows]

    def summarize_with_llm(
        self,
        contents: List[str],
        memory_types: List[str]
    ) -> Tuple[str, List[str]]:
        """
        Summarize memories using LLM.

        Args:
            contents: List of memory contents
            memory_types: List of memory types

        Returns:
            Tuple of (summary, key_points)
        """
        if not self.llm_client:
            raise ValueError("LLM client not configured")

        combined_content = "\n\n---\n\n".join(
            f"[{mt}] {c}" for c, mt in zip(contents, memory_types)
        )

        prompt = f"""Summarize the following memories concisely, preserving key information:

{combined_content}

Provide:
1. A summary (max {self.config.max_summary_length} characters)
2. Key points (up to {self.config.max_key_points} bullet points)

Format as JSON:
{{"summary": "...", "key_points": ["point 1", "point 2", ...]}}"""

        try:
            response = self.llm_client.messages.create(
                model=self.config.llm_model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            result = json.loads(response.content[0].text)
            return result.get("summary", ""), result.get("key_points", [])
        except Exception as e:
            logger.error(f"LLM summarization failed: {e}")
            raise

    def summarize_with_heuristics(
        self,
        contents: List[str],
        memory_types: List[str]
    ) -> Tuple[str, List[str]]:
        """
        Fallback summarization using heuristics.

        Args:
            contents: List of memory contents
            memory_types: List of memory types

        Returns:
            Tuple of (summary, key_points)
        """
        key_points = []
        summary_parts = []

        # Extract first sentences as summary
        for content in contents[:3]:
            sentences = content.split('.')
            if sentences:
                first = sentences[0].strip()
                if len(first) > 10:
                    summary_parts.append(first)

        # Extract potential key points (lines starting with -, *, or numbered)
        for content in contents:
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith(('-', '*', '•', '1.', '2.', '3.')):
                    key_points.append(line.lstrip('-*•0123456789. '))
                    if len(key_points) >= self.config.max_key_points:
                        break

        # If no structured points, use important words
        if not key_points:
            for content in contents[:2]:
                words = content.split()
                key_points.append(" ".join(words[:15]) + "...")

        summary = ". ".join(summary_parts[:3])
        if len(summary) > self.config.max_summary_length:
            summary = summary[:self.config.max_summary_length - 3] + "..."

        return summary, key_points[:self.config.max_key_points]

    def create_summary(
        self,
        memory_ids: List[str],
        user_id: str,
        original_contents: List[str],
        memory_types: List[str],
        importance: str = "normal"
    ) -> MemorySummary:
        """
        Create a summary from multiple memories.

        Args:
            memory_ids: List of memory IDs being summarized
            user_id: User ID
            original_contents: Original content of memories
            memory_types: Types of memories
            importance: Combined importance level

        Returns:
            MemorySummary object
        """
        import uuid

        summary_id = f"sum_{uuid.uuid4().hex[:12]}"

        # Try LLM first, fallback to heuristics
        summary_text = ""
        key_points: List[str] = []

        if self.config.use_llm and self.llm_client:
            try:
                summary_text, key_points = self.summarize_with_llm(
                    original_contents, memory_types
                )
            except Exception as e:
                logger.warning(f"LLM summarization failed, using heuristics: {e}")
                if self.config.use_fallback:
                    summary_text, key_points = self.summarize_with_heuristics(
                        original_contents, memory_types
                    )
        elif self.config.use_fallback:
            summary_text, key_points = self.summarize_with_heuristics(
                original_contents, memory_types
            )

        # Use combined content as fallback
        if not summary_text:
            summary_text = " | ".join(c[:100] for c in original_contents[:3])

        summary = MemorySummary(
            summary_id=summary_id,
            memory_id=memory_ids[0] if len(memory_ids) == 1 else None,
            user_id=user_id,
            original_content="\n\n".join(original_contents),
            summary=summary_text,
            key_points=key_points,
            memory_type=memory_types[0] if memory_types else "general",
            importance=importance,
            compressed_count=len(memory_ids),
        )

        # Save to database
        self._save_summary(summary)

        return summary

    def _save_summary(self, summary: MemorySummary):
        """Save summary to database."""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        data = summary.to_dict()

        placeholders = ', '.join(['?'] * len(data))
        columns = ', '.join(data.keys())
        conn.execute(
            f"INSERT OR REPLACE INTO memory_summaries ({columns}) VALUES ({placeholders})",
            list(data.values())
        )
        conn.commit()

    def get_summaries(
        self,
        user_id: str,
        memory_type: Optional[str] = None,
        limit: int = 20
    ) -> List[MemorySummary]:
        """Get summaries for a user."""
        conn = self._get_conn()

        query = "SELECT * FROM memory_summaries WHERE user_id = ?"
        params = [user_id]

        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        return [MemorySummary.from_dict(dict(row)) for row in rows]

    def compress_old_memories(
        self,
        user_id: str,
        batch_callback: Optional[Callable[[List[str]], None]] = None
    ) -> Dict[str, Any]:
        """
        Find and compress old memories into summaries.

        Args:
            user_id: User ID
            batch_callback: Optional callback with batched memory_ids

        Returns:
            Dict with compression stats
        """
        memories = self.find_memories_to_summarize(user_id)

        if len(memories) < self.config.min_memories_for_batching:
            return {
                "status": "skipped",
                "reason": "not_enough_memories",
                "found": len(memories),
                "needed": self.config.min_memories_for_batching
            }

        # Batch memories for compression
        batches = []
        for i in range(0, len(memories), self.config.max_batch_size):
            batch = memories[i:i + self.config.max_batch_size]
            batches.append(batch)

        stats = {
            "status": "success",
            "memories_processed": 0,
            "summaries_created": 0,
            "batches": []
        }

        for batch in batches:
            memory_ids = [m['memory_id'] for m in batch]
            contents = [m['content'] for m in batch]
            types = [m['memory_type'] for m in batch]

            # Create summary
            summary = self.create_summary(
                memory_ids=memory_ids,
                user_id=user_id,
                original_contents=contents,
                memory_types=types,
                importance=batch[0].get('importance', 'normal')
            )

            # Archive original memories
            self._archive_memories(memory_ids)

            if batch_callback:
                batch_callback(memory_ids)

            stats["memories_processed"] += len(memory_ids)
            stats["summaries_created"] += 1
            stats["batches"].append({
                "memory_ids": memory_ids,
                "summary_id": summary.summary_id
            })

        return stats

    def _archive_memories(self, memory_ids: List[str]):
        """Archive original memories after summarization."""
        conn = self._get_conn()
        placeholders = ','.join(['?'] * len(memory_ids))
        conn.execute(f"""
            UPDATE memories
            SET status = 'archived',
                updated_at = ?
            WHERE memory_id IN ({placeholders})
        """, [int(time.time())] + memory_ids)
        conn.commit()

    def expand_summary(self, summary_id: str) -> Optional[Dict[str, Any]]:
        """
        Expand a summary back to its original form.

        Args:
            summary_id: Summary ID

        Returns:
            Dict with original content and metadata
        """
        conn = self._get_conn()

        row = conn.execute(
            "SELECT * FROM memory_summaries WHERE summary_id = ?",
            (summary_id,)
        ).fetchone()

        if not row:
            return None

        summary = MemorySummary.from_dict(dict(row))

        # Check if original memories are still archived
        original_content = None
        if summary.memory_id:
            try:
                original = conn.execute(
                    "SELECT content FROM memories WHERE memory_id = ?",
                    (summary.memory_id,)
                ).fetchone()

                if original:
                    original_content = dict(original)['content']
            except sqlite3.OperationalError:
                # memories table may not exist
                pass

        return {
            "original_content": original_content or summary.original_content,
            "summary": summary.summary,
            "key_points": summary.key_points,
            "compressed_count": summary.compressed_count
        }
