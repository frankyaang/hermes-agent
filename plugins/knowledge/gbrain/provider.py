from __future__ import annotations
import json
import logging
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from agent.knowledge_models import KnowledgeDoc
from agent.knowledge_provider import KnowledgeProvider

logger = logging.getLogger(__name__)

# PGLite does not support concurrent process access — all gbrain subprocess
# calls must be serialized through this lock.
_GBRAIN_LOCK = threading.Lock()


def _run(cmd: list[str], cwd: str, input_text: str | None = None, timeout: int = 30) -> tuple[str, str, int]:
    """Run a gbrain CLI command. Returns (stdout, stderr, returncode)."""
    with _GBRAIN_LOCK:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return result.stdout, result.stderr, result.returncode


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Split YAML frontmatter from markdown body. Returns (frontmatter_dict, body)."""
    import yaml
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end == -1:
        return {}, raw
    yaml_text = raw[3:end].strip()
    body = raw[end + 4:].strip()
    try:
        fm = yaml.safe_load(yaml_text) or {}
    except Exception:
        fm = {}
    return fm, body


class GBrainCLIKnowledgeProvider(KnowledgeProvider):
    """gbrain CLI adapter.

    Slug naming: pl-{product_line_id}-{finance|general}-{doc_slug}

    ACL is enforced by KnowledgeManager before any call reaches here.
    This provider only handles storage and retrieval.

    Note: PGLite does not support concurrent processes — all calls are
    serialized via _GBRAIN_LOCK. If concurrent throughput becomes a concern,
    switch to gbrain MCP server mode.
    """

    def __init__(self, gbrain_cwd: str | None = None):
        self._cwd = gbrain_cwd or str(Path.home() / "gbrain")

    @property
    def name(self) -> str:
        return "gbrain_cli"

    def is_available(self) -> bool:
        try:
            stdout, _, rc = _run(["gbrain", "health"], cwd=self._cwd, timeout=10)
            return rc == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _make_slug(self, product_line_id: str, finance_flag: bool, doc_slug: str) -> str:
        kind = "finance" if finance_flag else "general"
        return f"pl-{product_line_id}-{kind}-{doc_slug}"

    def _get_page(self, slug: str) -> KnowledgeDoc | None:
        """Fetch a single page by slug and parse its frontmatter."""
        try:
            stdout, _, rc = _run(["gbrain", "get", slug], cwd=self._cwd)
            if rc != 0:
                return None
            fm, body = _parse_frontmatter(stdout)
            # Derive product_line_id and finance_flag from slug if not in frontmatter
            pl_match = re.match(r"pl-([^-]+(?:-[^-]+)*?)-(finance|general)-(.+)", slug)
            product_line_id = fm.get("product_line_id", "")
            finance_flag = fm.get("finance_flag", False)
            if pl_match and not product_line_id:
                product_line_id = pl_match.group(1)
                finance_flag = pl_match.group(2) == "finance"
            return KnowledgeDoc(
                slug=slug,
                title=fm.get("title", slug),
                content=body,
                snippet="",
                product_line_id=product_line_id,
                finance_flag=bool(finance_flag),
                source_uri=fm.get("source_uri", ""),
                knowledge_type=fm.get("knowledge_type", "other"),
                sensitivity_level=fm.get("sensitivity_level", "internal"),
                confidence=fm.get("confidence", "unverified"),
                owner=fm.get("owner", ""),
                created_at=fm.get("created_at", ""),
                updated_at=fm.get("updated_at", ""),
                updated_by=fm.get("updated_by", ""),
            )
        except Exception as exc:
            logger.error("gbrain get %s failed: %s", slug, exc)
            return None

    def query(
        self,
        query: str,
        product_line_id: str,
        finance_flag: bool,
        limit: int = 10,
    ) -> list[KnowledgeDoc]:
        """
        Run gbrain query, parse [score] slug -- snippet lines, then fetch
        each matching page via gbrain get for full frontmatter.
        """
        try:
            stdout, stderr, rc = _run(
                ["gbrain", "query", query, f"--limit={limit}"],
                cwd=self._cwd,
            )
            if rc != 0:
                logger.error("gbrain query failed (rc=%d): %s", rc, stderr[:200])
                return []
        except subprocess.TimeoutExpired:
            logger.error("gbrain query timed out")
            return []
        except Exception as exc:
            logger.error("gbrain query exception: %s", exc)
            return []

        # Parse lines: [0.2432] some-slug -- snippet text
        expected_prefix = f"pl-{product_line_id}-"
        finance_prefix = f"pl-{product_line_id}-finance-"
        docs: list[KnowledgeDoc] = []

        for line in stdout.splitlines():
            line = line.strip()
            m = re.match(r"^\[[\d.]+\]\s+(\S+)\s+--\s*(.*)", line)
            if not m:
                continue
            slug, snippet = m.group(1), m.group(2)

            # Filter by product_line prefix
            if not slug.startswith(expected_prefix):
                continue

            # Filter finance
            is_finance = slug.startswith(finance_prefix)
            if is_finance and not finance_flag:
                continue

            doc = self._get_page(slug)
            if doc is None:
                continue
            doc.snippet = snippet
            docs.append(doc)

        return docs

    def write(self, doc: KnowledgeDoc, actor_user_id: str) -> str:
        slug = self._make_slug(doc.product_line_id, doc.finance_flag, doc.slug)
        now = datetime.now(timezone.utc).isoformat()
        page_content = (
            "---\n"
            f"product_line_id: {doc.product_line_id}\n"
            f"knowledge_type: {doc.knowledge_type}\n"
            f"sensitivity_level: {doc.sensitivity_level}\n"
            f"finance_flag: {str(doc.finance_flag).lower()}\n"
            f"source_uri: '{doc.source_uri}'\n"
            f"owner: {doc.owner}\n"
            f"confidence: {doc.confidence}\n"
            f"created_at: {doc.created_at or now}\n"
            f"updated_at: {now}\n"
            f"updated_by: {actor_user_id}\n"
            "---\n\n"
            f"# {doc.title}\n\n"
            f"{doc.content}\n"
        )
        try:
            stdout, stderr, rc = _run(
                ["gbrain", "put", slug],
                cwd=self._cwd,
                input_text=page_content,
            )
            if rc != 0:
                raise RuntimeError(f"gbrain put failed (rc={rc}): {stderr[:200]}")
            # gbrain put returns JSON: {"slug": "...", "status": "created_or_updated", ...}
            result = json.loads(stdout)
            if result.get("status") not in ("created_or_updated", "updated", "created"):
                logger.warning("gbrain put unexpected status: %s", result.get("status"))
            logger.info("gbrain put: slug=%s status=%s", slug, result.get("status"))
            return slug
        except json.JSONDecodeError:
            # gbrain put returned non-JSON — treat as success if rc==0
            logger.warning("gbrain put returned non-JSON stdout: %s", stdout[:100])
            return slug
        except subprocess.TimeoutExpired:
            raise RuntimeError("gbrain put timed out")
