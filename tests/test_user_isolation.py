"""
Tests for per-user memory isolation.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from tools.memory_tool import MemoryStore, get_memory_dir, _sanitize_user_id


class TestUserIdSanitization:
    """Test user ID sanitization for directory names."""

    def test_sanitize_simple_user_id(self):
        """Test sanitizing simple user IDs."""
        assert _sanitize_user_id("ou_xxx") == "ou_xxx"
        assert _sanitize_user_id("user123") == "user123"

    def test_sanitize_colon_separator(self):
        """Test sanitizing user IDs with colons."""
        assert _sanitize_user_id("telegram:123456") == "telegram_123456"
        assert _sanitize_user_id("platform:user:id") == "platform_user_id"

    def test_sanitize_slash(self):
        """Test sanitizing user IDs with slashes."""
        assert _sanitize_user_id("group/user") == "group_user"
        assert _sanitize_user_id("a/b/c") == "a_b_c"

    def test_sanitize_email(self):
        """Test sanitizing email-like user IDs."""
        assert _sanitize_user_id("user@domain.com") == "user_domain_com"

    def test_sanitize_special_chars(self):
        """Test sanitizing various special characters."""
        result = _sanitize_user_id("user!@#$%^&*()")
        # Should only contain alphanumeric, underscore, and hyphen
        assert all(c.isalnum() or c in ('_', '-') for c in result)


class TestMemoryDirIsolation:
    """Test memory directory isolation."""

    def test_get_memory_dir_without_user_id(self, monkeypatch):
        """Test getting global memory directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("HERMES_HOME", tmpdir)
            mem_dir = get_memory_dir()
            assert mem_dir == Path(tmpdir) / "memories"

    def test_get_memory_dir_with_user_id(self, monkeypatch):
        """Test getting per-user memory directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("HERMES_HOME", tmpdir)
            mem_dir = get_memory_dir(user_id="ou_user_a")
            assert mem_dir == Path(tmpdir) / "memories" / "ou_user_a"
            assert mem_dir.exists()  # Should be created

    def test_different_users_get_different_dirs(self, monkeypatch):
        """Test that different users get different directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("HERMES_HOME", tmpdir)

            dir_a = get_memory_dir(user_id="ou_user_a")
            dir_b = get_memory_dir(user_id="ou_user_b")

            assert dir_a != dir_b
            assert "ou_user_a" in str(dir_a)
            assert "ou_user_b" in str(dir_b)


