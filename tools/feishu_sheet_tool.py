"""Feishu Sheet Tools -- spreadsheet structure read and range write via Feishu/Lark API."""

import json
import logging
import re
from urllib.parse import quote

from tools.feishu_client_context import (
    bind_task_client,
    get_client as _get_shared_client,
    set_thread_client,
    unbind_task_client,
)
from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

_SPREADSHEET_INFO_URI = "/open-apis/sheets/v3/spreadsheets/:spreadsheet_token"
_LIST_SHEETS_URI = "/open-apis/sheets/v3/spreadsheets/:spreadsheet_token/sheets/query"
_READ_RANGE_URI = "/open-apis/sheets/v2/spreadsheets/:spreadsheetToken/values/:range"
_WRITE_RANGE_URI = "/open-apis/sheets/v2/spreadsheets/:spreadsheetToken/values"
_CELL_REF_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def set_client(client):
    """Store a lark client for the current thread."""
    set_thread_client(client)


def bind_client(task_id, client):
    bind_task_client(task_id, client)


def unbind_client(task_id):
    unbind_task_client(task_id)


def get_client(task_id=None):
    """Return the active lark client for the current thread or task."""
    return _get_shared_client(task_id)


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
        "PUT": HttpMethod.PUT,
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


def _column_index_to_letters(index: int) -> str:
    if index < 1:
        raise ValueError("column index must be >= 1")
    letters = []
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


def _column_letters_to_index(letters: str) -> int:
    value = 0
    for ch in letters.upper():
        if not ("A" <= ch <= "Z"):
            raise ValueError("invalid column letters")
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value


def _normalize_values(values):
    if not isinstance(values, list) or not values:
        raise ValueError("values must be a non-empty 2D array")
    normalized = []
    max_cols = 0
    for row in values:
        if not isinstance(row, list):
            raise ValueError("each row in values must be an array")
        normalized.append(row)
        max_cols = max(max_cols, len(row))
    if max_cols < 1:
        raise ValueError("values must contain at least one cell")
    return normalized, len(normalized), max_cols


def _build_range_from_start(sheet_id: str, start_cell: str, values) -> str:
    match = _CELL_REF_RE.match(start_cell.strip().upper())
    if not match:
        raise ValueError("start_cell must look like A1")
    col_letters, row_number = match.groups()
    start_col = _column_letters_to_index(col_letters)
    start_row = int(row_number)
    if start_row < 1:
        raise ValueError("start_cell row must be >= 1")

    _, row_count, col_count = _normalize_values(values)
    end_col = start_col + col_count - 1
    end_row = start_row + row_count - 1
    return (
        f"{sheet_id}!{_column_index_to_letters(start_col)}{start_row}:"
        f"{_column_index_to_letters(end_col)}{end_row}"
    )


def _summarize_sheets(sheets):
    items = []
    for sheet in sheets or []:
        grid = sheet.get("grid_properties") or {}
        items.append(
            {
                "sheet_id": sheet.get("sheet_id"),
                "title": sheet.get("title"),
                "index": sheet.get("index"),
                "hidden": sheet.get("hidden"),
                "resource_type": sheet.get("resource_type"),
                "row_count": grid.get("row_count"),
                "column_count": grid.get("column_count"),
                "frozen_row_count": grid.get("frozen_row_count"),
                "frozen_column_count": grid.get("frozen_column_count"),
            }
        )
    return items


def _pick_preview_sheet(sheets):
    visible_sheet = next(
        (
            sheet for sheet in sheets
            if sheet.get("resource_type") == "sheet" and not sheet.get("hidden", False)
        ),
        None,
    )
    if visible_sheet is not None:
        return visible_sheet
    return next((sheet for sheet in sheets if sheet.get("resource_type") == "sheet"), None)


