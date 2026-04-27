"""Feishu Document Tool -- read document content via Feishu/Lark API.

Provides ``feishu_doc_read`` for reading document content as plain text.
When the plain-text body is sparse, the tool automatically inspects Docx
blocks and summarizes embedded sheets so the agent can still see the useful
business content.
"""

import json
import logging
from typing import Any, Dict, List

from tools.feishu_client_context import (
    bind_task_client,
    get_client as _get_shared_client,
    set_thread_client,
    unbind_task_client,
)
from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

def set_client(client):
    """Store a lark client for the current thread (called by feishu_comment)."""
    set_thread_client(client)


def bind_client(task_id, client):
    bind_task_client(task_id, client)


def unbind_client(task_id):
    unbind_task_client(task_id)


def get_client(task_id=None):
    """Return the active lark client for the current thread or task."""
    return _get_shared_client(task_id)


# ---------------------------------------------------------------------------
# feishu_doc_read
# ---------------------------------------------------------------------------

_RAW_CONTENT_URI = "/open-apis/docx/v1/documents/:document_id/raw_content"
_BLOCKS_URI = "/open-apis/docx/v1/documents/:document_id/blocks"
_SHORT_CONTENT_MIN_CHARS = 120
_SHORT_CONTENT_MIN_NONSPACE_CHARS = 40
_BLOCKS_PAGE_SIZE = 500
_BLOCKS_PAGE_LIMIT = 20
_EMBEDDED_SHEET_PREVIEW_ROWS = 10
_EMBEDDED_SHEET_PREVIEW_COLUMNS = 8
_BLOCK_TYPE_NAMES = {
    1: "page",
    2: "text",
    3: "heading1",
    4: "heading2",
    5: "heading3",
    6: "heading4",
    7: "heading5",
    8: "heading6",
    9: "heading7",
    10: "heading8",
    11: "heading9",
    12: "bullet",
    13: "ordered",
    14: "code",
    15: "quote",
    17: "callout",
    22: "divider",
    30: "sheet",
    31: "bitable",
}
_BLOCK_META_KEYS = {"block_id", "block_type", "children", "parent_id"}

FEISHU_DOC_READ_SCHEMA = {
    "name": "feishu_doc_read",
    "description": (
        "Read the content of a Feishu/Lark document. "
        "When plain-text content is sparse, automatically inspect document "
        "blocks and summarize embedded sheets."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doc_token": {
                "type": "string",
                "description": "The document token (from the document URL or comment context).",
            },
        },
        "required": ["doc_token"],
    },
}


def _check_feishu():
    try:
        import lark_oapi  # noqa: F401
        return True
    except ImportError:
        return False


def _do_request(client, method, uri, paths=None, queries=None, body=None):
    from lark_oapi import AccessTokenType
    from lark_oapi.core.enum import HttpMethod
    from lark_oapi.core.model.base_request import BaseRequest

    method_map = {
        "GET": HttpMethod.GET,
        "POST": HttpMethod.POST,
    }
    http_method = method_map[method]

    builder = (
        BaseRequest.builder()
        .http_method(http_method)
        .uri(uri)
        .token_types({AccessTokenType.TENANT})
    )
    if paths:
        builder = builder.paths(paths)
    if queries:
        builder = builder.queries(queries)
    if body is not None:
        builder = builder.body(body)

    request = builder.build()
    response = client.request(request)

    code = getattr(response, "code", None)
    msg = getattr(response, "msg", "")

    data = {}
    raw = getattr(response, "raw", None)
    if raw and hasattr(raw, "content"):
        try:
            body_json = json.loads(raw.content)
            data = body_json.get("data", {})
        except (json.JSONDecodeError, AttributeError):
            pass
    if not data:
        resp_data = getattr(response, "data", None)
        if isinstance(resp_data, dict):
            data = resp_data
        elif resp_data and hasattr(resp_data, "__dict__"):
            data = vars(resp_data)

    return code, msg, data


def _normalize_inline_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _is_sparse_content(content: str) -> bool:
    stripped = str(content or "").strip()
    if not stripped:
        return True
    compact = "".join(stripped.split())
    non_empty_lines = [line for line in stripped.splitlines() if line.strip()]
    return (
        len(compact) < _SHORT_CONTENT_MIN_NONSPACE_CHARS
        or (
            len(stripped) < _SHORT_CONTENT_MIN_CHARS
            and len(non_empty_lines) <= 2
        )
    )


