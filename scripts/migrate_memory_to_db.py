#!/usr/bin/env python3
"""
Migration script: MEMORY.md/USER.md → SQLite database

Migrates plain text memory files to structured SQLite database while
preserving all content and maintaining per-user isolation.
"""

import sys
import argparse
import time
import uuid
from pathlib import Path
from typing import List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.memory_database import MemoryDatabase, Memory
from tools.memory_tool import MemoryStore, get_memory_dir


def migrate_user_memories(
    user_id: str,
    legacy_dir: Path,
    db_path: Path,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Migrate a single user's memories from files to database.

    Args:
        user_id: User identifier
        legacy_dir: Directory containing MEMORY.md and USER.md
        db_path: Path to SQLite database
        dry_run: If True, don't actually write to database

    Returns:
        Tuple of (memory_count, user_profile_count)
    """
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migrating memories for user: {user_id}")
    print(f"  Legacy dir: {legacy_dir}")
    print(f"  Database:   {db_path}")

    # Load legacy memories
    store = MemoryStore(user_id=user_id, memory_dir=legacy_dir)
    store.load_from_disk()

    memory_count = len(store.memory_entries)
    user_count = len(store.user_entries)

    print(f"  Found: {memory_count} memories, {user_count} user profile entries")

    if dry_run:
        return memory_count, user_count

    # Initialize database
    db = MemoryDatabase(db_path, user_id)

    # Migrate MEMORY.md entries
    for content in store.memory_entries:
        memory = Memory(
            memory_id=str(uuid.uuid4()),
            user_id=user_id,
            content=content,
            memory_type="fact",
            scope="user",
            created_at=int(time.time()),
            updated_at=int(time.time()),
            confidence=1.0,
            priority=50,
            metadata={"migrated_from": "MEMORY.md"}
        )
        try:
            db.insert(memory)
        except Exception as e:
            print(f"  ⚠️  Failed to insert memory: {e}")

    # Migrate USER.md entries
    for content in store.user_entries:
        memory = Memory(
            memory_id=str(uuid.uuid4()),
            user_id=user_id,
            content=content,
            memory_type="user_profile",
            scope="user",
            created_at=int(time.time()),
            updated_at=int(time.time()),
            confidence=1.0,
            priority=60,  # Higher priority for user profiles
            metadata={"migrated_from": "USER.md"}
        )
        try:
            db.insert(memory)
        except Exception as e:
            print(f"  ⚠️  Failed to insert user profile: {e}")

    db.close()

    print(f"  ✓ Migrated {memory_count} memories and {user_count} user profiles")
    return memory_count, user_count


def discover_users(memories_base: Path) -> List[Tuple[str, Path]]:
    """
    Discover all users with memory directories.

    Args:
        memories_base: Base memories directory (~/.hermes/memories)

    Returns:
        List of (user_id, user_dir) tuples
    """
    users = []

    # Check for global directory (no user_id)
    if (memories_base / "MEMORY.md").exists() or (memories_base / "USER.md").exists():
        users.append(("default", memories_base))

    # Check for per-user directories
    if memories_base.exists():
        for user_dir in memories_base.iterdir():
            if user_dir.is_dir():
                if (user_dir / "MEMORY.md").exists() or (user_dir / "USER.md").exists():
                    users.append((user_dir.name, user_dir))

    return users


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Hermes memories from plain text to SQLite database"
    )
    parser.add_argument(
        "--user-id",
        help="Migrate specific user (default: auto-discover all users)"
    )
    parser.add_argument(
        "--legacy-dir",
        type=Path,
        help="Legacy memory directory (default: auto-detect)"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="SQLite database path (default: ~/.hermes/memories.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually migrating"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Backup legacy files before migration (default: True)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup (not recommended)"
    )

    args = parser.parse_args()

    # Determine paths
    from hermes_constants import get_hermes_home
    hermes_home = get_hermes_home()
    memories_base = hermes_home / "memories"
    db_path = args.db_path or (hermes_home / "memories.db")

    print("=" * 60)
    print("Hermes Memory Migration: Files → SQLite")
    print("=" * 60)
    print(f"Hermes Home: {hermes_home}")
    print(f"Memories Base: {memories_base}")
    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE MIGRATION'}")
    print("=" * 60)

    # Backup if requested
    if not args.no_backup and not args.dry_run:
        backup_dir = memories_base.parent / f"memories.backup.{int(time.time())}"
        print(f"\n📦 Creating backup: {backup_dir}")
        import shutil
        if memories_base.exists():
            shutil.copytree(memories_base, backup_dir)
            print(f"  ✓ Backup created")

    # Discover users
    if args.user_id and args.legacy_dir:
        users = [(args.user_id, args.legacy_dir)]
    elif args.user_id:
        user_dir = memories_base / args.user_id
        if not user_dir.exists():
            user_dir = memories_base  # Try global directory
        users = [(args.user_id, user_dir)]
    else:
        print("\n🔍 Auto-discovering users...")
        users = discover_users(memories_base)
        print(f"  Found {len(users)} user(s) with memories")

    if not users:
        print("\n⚠️  No users found with memory files")
        print("  Nothing to migrate")
        return 0

    # Migrate each user
    total_memories = 0
    total_profiles = 0

    for user_id, user_dir in users:
        try:
            mem_count, prof_count = migrate_user_memories(
                user_id=user_id,
                legacy_dir=user_dir,
                db_path=db_path,
                dry_run=args.dry_run
            )
            total_memories += mem_count
            total_profiles += prof_count
        except Exception as e:
            print(f"  ❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Users migrated: {len(users)}")
    print(f"Total memories: {total_memories}")
    print(f"Total user profiles: {total_profiles}")
    print(f"Total entries: {total_memories + total_profiles}")

    if args.dry_run:
        print("\n💡 This was a dry run. No changes were made.")
        print("   Run without --dry-run to perform actual migration.")
    else:
        print(f"\n✅ Migration complete!")
        print(f"   Database: {db_path}")
        print(f"   Backup: {backup_dir if not args.no_backup else 'None'}")
        print("\n⚠️  Legacy files are still in place.")
        print("   After verifying the migration, you can:")
        print(f"   - Keep them as backup: mv {memories_base} {memories_base}.old")
        print(f"   - Delete them: rm -rf {memories_base}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
