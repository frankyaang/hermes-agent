"""最终交付保障：把报告/分析交付物自动塞进当前会话。

This module is the gateway's safety net: if the agent returns a final
reply that points to a local report file, or that is too long for a
single platform message, it must still land in the current chat —
without asking the user to know about "segmented output" or to retry.

The manager runs on the gateway side just before the adapter sends the
final response.  Responsibilities:

* Short final text — pass through, let the adapter send as usual.
* Very long final text — chunk it, label each chunk "第 X 段 / 共 N 段",
  and send through the adapter's send().
* Local .md / .txt / .html / .csv paths — read the file and chunk-send
  its body.
* Local .xlsx / .pdf / .docx / .pptx / .png / .jpg / .jpeg paths —
  attempt platform upload; on failure, send a textual fallback so the
  user at least sees the path.

Errors are never raised — they're recorded on the returned outcome so
the caller can fall back gracefully.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# Internal recovery marker that run_agent.py emits when a write_file
# tool call is dropped mid-stream.  The gateway looks for this marker
# inside the agent's final response and triggers a one-shot auto
# recovery instead of asking the user to retry.
RECOVERY_MARKER_WRITE_FILE_STALL = "[[HERMES_DELIVERY_RECOVERY:write_file_stalled]]"

_TEXT_EXTENSIONS = frozenset({".md", ".txt", ".html", ".csv"})
_BINARY_EXTENSIONS = frozenset({".xlsx", ".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg"})
_ALL_EXTENSIONS = _TEXT_EXTENSIONS | _BINARY_EXTENSIONS

# Only match paths under well-known directories to avoid scanning sensitive paths.
# /private is included because macOS resolves /tmp and /var through /private.
_PATH_RE = re.compile(
    r"(?<!\w)"
    r"(/(?:Users|tmp|var|home|opt|private)/[\w/.\-]{1,300}"
    r"\.(?:md|txt|html|csv|xlsx|pdf|docx|pptx|png|jpg|jpeg))"
    r"(?!\w)"
)

# Pre-stripped before path detection so MEDIA-handled attachments are
# never double-delivered (the adapter's MEDIA: flow already handles those).
_MEDIA_TAG_RE = re.compile(r"MEDIA:\s*\S+")

SendFn = Callable[[str], Awaitable[None]]
UploadFn = Callable[[Path], Awaitable[bool]]  # True=success, False=failure


@dataclass
class DeliveryResult:
    """Per-path outcome from delivering a single file."""

    path: str
    method: str = ""   # "chunked_text" | "file_upload" | "fallback" | "skipped"
    status: str = ""   # "delivered" | "partial" | "failed"
    chunks_sent: int = 0
    error: str = ""


@dataclass
class DeliveryOutcome:
    """Aggregated outcome of a single ``deliver()`` call.

    ``handled``      — True when DeliveryManager actually sent something to
                       the chat (chunks or file uploads).  When False, the
                       caller should fall back to the adapter's normal
                       send path.
    ``status``       — delivered / partial / failed / skipped.
    ``method``       — passthrough / chunked_text / file_text /
                       file_upload / fallback / mixed.
    ``chunks_sent``  — total successful send() calls across all paths and
                       chunks.
    ``errors``       — list of error strings encountered.
    ``file_results`` — per-path DeliveryResult entries (empty for the
                       text-only chunked path).
    ``remainder``    — what's left of the response after DM consumed
                       its share.  For chunked_text, "" (suppress the
                       caller's send).  For file paths, the response
                       with the matched paths stripped (so the adapter
                       still gets to process MEDIA: tags and images).
    """

    handled: bool = False
    status: str = "skipped"
    method: str = "passthrough"
    chunks_sent: int = 0
    errors: list[str] = field(default_factory=list)
    file_results: list[DeliveryResult] = field(default_factory=list)
    remainder: str | None = None


class DeliveryManager:
    """Detect local file paths in a response and deliver their contents to the session.

    Text files are read and sent as chunked messages.
    Binary files are uploaded or, on failure, described with a fallback message.
    Never raises — all errors are recorded in DeliveryResult / DeliveryOutcome.
    """

    def __init__(self, max_chars: int = 4000) -> None:
        # Defensive: some adapters expose enormous MAX_MESSAGE_LENGTH;
        # clamp the upper bound so chunks stay readable on platforms
        # whose actual UI limit is lower than the API limit.  No lower
        # bound — callers and tests can pass small values intentionally.
        self.max_chars = max(1, min(int(max_chars), 8000))

    # ── Detection ──────────────────────────────────────────────────────

    def detect_paths(self, text: str) -> list[str]:
        """Return whitelisted local file paths found in ``text``.

        Paths that appear inside ``MEDIA:`` tags are excluded — the
        adapter's existing MEDIA flow already handles those.
        """
        if not text:
            return []
        scrubbed = _MEDIA_TAG_RE.sub("", text)
        scrubbed = scrubbed.replace("[[audio_as_voice]]", "")
        return [p for p in _PATH_RE.findall(scrubbed) if Path(p).suffix in _ALL_EXTENSIONS]

    # ── Chunking ───────────────────────────────────────────────────────

    def chunk_text(self, content: str) -> list[str]:
        """Split ``content`` on paragraph / line boundaries up to ``max_chars``.

        Single-chunk inputs come back unlabeled; multi-chunk inputs get
        a "（第 X 段 / 共 N 段）" header so the user can tell when more
        is coming.
        """
        if len(content) <= self.max_chars:
            return [content]
        chunks: list[str] = []
        remaining = content
        while remaining:
            if len(remaining) <= self.max_chars:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n\n", 0, self.max_chars)
            if split_at < 200:
                split_at = remaining.rfind("\n", 0, self.max_chars)
            if split_at < 200:
                split_at = self.max_chars
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        total = len(chunks)
        if total == 1:
            return chunks
        return [f"（第 {i + 1} 段 / 共 {total} 段）\n\n{c}" for i, c in enumerate(chunks)]

    # ── Per-path delivery ──────────────────────────────────────────────

    async def deliver_file(
        self,
        path_str: str,
        send_fn: SendFn,
        upload_fn: UploadFn | None = None,
    ) -> DeliveryResult:
        import asyncio

        result = DeliveryResult(path=path_str)
        p = Path(path_str)

        if not p.exists():
            result.method = "skipped"
            result.status = "failed"
            result.error = "file_not_found"
            logger.warning("[delivery-manager] file not found: %s", path_str)
            return result

        if p.suffix in _TEXT_EXTENSIONS:
            try:
                content = await asyncio.to_thread(p.read_text, encoding="utf-8", errors="replace")
            except Exception as exc:
                result.method = "chunked_text"
                result.status = "failed"
                result.error = str(exc)
                return result

            chunks = self.chunk_text(content)
            sent = 0
            result.method = "chunked_text"
            for chunk in chunks:
                try:
                    await send_fn(chunk)
                    sent += 1
                except Exception as exc:
                    result.error = str(exc)
                    break
            result.chunks_sent = sent
            result.status = "delivered" if sent == len(chunks) else "partial"

        elif p.suffix in _BINARY_EXTENSIONS:
            result.method = "file_upload"
            uploaded = False
            if upload_fn is not None:
                try:
                    uploaded = await upload_fn(p)
                except Exception as exc:
                    result.error = str(exc)
            if uploaded:
                result.status = "delivered"
                result.chunks_sent = 1
            else:
                fallback = (
                    f"文件已生成但暂时无法直接发送到会话。\n"
                    f"文件路径：`{path_str}`\n"
                    f"如需查看，请在 Hermes 终端运行：`cat {path_str}`"
                )
                try:
                    await send_fn(fallback)
                    result.method = "fallback"
                    result.status = "delivered"
                    result.chunks_sent = 1
                except Exception as exc:
                    result.method = "fallback"
                    result.status = "failed"
                    result.error = str(exc)

        return result

    # ── Legacy entry point (kept for existing callers/tests) ───────────

    async def process_response(
        self,
        response_text: str,
        send_fn: SendFn,
        upload_fn: UploadFn | None = None,
    ) -> list[DeliveryResult]:
        """Scan response for local file paths and deliver their contents to the session.

        Returns one DeliveryResult per detected path.  Empty list when
        no path is detected.  Does not handle long-text chunking — use
        :py:meth:`deliver` for the full structured outcome.
        """
        paths = self.detect_paths(response_text)
        if not paths:
            return []

        results: list[DeliveryResult] = []
        for path_str in paths:
            r = await self.deliver_file(path_str, send_fn, upload_fn)
            results.append(r)
            logger.info(
                "[delivery-manager] path=%s method=%s status=%s chunks=%d",
                path_str, r.method, r.status, r.chunks_sent,
            )
        return results

    # ── New unified entry point ────────────────────────────────────────

    async def deliver(
        self,
        response_text: str,
        send_fn: SendFn,
        upload_fn: UploadFn | None = None,
    ) -> DeliveryOutcome:
        """Decide and execute delivery for a final agent response.

        * No content → handled=False, status=skipped.
        * Local file paths present → deliver each (text or upload),
          handled=True, ``remainder`` has the response with paths
          stripped so the adapter can still process MEDIA: / image
          attachments left in the wrapper text.
        * Very long final text (and no MEDIA: markers) → chunk-send,
          handled=True, ``remainder=""``.
        * Otherwise → passthrough.
        """
        outcome = DeliveryOutcome(remainder=response_text)
        text = (response_text or "").strip()
        if not text:
            outcome.remainder = response_text or ""
            return outcome

        has_media_tag = "MEDIA:" in response_text or "[[audio_as_voice]]" in response_text
        paths = self.detect_paths(response_text)

        if paths:
            file_results: list[DeliveryResult] = []
            for path_str in paths:
                r = await self.deliver_file(path_str, send_fn, upload_fn)
                file_results.append(r)
                logger.info(
                    "[delivery-manager] path=%s method=%s status=%s chunks=%d",
                    path_str, r.method, r.status, r.chunks_sent,
                )

            outcome.file_results = file_results
            outcome.chunks_sent = sum(r.chunks_sent for r in file_results)
            outcome.errors = [r.error for r in file_results if r.error]

            any_delivered = any(r.status == "delivered" for r in file_results)
            any_failed = any(r.status == "failed" for r in file_results)
            if any_delivered and not any_failed:
                outcome.status = "delivered"
            elif any_delivered:
                outcome.status = "partial"
            else:
                outcome.status = "failed"

            methods = {r.method for r in file_results}
            if methods == {"chunked_text"}:
                outcome.method = "file_text"
            elif methods == {"file_upload"}:
                outcome.method = "file_upload"
            elif methods == {"fallback"}:
                outcome.method = "fallback"
            elif methods and methods.issubset({"chunked_text", "file_upload", "fallback"}):
                outcome.method = "mixed"
            else:
                outcome.method = "file_text"

            remainder = response_text
            for path_str in paths:
                remainder = remainder.replace(path_str, "")
            outcome.remainder = remainder
            outcome.handled = outcome.status in ("delivered", "partial")
            return outcome

        if not has_media_tag and len(text) > self.max_chars:
            chunks = self.chunk_text(text)
            sent = 0
            for chunk in chunks:
                try:
                    await send_fn(chunk)
                    sent += 1
                except Exception as exc:
                    outcome.errors.append(str(exc))
                    break
            outcome.chunks_sent = sent
            outcome.method = "chunked_text"
            if sent == len(chunks):
                outcome.status = "delivered"
            elif sent > 0:
                outcome.status = "partial"
            else:
                outcome.status = "failed"
            outcome.handled = sent > 0
            outcome.remainder = "" if outcome.handled else response_text
            return outcome

        outcome.method = "passthrough"
        outcome.handled = False
        outcome.status = "skipped"
        outcome.remainder = response_text
        return outcome
