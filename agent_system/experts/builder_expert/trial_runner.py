"""
TRIAL_RUN data ingestion — Stage 7 helper per EXPERT.md §7.

4 sources are described in the design doc. Only `paste` is fully wired in
this MVP — the other three record the user's input and mark the data as
"deferred until adapter integration" (Hermes 飞书 SDK / channel reader /
file upload pipeline). Real execution still depends on Task #8 后半段
giving us pipeline.steps to actually run.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------- source detection ----------

_URL_RE = re.compile(r"https?://\S+")


def detect_source_kind(user_message: str) -> str:
    """Heuristic mapping: paste / feishu_url / channel_ref / file_path."""
    msg = user_message.strip()
    if not msg:
        return "unknown"
    # Numbered choice (matches the ASK_SOURCE menu)
    if msg in {"1", "一"}:
        return "feishu_url"
    if msg in {"2", "二"}:
        return "paste"
    if msg in {"3", "三"}:
        return "channel_ref"
    if msg in {"4", "四"}:
        return "file_path"
    # Free-text inference
    if _URL_RE.search(msg):
        return "feishu_url" if "feishu" in msg.lower() or "larksuite" in msg.lower() else "url"
    # Existing-file path
    if msg.startswith("/") or msg.startswith("~"):
        return "file_path"
    # Hermes channel ref convention: "群:" / "频道:" / "channel:"
    if any(prefix in msg.lower() for prefix in ("群:", "频道:", "channel:", "ou_", "oc_")):
        return "channel_ref"
    # Default: treat as paste
    return "paste"


# ---------- per-source ingest ----------


def ingest_paste(user_message: str) -> dict[str, Any]:
    text = user_message.strip()
    return {
        "kind": "paste",
        "ok": bool(text),
        "data_ref": None,
        "size_chars": len(text),
        "preview": text[:300] + ("…" if len(text) > 300 else ""),
        "deferred": False,
        "note": None,
    }


def ingest_feishu_url(user_message: str) -> dict[str, Any]:
    m = _URL_RE.search(user_message)
    url = m.group(0) if m else user_message.strip()
    return {
        "kind": "feishu_url",
        "ok": bool(url),
        "data_ref": url,
        "size_chars": None,
        "preview": f"[飞书云文档链接已记录]\n{url}",
        "deferred": True,
        "note": "实际拉取内容需要接入 Hermes 飞书 SDK，本 MVP 仅记录引用。",
    }


def ingest_channel_ref(user_message: str) -> dict[str, Any]:
    return {
        "kind": "channel_ref",
        "ok": True,
        "data_ref": user_message.strip(),
        "size_chars": None,
        "preview": f"[Hermes 已接入数据源引用]\n{user_message.strip()}",
        "deferred": True,
        "note": "实际拉取需要 channel reader 适配器，本 MVP 仅记录引用。",
    }


def ingest_file_path(user_message: str) -> dict[str, Any]:
    raw = user_message.strip()
    p = Path(raw).expanduser()
    if not p.exists():
        return {
            "kind": "file_path",
            "ok": False,
            "data_ref": str(p),
            "size_chars": None,
            "preview": None,
            "deferred": False,
            "note": f"文件不存在：{p}",
        }
    if not p.is_file():
        return {
            "kind": "file_path",
            "ok": False,
            "data_ref": str(p),
            "size_chars": None,
            "preview": None,
            "deferred": False,
            "note": f"路径不是文件：{p}",
        }
    try:
        size = p.stat().st_size
        head = ""
        if size < 50_000:
            head = p.read_text(encoding="utf-8", errors="replace")[:300]
    except Exception as exc:
        return {
            "kind": "file_path",
            "ok": False,
            "data_ref": str(p),
            "size_chars": None,
            "preview": None,
            "deferred": False,
            "note": f"读取失败：{exc}",
        }
    return {
        "kind": "file_path",
        "ok": True,
        "data_ref": str(p),
        "size_chars": size,
        "preview": f"[文件 {p.name} · {size} bytes · 前 300 字]\n{head}",
        "deferred": True,
        "note": "文件已定位，但解析为 skill 输入需要 file pipeline 适配器（CSV/JSON/markdown 各异）。",
    }


_INGESTERS = {
    "paste": ingest_paste,
    "feishu_url": ingest_feishu_url,
    "url": ingest_feishu_url,  # treat generic URL like feishu URL for now
    "channel_ref": ingest_channel_ref,
    "file_path": ingest_file_path,
}


def ingest(user_message: str, kind: str | None = None) -> dict[str, Any]:
    """Dispatch to the right ingester. If kind not given, auto-detect."""
    if kind is None:
        kind = detect_source_kind(user_message)
    fn = _INGESTERS.get(kind)
    if fn is None:
        return {
            "kind": kind,
            "ok": False,
            "data_ref": None,
            "size_chars": None,
            "preview": None,
            "deferred": False,
            "note": f"无法识别数据源类型：{kind}",
        }
    return fn(user_message)


# ---------- summary rendering ----------


def render_trial_summary(intake: dict[str, Any], result: dict[str, Any], output_kind: str) -> str:
    """Briefing-style preview shown to user before they answer 是否符合预期."""
    lines: list[str] = []
    lines.append(f"**数据源**：{result['kind']}")
    if result.get("data_ref"):
        lines.append(f"**引用**：{result['data_ref']}")
    if result.get("size_chars") is not None:
        lines.append(f"**大小**：{result['size_chars']} 字符/字节")
    if result.get("note"):
        lines.append(f"⚠️ {result['note']}")
    if result.get("preview"):
        lines.append("")
        lines.append("**数据预览**：")
        lines.append("```")
        lines.append(result["preview"])
        lines.append("```")
    lines.append("")
    lines.append(
        "**预期产出类型**："
        f"`{output_kind}`（来自 INTAKE 第 4 题：{intake.get('output_type', '')}）"
    )
    if result.get("deferred"):
        lines.append(
            "\n⚠️ **注意**：本次未真正跑端到端（pipeline.steps 仍由 LLM 升级填充，"
            "且数据源适配器待接入）。这一步是流程闸门预览，给你确认下一步要不要 COMMIT。"
        )
    else:
        lines.append(
            "\n✓ 数据已就绪。pipeline.steps 仍空（待 LLM 升级），所以暂未跑出真实业务输出。"
        )
    return "\n".join(lines)
