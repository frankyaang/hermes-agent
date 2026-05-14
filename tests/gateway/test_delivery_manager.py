import asyncio
import pytest
from pathlib import Path

from gateway.delivery_manager import (
    DeliveryManager,
    DeliveryOutcome,
    RECOVERY_MARKER_WRITE_FILE_STALL,
)


def test_short_text_no_paths():
    dm = DeliveryManager()
    paths = dm.detect_paths("这是一段普通回复，不包含文件路径。")
    assert paths == []


def test_path_detection():
    dm = DeliveryManager()
    paths = dm.detect_paths("报告已生成：/Users/frank/report.md，请查收。")
    assert paths == ["/Users/frank/report.md"]


def test_long_text_chunked():
    dm = DeliveryManager(max_chars=100)
    text = "A" * 350
    chunks = dm.chunk_text(text)
    assert len(chunks) > 1
    assert "（第 1 段 / 共" in chunks[0]
    assert "（第 2 段 / 共" in chunks[1]


def test_short_text_no_segment_label():
    dm = DeliveryManager(max_chars=1000)
    text = "short"
    chunks = dm.chunk_text(text)
    assert chunks == ["short"]


@pytest.mark.asyncio
async def test_md_path_sends_content(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("# 报告\n\n内容很长\n" * 50)

    sent: list[str] = []

    async def mock_send(text: str):
        sent.append(text)

    dm = DeliveryManager(max_chars=200)
    response = f"报告已生成：{report}"
    results = await dm.process_response(response, mock_send)

    assert len(results) == 1
    assert results[0].method == "chunked_text"
    assert results[0].status == "delivered"
    assert results[0].chunks_sent > 0
    assert len(sent) == results[0].chunks_sent
    # Sent content is the file body, not the original response message
    assert all("报告已生成" not in m for m in sent)


@pytest.mark.asyncio
async def test_binary_file_uses_upload_fn(tmp_path):
    xlsx = tmp_path / "data.xlsx"
    xlsx.write_bytes(b"fake xlsx content")

    uploaded: list[Path] = []

    async def mock_upload(p: Path) -> bool:
        uploaded.append(p)
        return True

    async def mock_send(text: str):
        pass

    dm = DeliveryManager()
    response = f"数据表已生成：{xlsx}"
    results = await dm.process_response(response, mock_send, mock_upload)

    assert results[0].method == "file_upload"
    assert results[0].status == "delivered"
    assert xlsx in uploaded


@pytest.mark.asyncio
async def test_binary_fallback_when_upload_fails(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"fake pdf")

    sent: list[str] = []

    async def mock_send(text: str):
        sent.append(text)

    async def mock_upload(p: Path) -> bool:
        return False

    dm = DeliveryManager()
    response = f"报告路径：{pdf}"
    results = await dm.process_response(response, mock_send, mock_upload)

    assert results[0].method == "fallback"
    assert results[0].status == "delivered"
    assert any(str(pdf) in m for m in sent)


@pytest.mark.asyncio
async def test_nonexistent_file_returns_failed():
    dm = DeliveryManager()
    response = "/Users/fake_hermes_test_nonexistent/report.md"

    async def noop_send(text: str):
        pass

    results = await dm.process_response(response, noop_send)
    assert len(results) == 1
    assert results[0].status == "failed"
    assert results[0].error == "file_not_found"


# ---------------------------------------------------------------------------
# DeliveryManager.deliver — unified structured outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_short_text_is_passthrough():
    """Short final text must NOT be intercepted — the adapter still
    handles it via its normal send path so we don't regress UX."""
    dm = DeliveryManager(max_chars=4000)
    sent: list[str] = []

    async def mock_send(t: str) -> None:
        sent.append(t)

    response = "好的，这是一个简短回复。"
    outcome = await dm.deliver(response, mock_send)

    assert isinstance(outcome, DeliveryOutcome)
    assert outcome.handled is False
    assert outcome.status == "skipped"
    assert outcome.method == "passthrough"
    assert outcome.remainder == response
    assert sent == [], "Short text must not be sent through DeliveryManager"


@pytest.mark.asyncio
async def test_deliver_long_text_chunked_and_handled():
    """Very long final text must be chunked and sent through the
    DeliveryManager so the gateway can suppress duplicate delivery."""
    dm = DeliveryManager(max_chars=200)
    sent: list[str] = []

    async def mock_send(t: str) -> None:
        sent.append(t)

    body = ("段落内容很多。" * 200)  # > max_chars
    outcome = await dm.deliver(body, mock_send)

    assert outcome.handled is True
    assert outcome.status == "delivered"
    assert outcome.method == "chunked_text"
    assert outcome.chunks_sent >= 2
    assert outcome.remainder == ""
    assert any("第 1 段 / 共" in chunk for chunk in sent)


@pytest.mark.asyncio
async def test_deliver_md_path_is_handled_and_strips_path(tmp_path):
    """Detected .md path → file body chunked; remainder is the wrapper
    text with the path stripped so the adapter can still process any
    MEDIA: tags left in it."""
    report = tmp_path / "report.md"
    report.write_text("# 报告\n\n" + ("正文段落。\n" * 50))

    sent: list[str] = []

    async def mock_send(t: str) -> None:
        sent.append(t)

    dm = DeliveryManager(max_chars=300)
    response = f"报告已生成：{report}，请查收。"
    outcome = await dm.deliver(response, mock_send)

    assert outcome.handled is True
    assert outcome.status == "delivered"
    assert outcome.method == "file_text"
    assert outcome.chunks_sent >= 1
    # The path itself must not survive in the remainder (the body has
    # already been chunked into the chat).
    assert str(report) not in (outcome.remainder or "")
    # File content went out — the wrapper text never did.
    assert all("请查收" not in m for m in sent)


@pytest.mark.asyncio
async def test_deliver_skips_paths_inside_media_tags(tmp_path):
    """MEDIA:<path> tags belong to the adapter's MEDIA flow.  DM must
    not double-deliver them."""
    pdf = tmp_path / "demo.pdf"
    pdf.write_bytes(b"fake pdf")

    sent: list[str] = []
    uploaded: list[Path] = []

    async def mock_send(t: str) -> None:
        sent.append(t)

    async def mock_upload(p: Path) -> bool:
        uploaded.append(p)
        return True

    dm = DeliveryManager()
    response = f"音频报告已生成。\nMEDIA:{pdf}"
    outcome = await dm.deliver(response, mock_send, mock_upload)

    assert outcome.handled is False
    assert outcome.status == "skipped"
    assert outcome.method == "passthrough"
    assert sent == []
    assert uploaded == []


@pytest.mark.asyncio
async def test_deliver_binary_upload_then_fallback(tmp_path):
    """Binary upload failure must fall back to a text note so the user
    still sees the path."""
    pdf = tmp_path / "long_report.pdf"
    pdf.write_bytes(b"fake pdf body")

    sent: list[str] = []

    async def mock_send(t: str) -> None:
        sent.append(t)

    async def fail_upload(p: Path) -> bool:
        return False

    dm = DeliveryManager()
    response = f"分析完毕：{pdf}"
    outcome = await dm.deliver(response, mock_send, fail_upload)

    assert outcome.handled is True
    assert outcome.status == "delivered"
    assert outcome.method == "fallback"
    assert any(str(pdf) in m for m in sent)


@pytest.mark.asyncio
async def test_deliver_failed_binary_no_send_fn_marked_failed(tmp_path):
    """When upload fails AND send_fn raises (network down), the outcome
    must report failed so the caller falls back."""
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"x")

    async def bad_send(t: str) -> None:
        raise RuntimeError("network down")

    async def fail_upload(p: Path) -> bool:
        return False

    dm = DeliveryManager()
    response = f"路径：{docx}"
    outcome = await dm.deliver(response, bad_send, fail_upload)

    assert outcome.handled is False  # nothing reached the chat
    assert outcome.status == "failed"
    assert "network down" in (outcome.errors[0] if outcome.errors else "")


@pytest.mark.asyncio
async def test_deliver_empty_response_passthrough():
    dm = DeliveryManager()

    async def mock_send(_):
        raise AssertionError("send should not be called for empty response")

    outcome = await dm.deliver("", mock_send)
    assert outcome.handled is False
    assert outcome.status == "skipped"


def test_recovery_marker_constant_is_stable():
    """The recovery marker is part of the run_agent.py <-> gateway
    contract — locking the literal here so accidental renames break
    loudly instead of silently breaking auto recovery."""
    assert RECOVERY_MARKER_WRITE_FILE_STALL == "[[HERMES_DELIVERY_RECOVERY:write_file_stalled]]"