def _build_preview_range(sheet, preview_rows: int, preview_columns: int) -> str:
    grid = sheet.get("grid_properties") or {}
    row_count = max(1, min(int(grid.get("row_count") or preview_rows or 20), preview_rows))
    column_count = max(1, min(int(grid.get("column_count") or preview_columns or 10), preview_columns))
    end_col = _column_index_to_letters(column_count)
    return f"{sheet.get('sheet_id')}!A1:{end_col}{row_count}"


def _parse_positive_int(value, *, default: int, minimum: int, maximum: int, field_name: str) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    return max(minimum, min(parsed, maximum))


FEISHU_SHEET_READ_SCHEMA = {
    "name": "feishu_sheet_read",
    "description": (
        "Read Feishu/Lark spreadsheet structure and preview data via API. "
        "If range is omitted, returns spreadsheet info, worksheet list, and a preview "
        "from the first visible sheet."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "spreadsheet_token": {
                "type": "string",
                "description": "Spreadsheet token from the sheets URL.",
            },
            "range": {
                "type": "string",
                "description": "Optional A1 range with sheetId, e.g. X1MFFa!A1:F20.",
            },
            "preview_rows": {
                "type": "integer",
                "description": "When range is omitted, how many rows to preview from the first visible sheet.",
                "default": 20,
            },
            "preview_columns": {
                "type": "integer",
                "description": "When range is omitted, how many columns to preview from the first visible sheet.",
                "default": 10,
            },
            "value_render_option": {
                "type": "string",
                "description": "Cell render mode: ToString, Formula, FormattedValue, or UnformattedValue.",
                "default": "FormattedValue",
            },
            "date_time_render_option": {
                "type": "string",
                "description": "Date render mode. Use FormattedString for human-readable values.",
                "default": "FormattedString",
            },
        },
        "required": ["spreadsheet_token"],
    },
}


FEISHU_SHEET_WRITE_SCHEMA = {
    "name": "feishu_sheet_write",
    "description": (
        "Write data to a single Feishu/Lark spreadsheet range. Overwrites existing cells "
        "inside the target range."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "spreadsheet_token": {
                "type": "string",
                "description": "Spreadsheet token from the sheets URL.",
            },
            "range": {
                "type": "string",
                "description": "Optional explicit A1 range with sheetId, e.g. X1MFFa!A1:B2.",
            },
            "sheet_id": {
                "type": "string",
                "description": "Sheet ID used when range is omitted.",
            },
            "start_cell": {
                "type": "string",
                "description": "Start cell used with sheet_id when range is omitted.",
                "default": "A1",
            },
            "values": {
                "type": "array",
                "description": "2D array of cell values to write.",
                "items": {
                    "type": "array",
                    "items": {},
                },
            },
        },
        "required": ["spreadsheet_token", "values"],
    },
}


