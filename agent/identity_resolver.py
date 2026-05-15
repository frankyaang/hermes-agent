# agent/identity_resolver.py
"""Session-aware identity resolution for knowledge sedimentation."""
from __future__ import annotations
import getpass
import os
from dataclasses import dataclass


class IdentitySource:
    SESSION = "session"
    CLI_FALLBACK = "cli_fallback"


@dataclass
class ResolvedIdentity:
    user_id: str
    platform: str
    raw_user_id: str
    source: str   # IdentitySource value


def resolve_identity() -> ResolvedIdentity:
    """Resolve user identity from session context variables.

    Feishu: platform=feishu, user_id=ou_xxx → feishu:ou_xxx
    CLI: fallback to cli:user:profile
    """
    from gateway.session_context import get_session_env
    platform = get_session_env("HERMES_SESSION_PLATFORM", "").strip().lower()
    raw_user_id = get_session_env("HERMES_SESSION_USER_ID", "").strip()

    if raw_user_id:
        if platform and not raw_user_id.startswith(f"{platform}:"):
            user_id = f"{platform}:{raw_user_id}"
        else:
            user_id = raw_user_id
        return ResolvedIdentity(
            user_id=user_id,
            platform=platform,
            raw_user_id=raw_user_id,
            source=IdentitySource.SESSION,
        )

    profile = os.getenv("HERMES_PROFILE", "default")
    cli_user_id = f"cli:{getpass.getuser()}:{profile}"
    return ResolvedIdentity(
        user_id=cli_user_id,
        platform=platform or "cli",
        raw_user_id="",
        source=IdentitySource.CLI_FALLBACK,
    )


def candidate_registry_ids(platform: str, raw_user_id: str) -> list[str]:
    """Return registry lookup candidates (mirrors knowledge_tool._candidate_user_ids logic)."""
    raw = (raw_user_id or "").strip()
    platform_key = (platform or "").strip().lower()
    candidates: list[str] = []
    if raw:
        if platform_key and ":" not in raw:
            candidates.append(f"{platform_key}:{raw}")
        candidates.append(raw)
    else:
        profile = os.getenv("HERMES_PROFILE", "default")
        candidates.append(f"cli:{getpass.getuser()}:{profile}")
    return [c for c in dict.fromkeys(candidates) if c]