def _extract_inline_text(elements) -> str:
    parts: List[str] = []
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        if "text_run" in element:
            parts.append(str((element.get("text_run") or {}).get("content") or ""))
            continue
        if "mention_user" in element:
            mention = element.get("mention_user") or {}
            name = (
                mention.get("user_name")
                or mention.get("name")
                or mention.get("open_id")
                or mention.get("union_id")
                or "用户"
            )
            parts.append(f"@{name}")
            continue
        if "mention_doc" in element:
            mention = element.get("mention_doc") or {}
            parts.append(str(mention.get("title") or mention.get("token") or ""))
            continue
        if "equation" in element:
            parts.append(str((element.get("equation") or {}).get("content") or ""))
            continue
        if "reminder" in element:
            reminder = element.get("reminder") or {}
            parts.append(str(reminder.get("mention") or reminder.get("notify_time") or "提醒"))
            continue
    return _normalize_inline_text("".join(parts))


def _extract_block_text(block: Dict[str, Any]) -> str:
    for key, value in block.items():
        if key in _BLOCK_META_KEYS or not isinstance(value, dict):
            continue
        elements = value.get("elements")
        if isinstance(elements, list):
            text = _extract_inline_text(elements)
            if text:
                return text
    return ""


def _list_document_blocks(client, doc_token: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page_token = ""
    for _ in range(_BLOCKS_PAGE_LIMIT):
        queries = [("page_size", str(_BLOCKS_PAGE_SIZE))]
        if page_token:
            queries.append(("page_token", page_token))
        code, msg, data = _do_request(
            client,
            "GET",
            _BLOCKS_URI,
            paths={"document_id": doc_token},
            queries=queries,
        )
        if code != 0:
            raise RuntimeError(f"Failed to list blocks: code={code} msg={msg}")
        page_items = data.get("items") or []
        items.extend(page_items)
        if not data.get("has_more"):
            break
        page_token = str(data.get("page_token") or "").strip()
        if not page_token:
            break
    return items


def _block_type_name(block_type: Any) -> str:
    try:
        numeric = int(block_type)
    except (TypeError, ValueError):
        return str(block_type or "unknown")
    return _BLOCK_TYPE_NAMES.get(numeric, f"type_{numeric}")


def _summarize_blocks(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for block in blocks:
        key = _block_type_name(block.get("block_type"))
        counts[key] = counts.get(key, 0) + 1
    return {
        "count": len(blocks),
        "by_type": counts,
    }


def _column_index_to_letters(index: int) -> str:
    if index < 1:
        raise ValueError("column index must be >= 1")
    letters = []
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


def _parse_embedded_sheet_token(raw_token: str) -> Dict[str, str] | None:
    token = str(raw_token or "").strip()
    if not token or "_" not in token:
        return None
    spreadsheet_token, sheet_id = token.rsplit("_", 1)
    if not spreadsheet_token or not sheet_id:
        return None
    return {
        "raw_token": token,
        "spreadsheet_token": spreadsheet_token,
        "sheet_id": sheet_id,
    }


def _trim_value_matrix(values) -> List[List[str]]:
    rows: List[List[str]] = []
    last_non_empty_column = 0
    for row in values or []:
        if not isinstance(row, list):
            continue
        normalized_row = []
        for cell in row:
            if cell is None:
                normalized_row.append("")
            else:
                normalized_row.append(str(cell).replace("\n", " / "))
        for idx, cell in enumerate(normalized_row, start=1):
            if cell.strip():
                last_non_empty_column = max(last_non_empty_column, idx)
        rows.append(normalized_row)
    if last_non_empty_column <= 0:
        return []
    trimmed = []
    for row in rows:
        padded = row[:last_non_empty_column]
        if len(padded) < last_non_empty_column:
            padded.extend([""] * (last_non_empty_column - len(padded)))
        trimmed.append(padded)
    return trimmed


def _read_embedded_sheet_preview(raw_token: str, *, task_id=None) -> Dict[str, Any]:
    parsed = _parse_embedded_sheet_token(raw_token)
    if parsed is None:
        return {
            "type": "sheet",
            "raw_token": str(raw_token or ""),
            "error": "无法解析嵌入电子表格 token",
        }

    try:
        from tools.feishu_sheet_tool import _handle_feishu_sheet_read
    except Exception as exc:  # pragma: no cover - import failure is a rare runtime issue
        logger.warning("Failed to import feishu_sheet_tool: %s", exc)
        return {
            "type": "sheet",
            **parsed,
            "error": f"无法加载飞书表格工具: {exc}",
        }

    preview_range = (
        f"{parsed['sheet_id']}!A1:"
        f"{_column_index_to_letters(_EMBEDDED_SHEET_PREVIEW_COLUMNS)}"
        f"{_EMBEDDED_SHEET_PREVIEW_ROWS}"
    )
    sheet_result_raw = _handle_feishu_sheet_read(
        {
            "spreadsheet_token": parsed["spreadsheet_token"],
            "range": preview_range,
            "value_render_option": "FormattedValue",
            "date_time_render_option": "FormattedString",
        },
        task_id=task_id,
    )
    try:
        sheet_result = json.loads(sheet_result_raw)
    except json.JSONDecodeError:
        return {
            "type": "sheet",
            **parsed,
            "error": "飞书表格工具返回了无法解析的结果",
        }

    if sheet_result.get("error"):
        return {
            "type": "sheet",
            **parsed,
            "error": str(sheet_result.get("error")),
        }

    spreadsheet = sheet_result.get("spreadsheet") or {}
    sheets = sheet_result.get("sheets") or []
    matched_sheet = next(
        (sheet for sheet in sheets if sheet.get("sheet_id") == parsed["sheet_id"]),
        None,
    )
    trimmed_values = _trim_value_matrix(
        (sheet_result.get("value_range") or {}).get("values") or []
    )
    result = {
        "type": "sheet",
        **parsed,
        "spreadsheet_title": spreadsheet.get("title") or "",
        "spreadsheet_url": spreadsheet.get("url") or "",
        "sheet_title": (matched_sheet or {}).get("title") or "",
        "selected_range": sheet_result.get("selected_range") or preview_range,
        "values": trimmed_values,
    }
    return result


def _render_embedded_sheet_content(sheet: Dict[str, Any]) -> str:
    lines = ["[嵌入电子表格]"]
    if sheet.get("spreadsheet_title"):
        lines.append(f"表格标题: {sheet['spreadsheet_title']}")
    if sheet.get("sheet_title"):
        lines.append(f"工作表: {sheet['sheet_title']}")
    elif sheet.get("sheet_id"):
        lines.append(f"工作表ID: {sheet['sheet_id']}")
    if sheet.get("selected_range"):
        lines.append(f"预览范围: {sheet['selected_range']}")
    if sheet.get("error"):
        lines.append(f"读取状态: {sheet['error']}")
        return "\n".join(lines)
    values = sheet.get("values") or []
    if values:
        lines.append("预览内容:")
        lines.extend("\t".join(row) for row in values)
    return "\n".join(lines)


def _build_content(raw_content: str, blocks: List[Dict[str, Any]], embedded_resources) -> str:
    sections: List[str] = []
    seen_lines = set()

    for line in str(raw_content or "").splitlines():
        normalized = _normalize_inline_text(line)
        if normalized and normalized not in seen_lines:
            seen_lines.add(normalized)
            sections.append(normalized)

    for block in blocks or []:
        text = _extract_block_text(block)
        if text and text not in seen_lines:
            seen_lines.add(text)
            sections.append(text)

    for resource in embedded_resources or []:
        if resource.get("type") == "sheet":
            sections.append(_render_embedded_sheet_content(resource))

    return "\n\n".join(part for part in sections if part).strip()


def _handle_feishu_doc_read(args: dict, **kwargs) -> str:
    doc_token = args.get("doc_token", "").strip()
    if not doc_token:
        return tool_error("doc_token is required")

    client = get_client(kwargs.get("task_id"))
    if client is None:
        return tool_error("Feishu client not available for this task")

    try:
        import lark_oapi  # noqa: F401
    except ImportError:
        return tool_error("lark_oapi not installed")

    code, msg, data = _do_request(
        client,
        "GET",
        _RAW_CONTENT_URI,
        paths={"document_id": doc_token},
    )
    if code != 0:
        return tool_error(f"Failed to read document: code={code} msg={msg}")

    raw_content = str(data.get("content", "") or "")
    blocks_fallback_used = False
    blocks_error = ""
    blocks: List[Dict[str, Any]] = []
    embedded_resources = []

    if _is_sparse_content(raw_content):
        blocks_fallback_used = True
        try:
            blocks = _list_document_blocks(client, doc_token)
        except Exception as exc:
            blocks_error = str(exc)
            logger.warning("Failed to list Feishu doc blocks for %s: %s", doc_token, exc)
        else:
            for block in blocks:
                sheet_data = block.get("sheet")
                if not isinstance(sheet_data, dict):
                    continue
                token = str(sheet_data.get("token") or "").strip()
                if not token:
                    continue
                embedded_resources.append(
                    _read_embedded_sheet_preview(token, task_id=kwargs.get("task_id"))
                )

    if not blocks_fallback_used and not embedded_resources:
        content = raw_content
    else:
        content = _build_content(raw_content, blocks, embedded_resources)
        if not content:
            content = raw_content

    result = {
        "success": True,
        "content": content,
        "raw_content": raw_content,
        "blocks_fallback_used": blocks_fallback_used,
        "embedded_resources": embedded_resources,
    }
    if blocks_fallback_used:
        result["blocks_summary"] = _summarize_blocks(blocks)
    if blocks_error:
        result["blocks_error"] = blocks_error
    return tool_result(result)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

registry.register(
    name="feishu_doc_read",
    toolset="feishu_doc",
    schema=FEISHU_DOC_READ_SCHEMA,
    handler=_handle_feishu_doc_read,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Read Feishu document content",
    emoji="\U0001f4c4",
)