def _handle_feishu_sheet_read(args: dict, **kwargs) -> str:
    client = get_client(kwargs.get("task_id"))
    if client is None:
        return tool_error("Feishu client not available for this task")

    spreadsheet_token = str(args.get("spreadsheet_token", "")).strip()
    if not spreadsheet_token:
        return tool_error("spreadsheet_token is required")

    try:
        preview_rows = _parse_positive_int(
            args.get("preview_rows"),
            default=20,
            minimum=1,
            maximum=200,
            field_name="preview_rows",
        )
        preview_columns = _parse_positive_int(
            args.get("preview_columns"),
            default=10,
            minimum=1,
            maximum=100,
            field_name="preview_columns",
        )
    except ValueError as exc:
        return tool_error(str(exc))
    value_render_option = str(args.get("value_render_option", "FormattedValue") or "FormattedValue")
    date_time_render_option = str(
        args.get("date_time_render_option", "FormattedString") or "FormattedString"
    )

    info_code, info_msg, info_data = _do_request(
        client,
        "GET",
        _SPREADSHEET_INFO_URI,
        paths={"spreadsheet_token": spreadsheet_token},
        queries=[("user_id_type", "open_id")],
    )
    if info_code != 0:
        return tool_error(
            f"Get spreadsheet info failed: code={info_code} msg={info_msg}",
            code=info_code,
        )

    sheets_code, sheets_msg, sheets_data = _do_request(
        client,
        "GET",
        _LIST_SHEETS_URI,
        paths={"spreadsheet_token": spreadsheet_token},
    )
    if sheets_code != 0:
        return tool_error(
            f"List spreadsheet sheets failed: code={sheets_code} msg={sheets_msg}",
            code=sheets_code,
        )

    sheets = sheets_data.get("sheets") or []
    selected_range = str(args.get("range", "")).strip()
    preview_sheet = _pick_preview_sheet(sheets)
    if not selected_range and preview_sheet is not None:
        selected_range = _build_preview_range(preview_sheet, preview_rows, preview_columns)

    value_range = None
    if selected_range:
        read_code, read_msg, read_data = _do_request(
            client,
            "GET",
            _READ_RANGE_URI,
            paths={
                "spreadsheetToken": spreadsheet_token,
                "range": quote(selected_range, safe=""),
            },
            queries=[
                ("valueRenderOption", value_render_option),
                ("dateTimeRenderOption", date_time_render_option),
                ("user_id_type", "open_id"),
            ],
        )
        if read_code != 0:
            return tool_error(
                f"Read spreadsheet range failed: code={read_code} msg={read_msg}",
                code=read_code,
                range=selected_range,
            )
        value_range = read_data.get("valueRange") or {}

    spreadsheet = (info_data.get("spreadsheet") or {}).copy()
    spreadsheet["token"] = spreadsheet.get("token") or spreadsheet_token

    return tool_result(
        success=True,
        spreadsheet=spreadsheet,
        sheets=_summarize_sheets(sheets),
        selected_range=selected_range or None,
        value_range=value_range,
    )


def _handle_feishu_sheet_write(args: dict, **kwargs) -> str:
    client = get_client(kwargs.get("task_id"))
    if client is None:
        return tool_error("Feishu client not available for this task")

    spreadsheet_token = str(args.get("spreadsheet_token", "")).strip()
    if not spreadsheet_token:
        return tool_error("spreadsheet_token is required")

    values = args.get("values")
    try:
        normalized_values, _, _ = _normalize_values(values)
    except ValueError as exc:
        return tool_error(str(exc))

    target_range = str(args.get("range", "")).strip()
    if not target_range:
        sheet_id = str(args.get("sheet_id", "")).strip()
        start_cell = str(args.get("start_cell", "A1") or "A1").strip()
        if not sheet_id:
            return tool_error("range or sheet_id is required")
        try:
            target_range = _build_range_from_start(sheet_id, start_cell, normalized_values)
        except ValueError as exc:
            return tool_error(str(exc))

    write_code, write_msg, write_data = _do_request(
        client,
        "PUT",
        _WRITE_RANGE_URI,
        paths={"spreadsheetToken": spreadsheet_token},
        body={
            "valueRange": {
                "range": target_range,
                "values": normalized_values,
            }
        },
    )
    if write_code != 0:
        return tool_error(
            f"Write spreadsheet range failed: code={write_code} msg={write_msg}",
            code=write_code,
            range=target_range,
        )

    return tool_result(
        {
            "success": True,
            "spreadsheet_token": spreadsheet_token,
            "requested_range": target_range,
            **write_data,
        }
    )


registry.register(
    name="feishu_sheet_read",
    toolset="feishu_sheet",
    schema=FEISHU_SHEET_READ_SCHEMA,
    handler=_handle_feishu_sheet_read,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Read Feishu spreadsheet structure and preview data",
    emoji="\U0001f4ca",
)

registry.register(
    name="feishu_sheet_write",
    toolset="feishu_sheet",
    schema=FEISHU_SHEET_WRITE_SCHEMA,
    handler=_handle_feishu_sheet_write,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Write data to a Feishu spreadsheet range",
    emoji="\u270f\ufe0f",
)