class TestMemoryStoreIsolation:
    """Test MemoryStore per-user isolation."""

    def test_memory_store_with_user_id(self):
        """Test creating MemoryStore with user_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(
                user_id="ou_test_user",
                memory_dir=Path(tmpdir) / "memories" / "ou_test_user"
            )
            assert store.user_id == "ou_test_user"

    def test_isolated_memory_files(self):
        """Test that different users have isolated memory files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create stores for two users
            store_a = MemoryStore(
                user_id="ou_user_a",
                memory_dir=base_dir / "memories" / "ou_user_a"
            )
            store_b = MemoryStore(
                user_id="ou_user_b",
                memory_dir=base_dir / "memories" / "ou_user_b"
            )

            # Load from disk (creates directories)
            store_a.load_from_disk()
            store_b.load_from_disk()

            # Add memory to user A
            store_a.memory_entries.append("User A's memory")
            store_a.save_to_disk("memory")

            # Add memory to user B
            store_b.memory_entries.append("User B's memory")
            store_b.save_to_disk("memory")

            # Reload and verify isolation
            store_a_reload = MemoryStore(
                user_id="ou_user_a",
                memory_dir=base_dir / "memories" / "ou_user_a"
            )
            store_a_reload.load_from_disk()

            store_b_reload = MemoryStore(
                user_id="ou_user_b",
                memory_dir=base_dir / "memories" / "ou_user_b"
            )
            store_b_reload.load_from_disk()

            # User A should only see their memory
            assert "User A's memory" in store_a_reload.memory_entries
            assert "User B's memory" not in store_a_reload.memory_entries

            # User B should only see their memory
            assert "User B's memory" in store_b_reload.memory_entries
            assert "User A's memory" not in store_b_reload.memory_entries

    def test_user_profile_isolation(self):
        """Test that USER.md is also isolated per user."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create stores for two users
            store_a = MemoryStore(
                user_id="ou_user_a",
                memory_dir=base_dir / "memories" / "ou_user_a"
            )
            store_b = MemoryStore(
                user_id="ou_user_b",
                memory_dir=base_dir / "memories" / "ou_user_b"
            )

            store_a.load_from_disk()
            store_b.load_from_disk()

            # Add user profiles
            store_a.user_entries.append("User A prefers Python")
            store_a.save_to_disk("user")

            store_b.user_entries.append("User B prefers JavaScript")
            store_b.save_to_disk("user")

            # Reload and verify
            store_a_reload = MemoryStore(
                user_id="ou_user_a",
                memory_dir=base_dir / "memories" / "ou_user_a"
            )
            store_a_reload.load_from_disk()

            store_b_reload = MemoryStore(
                user_id="ou_user_b",
                memory_dir=base_dir / "memories" / "ou_user_b"
            )
            store_b_reload.load_from_disk()

            assert "User A prefers Python" in store_a_reload.user_entries
            assert "User B prefers JavaScript" not in store_a_reload.user_entries

            assert "User B prefers JavaScript" in store_b_reload.user_entries
            assert "User A prefers Python" not in store_b_reload.user_entries

    def test_backward_compatibility_no_user_id(self):
        """Test backward compatibility when no user_id is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create store without user_id (legacy mode)
            store = MemoryStore(memory_dir=base_dir / "memories")
            store.load_from_disk()

            store.memory_entries.append("Global memory")
            store.save_to_disk("memory")

            # Reload without user_id
            store_reload = MemoryStore(memory_dir=base_dir / "memories")
            store_reload.load_from_disk()

            assert "Global memory" in store_reload.memory_entries


class TestMemoryIsolationIntegration:
    """Integration tests for memory isolation."""

    def test_concurrent_user_writes(self):
        """Test that concurrent writes from different users don't interfere."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            stores = {}
            for user_id in ["ou_user_1", "ou_user_2", "ou_user_3"]:
                store = MemoryStore(
                    user_id=user_id,
                    memory_dir=base_dir / "memories" / user_id
                )
                store.load_from_disk()
                store.memory_entries.append(f"Memory from {user_id}")
                store.save_to_disk("memory")
                stores[user_id] = store

            # Verify each user only sees their own memory
            for user_id, store in stores.items():
                store_reload = MemoryStore(
                    user_id=user_id,
                    memory_dir=base_dir / "memories" / user_id
                )
                store_reload.load_from_disk()

                # Should see own memory
                assert f"Memory from {user_id}" in store_reload.memory_entries

                # Should NOT see other users' memories
                for other_user_id in stores.keys():
                    if other_user_id != user_id:
                        assert f"Memory from {other_user_id}" not in store_reload.memory_entries

    def test_cron_job_vs_interactive_session(self):
        """Test isolation between cron job and interactive session for same user."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Same user, but different contexts
            # In practice, they would use the same user_id and share memories
            # This test verifies the mechanism works correctly

            user_id = "ou_user_a"

            # Interactive session
            interactive_store = MemoryStore(
                user_id=user_id,
                memory_dir=base_dir / "memories" / user_id
            )
            interactive_store.load_from_disk()
            interactive_store.memory_entries.append("Interactive memory")
            interactive_store.save_to_disk("memory")

            # Cron job (same user, should see same memories)
            cron_store = MemoryStore(
                user_id=user_id,
                memory_dir=base_dir / "memories" / user_id
            )
            cron_store.load_from_disk()

            # Cron job should see interactive memory (same user)
            assert "Interactive memory" in cron_store.memory_entries

            # Add cron-specific memory
            cron_store.memory_entries.append("Cron memory")
            cron_store.save_to_disk("memory")

            # Interactive session should see cron memory (same user)
            interactive_store_reload = MemoryStore(
                user_id=user_id,
                memory_dir=base_dir / "memories" / user_id
            )
            interactive_store_reload.load_from_disk()
            assert "Cron memory" in interactive_store_reload.memory_entries
