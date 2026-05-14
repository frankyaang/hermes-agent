from __future__ import annotations
import logging
from pathlib import Path
from agent.knowledge_models import KnowledgeUserContext
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


class KnowledgeUserRegistry:
    def __init__(self, registry_path: Path | None = None):
        self._path = registry_path or (get_hermes_home() / "knowledge" / "users.yaml")
        self._cache: dict[str, KnowledgeUserContext] = {}

    def load(self) -> None:
        if not self._path.exists():
            logger.warning("knowledge user registry not found: %s", self._path)
            return
        import yaml
        with open(self._path) as f:
            data = yaml.safe_load(f) or {}
        self._cache = {}
        for user in data.get("users", []):
            ctx = KnowledgeUserContext(
                user_id=user["user_id"],
                product_line_ids=list(user.get("product_line_ids") or []),
                default_product_line_id=user.get("default_product_line_id") or "",
                finance_product_line_ids=list(user.get("finance_product_line_ids") or []),
                role=user.get("role", "user"),
                is_admin=bool(user.get("is_admin", False)),
                conversation_access=user.get("conversation_access") or "default",
            )
            self._cache[ctx.user_id] = ctx

    def get_user(self, user_id: str) -> KnowledgeUserContext | None:
        return self._cache.get(user_id)

    def validate_config(self, ctx: KnowledgeUserContext) -> list[str]:
        errors: list[str] = []
        if ctx.default_product_line_id and ctx.default_product_line_id not in ctx.product_line_ids:
            errors.append(
                f"default_product_line_id '{ctx.default_product_line_id}' not in product_line_ids"
            )
        for fpl in ctx.finance_product_line_ids:
            if fpl not in ctx.product_line_ids:
                errors.append(f"finance_product_line_id '{fpl}' not in product_line_ids")
        return errors
