"""
DRY_RUN mock data generator — Stage 6 helper.

Picks a canned mock payload by keyword-matching the intake's `input_type`.
This is intentionally a deterministic lookup; LLM-driven mock synthesis is
deferred until the LLM upgrade slice (Task #8 second half) gives skills real
content to consume.
"""

from __future__ import annotations

from typing import Any


# Canned payloads. Each picked by keyword presence in input_type / output_type.
# The shapes mirror what existing Hermes skills (voc_insight, ops_dashboard, audit)
# tend to receive, so down-the-line a real skill should be able to consume them.
_MOCK_LIBRARY: dict[str, dict[str, Any]] = {
    "voc": {
        "source": "mock_voc",
        "items": [
            {"id": "v001", "channel": "taobao", "rating": 1, "text": "包装破损，物流太慢，再也不会买了。"},
            {"id": "v002", "channel": "taobao", "rating": 2, "text": "尺码偏小，建议买大一码。"},
            {"id": "v003", "channel": "taobao", "rating": 1, "text": "客服回复慢，问题没解决。"},
        ],
    },
    "ticket": {
        "source": "mock_ticket",
        "items": [
            {"id": "t001", "category": "退款", "status": "open", "summary": "用户申请整单退款，原因：尺码不合适"},
            {"id": "t002", "category": "物流", "status": "open", "summary": "快递异常派送 3 天未送达"},
        ],
    },
    "competitor": {
        "source": "mock_competitor",
        "items": [
            {"brand": "A", "review_count": 1234, "avg_rating": 4.6, "top_complaint": "续航差"},
            {"brand": "B", "review_count": 980,  "avg_rating": 4.2, "top_complaint": "做工粗糙"},
        ],
    },
    "file": {
        "source": "mock_file_upload",
        "filename": "sample.csv",
        "rows": [
            {"col_a": 1, "col_b": "alpha"},
            {"col_a": 2, "col_b": "beta"},
        ],
    },
    "generic": {
        "source": "mock_generic",
        "payload": {"note": "未匹配到专用 mock，给一个通用 payload 占位"},
    },
}


_KEYWORD_TO_KIND: list[tuple[tuple[str, ...], str]] = [
    (("voc", "评论", "差评", "好评"), "voc"),
    (("工单", "ticket", "客服"), "ticket"),
    (("竞品", "competitor", "对标"), "competitor"),
    (("文件", "上传", "csv", "json"), "file"),
]


def _pick_kind(input_type: str) -> str:
    msg = (input_type or "").lower()
    for keywords, kind in _KEYWORD_TO_KIND:
        if any(kw in msg for kw in keywords):
            return kind
    return "generic"


def make_mock(intake: dict[str, Any]) -> dict[str, Any]:
    """Pick a canned mock dict based on intake.input_type."""
    kind = _pick_kind(intake.get("input_type", ""))
    return {"_mock_kind": kind, **_MOCK_LIBRARY[kind]}


# Output expectation check — same kind of keyword match against intake.output_type.
# Returns (ok, reason) so handle_dry_run can include it in the response.
_OUTPUT_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("报告", "report", "markdown"), "report"),
    (("清单", "列表", "list"), "list"),
    (("看板", "dashboard"), "dashboard"),
    (("回复", "对话", "答复"), "reply"),
    (("数据库", "db", "写入"), "db_write"),
]


def output_kind(output_type: str) -> str:
    msg = (output_type or "").lower()
    for keywords, kind in _OUTPUT_KEYWORDS:
        if any(kw in msg for kw in keywords):
            return kind
    return "unknown"
