#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any


NEGATIVE_TERMS = (
    "负面",
    "抱怨",
    "差评",
    "故障",
    "报错",
    "失败",
    "不达标",
    "扫不干净",
    "拖不干净",
    "污渍拖不干净",
    "颗粒物扫不",
    "水痕",
    "水印",
    "返工",
    "击穿",
    "维修",
    "退换",
    "流失风险",
    "售后与客服",
    "客服很差",
    "更麻烦",
    "无法解决",
)

RISK_CONTEXT_TERMS = (
    "退换",
    "维修",
    "故障",
    "抱怨",
    "上升",
    "高于",
    "不达标",
    "不干净",
    "击穿",
    "预警",
    "硬伤",
    "TOP项",
    "风险研判",
)

TREND_ONLY_TERMS = (
    "【回落】这周主动提起少了一些",
    "【回落】口碑热度回落",
)


@dataclass(frozen=True)
class MarkdownBlock:
    block_id: str
    kind: str
    raw_text: str
    start_line: int
    end_line: int
    level: int | None = None
    table: list[list[str]] = field(default_factory=list)
    ordered: bool = False

    @property
    def source_hash(self) -> str:
        return hashlib.sha256(self.raw_text.encode("utf-8")).hexdigest()


@dataclass
class ParseResult:
    blocks: list[MarkdownBlock]
    diagnostics: list[dict[str, Any]]


@dataclass(frozen=True)
class RenderedBlock:
    block_id: str
    html_text: str


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_table_separator(parts: list[str]) -> bool:
    return bool(parts) and all(part and set(part) <= {":", "-", " "} for part in parts)


def split_markdown_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or "|" not in stripped[1:]:
        return None
    content = stripped[1:-1] if stripped.endswith("|") else stripped[1:]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in content:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())
    return cells


def is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s+\S", line))


def is_list_item(line: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*+]\s+|\d+[.]\s+)", line))


def is_horizontal_rule(line: str) -> bool:
    return line.strip() in {"---", "***", "___"}


def parse_markdown(text: str) -> ParseResult:
    lines = text.splitlines()
    blocks: list[MarkdownBlock] = []
    diagnostics: list[dict[str, Any]] = []
    index = 0

    def next_block_id() -> str:
        return f"b{len(blocks) + 1:04d}"

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        start = index
        table_row = split_markdown_table_row(line)
        if table_row is not None:
            table_lines: list[str] = []
            table: list[list[str]] = []
            while index < len(lines):
                parts = split_markdown_table_row(lines[index])
                if parts is None:
                    break
                table_lines.append(lines[index])
                if not is_table_separator(parts):
                    table.append(parts)
                index += 1
            expected_cols = len(table[0]) if table else 0
            for offset, row in enumerate(table, start=1):
                if len(row) != expected_cols:
                    diagnostics.append(
                        {
                            "type": "table_column_mismatch",
                            "line": start + offset,
                            "expected_columns": expected_cols,
                            "actual_columns": len(row),
                            "row": row,
                        }
                    )
            blocks.append(
                MarkdownBlock(
                    block_id=next_block_id(),
                    kind="table",
                    raw_text="\n".join(table_lines),
                    start_line=start + 1,
                    end_line=index,
                    table=table,
                )
            )
            continue

        if is_heading(line):
            match = re.match(r"^(#{1,6})\s+(.*)$", line)
            assert match is not None
            blocks.append(
                MarkdownBlock(
                    block_id=next_block_id(),
                    kind="heading",
                    raw_text=line,
                    start_line=start + 1,
                    end_line=start + 1,
                    level=len(match.group(1)),
                )
            )
            index += 1
            continue

        if is_horizontal_rule(line):
            blocks.append(
                MarkdownBlock(
                    block_id=next_block_id(),
                    kind="hr",
                    raw_text=line,
                    start_line=start + 1,
                    end_line=start + 1,
                )
            )
            index += 1
            continue

        if is_list_item(line):
            list_lines: list[str] = []
            ordered = bool(re.match(r"^\s*\d+[.]\s+", line))
            while index < len(lines) and is_list_item(lines[index]):
                list_lines.append(lines[index])
                index += 1
            blocks.append(
                MarkdownBlock(
                    block_id=next_block_id(),
                    kind="list",
                    raw_text="\n".join(list_lines),
                    start_line=start + 1,
                    end_line=index,
                    ordered=ordered,
                )
            )
            continue

        paragraph_lines: list[str] = []
        while index < len(lines):
            current = lines[index]
            if not current.strip():
                break
            if paragraph_lines and (
                is_heading(current)
                or split_markdown_table_row(current) is not None
                or is_list_item(current)
                or is_horizontal_rule(current)
            ):
                break
            paragraph_lines.append(current)
            index += 1
        blocks.append(
            MarkdownBlock(
                block_id=next_block_id(),
                kind="paragraph",
                raw_text="\n".join(paragraph_lines),
                start_line=start + 1,
                end_line=index,
            )
        )

    return ParseResult(blocks=blocks, diagnostics=diagnostics)


def strip_markdown_marks(text: str) -> str:
    return re.sub(r"[*_`]+", "", text).strip()


def is_negative_text(text: str) -> bool:
    normalized = strip_markdown_marks(text)
    if any(term in normalized for term in TREND_ONLY_TERMS) and not any(
        term in normalized for term in ("抱怨", "故障", "问题", "风险", "不达标")
    ):
        return False
    if any(term in normalized for term in NEGATIVE_TERMS):
        return True
    if ("FRR" in normalized or "FFR" in normalized or "风险" in normalized) and any(
        term in normalized for term in RISK_CONTEXT_TERMS
    ):
        return True
    return False


def render_inline(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    escaped = escaped.replace("&lt;br&gt;", "<br>").replace("&lt;br/&gt;", "<br>").replace("&lt;br /&gt;", "<br>")
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def render_trend_label(text: str, *, negative: bool) -> str:
    match = re.match(r"^(【[^】]+】)(.*)$", text, flags=re.DOTALL)
    if not match:
        return render_inline(text)
    label, rest = match.groups()
    if "平稳" in label:
        tag_class = "tag-green"
    elif "升温" in label or "恶化" in label:
        tag_class = "tag-red" if negative else "tag-orange"
    elif "回落" in label:
        tag_class = "tag-red" if negative else "tag-blue"
    else:
        tag_class = "tag-red" if negative else "tag-blue"
    return f'<span class="tag {tag_class}">{render_inline(label)}</span>{render_inline(rest)}'


def render_table_cell(cell: str, *, header: bool = False) -> str:
    if header:
        return render_inline(cell)
    return render_trend_label(cell, negative=is_negative_text(cell))


def block_attrs(block: MarkdownBlock, extra_classes: tuple[str, ...] = ()) -> str:
    classes = [f"md-{block.kind}"]
    classes.extend(extra_classes)
    if is_negative_text(block.raw_text):
        classes.append("sentiment-negative")
    return (
        f'class="{" ".join(classes)}" '
        f'data-source-block-id="{block.block_id}" '
        f'data-source-hash="{block.source_hash}" '
        f'data-source-lines="{block.start_line}-{block.end_line}"'
    )


def slugify(text: str, fallback: str) -> str:
    compact = re.sub(r"\s+", "-", strip_markdown_marks(text))
    compact = re.sub(r"[^\w\u4e00-\u9fff-]+", "", compact)
    return compact[:80] or fallback


def render_heading(block: MarkdownBlock) -> str:
    text = re.sub(r"^#{1,6}\s+", "", block.raw_text).strip()
    level = min(max(block.level or 2, 1), 6)
    anchor = slugify(text, block.block_id)
    extra: list[str] = []
    if "X 系" in text:
        extra.append("x-title")
    if "T 系" in text:
        extra.append("t-title")
    return f'<h{level} id="{html.escape(anchor)}" {block_attrs(block, tuple(extra))}>{render_inline(text)}</h{level}>'


def list_items(block: MarkdownBlock) -> list[str]:
    return [re.sub(r"^\s*(?:[-*+]\s+|\d+[.]\s+)", "", line).strip() for line in block.raw_text.splitlines()]


def is_summary_list(block: MarkdownBlock) -> bool:
    items = list_items(block)
    joined = "\n".join(items)
    return block.ordered and len(items) == 3 and "X 系" in joined and "T 系" in joined and "服务链路" in joined


def is_pm_insight(block: MarkdownBlock) -> bool:
    return block.kind == "paragraph" and strip_markdown_marks(block.raw_text).startswith("PM 总结提炼：")


def is_action_list(block: MarkdownBlock) -> bool:
    items = list_items(block)
    return block.kind == "list" and not block.ordered and bool(items) and all(item.startswith("**") for item in items)


def is_data_boundary_heading(block: MarkdownBlock) -> bool:
    return block.kind == "heading" and strip_markdown_marks(re.sub(r"^#{1,6}\s+", "", block.raw_text)).strip() == "数据边界说明"


def summary_card_class(item: str, index: int) -> str:
    if "X 系" in item:
        return "x"
    if "T 系" in item:
        return "t"
    if "服务链路" in item:
        return "s"
    return ("x", "t", "s")[min(index, 2)]


def render_summary_list(block: MarkdownBlock) -> str:
    cards: list[str] = []
    for index, item in enumerate(list_items(block)):
        card_class = summary_card_class(item, index)
        title_match = re.match(r"\*\*(.+?：)(.+?)\*\*$", item)
        if title_match:
            title = title_match.group(1)
            body = title_match.group(2)
            card_body = f"<h4>{render_inline(title)}</h4><p>{render_inline(body)}</p>"
        else:
            card_body = f"<p>{render_inline(item)}</p>"
        cards.append(f'<div class="summary-card {card_class}">{card_body}</div>')
    return f'<div {block_attrs(block, ("summary-grid",))}>' + "\n".join(cards) + "</div>"


def render_pm_insight(block: MarkdownBlock) -> str:
    insight_classes = ["pm-insight"]
    if "X 系" in block.raw_text:
        insight_classes.append("x-insight")
    if "T 系" in block.raw_text:
        insight_classes.append("t-insight")
    paragraph = render_inline(block.raw_text).replace("\n", "<br>")
    return f'<div {block_attrs(block, tuple(insight_classes))}>{paragraph}</div>'


def render_list(block: MarkdownBlock) -> str:
    if is_summary_list(block):
        return render_summary_list(block)
    tag = "ol" if block.ordered else "ul"
    items: list[str] = []
    for item in list_items(block):
        css_class = ' class="risk-negative"' if is_negative_text(item) else ""
        items.append(f"<li{css_class}>{render_inline(item)}</li>")
    return f'<{tag} {block_attrs(block)}>' + "\n".join(items) + f"</{tag}>"


def render_table(block: MarkdownBlock) -> str:
    if not block.table:
        return f'<div {block_attrs(block, ("table-wrapper", "empty-table"))}></div>'
    header = block.table[0]
    rows = block.table[1:]
    parts = [f'<div {block_attrs(block, ("table-wrapper",))}><table>']
    parts.append("<thead><tr>")
    for cell in header:
        parts.append(f"<th>{render_table_cell(cell, header=True)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in rows:
        row_class = ' class="sentiment-negative"' if any(is_negative_text(cell) for cell in row) else ""
        parts.append(f"<tr{row_class}>")
        for cell in row:
            cell_class = ' class="risk-negative"' if is_negative_text(cell) else ""
            parts.append(f"<td{cell_class}>{render_table_cell(cell)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "\n".join(parts)


def render_block(block: MarkdownBlock) -> str:
    if block.kind == "heading":
        return render_heading(block)
    if block.kind == "table":
        return render_table(block)
    if block.kind == "list":
        return render_list(block)
    if block.kind == "hr":
        return f"<hr {block_attrs(block)}>"
    if is_pm_insight(block):
        return render_pm_insight(block)
    paragraph = render_inline(block.raw_text).replace("\n", "<br>")
    return f"<p {block_attrs(block)}>{paragraph}</p>"


def build_nav(blocks: list[MarkdownBlock]) -> str:
    links: list[str] = []
    for block in blocks:
        if block.kind != "heading" or block.level not in {1, 2, 3}:
            continue
        text = re.sub(r"^#{1,6}\s+", "", block.raw_text).strip()
        anchor = slugify(text, block.block_id)
        css_class = f"level-{block.level}"
        links.append(f'<a class="{css_class}" href="#{html.escape(anchor)}">{render_inline(text)}</a>')
    return "\n".join(links)


def render_action_card(heading: MarkdownBlock, action_list: MarkdownBlock) -> str:
    return '<div class="action-card">' + render_heading(heading) + render_list(action_list) + "</div>"


def render_data_boundary(heading: MarkdownBlock, boundary_list: MarkdownBlock) -> str:
    return '<footer class="data-boundary">' + render_heading(heading) + render_list(boundary_list) + "</footer>"


def render_document(blocks: list[MarkdownBlock]) -> str:
    rendered: list[str] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if block.kind == "heading" and block.level == 3 and index + 1 < len(blocks) and is_action_list(blocks[index + 1]):
            cards: list[str] = []
            while (
                index + 1 < len(blocks)
                and blocks[index].kind == "heading"
                and blocks[index].level == 3
                and is_action_list(blocks[index + 1])
            ):
                cards.append(render_action_card(blocks[index], blocks[index + 1]))
                index += 2
            rendered.append('<div class="action-grid">' + "\n".join(cards) + "</div>")
            continue
        if is_data_boundary_heading(block) and index + 1 < len(blocks) and blocks[index + 1].kind == "list":
            rendered.append(render_data_boundary(block, blocks[index + 1]))
            index += 2
            continue
        rendered.append(render_block(block))
        index += 1
    return "\n".join(rendered)


def build_html(report_title: str, blocks: list[MarkdownBlock], *, theme: str = "ai_studio") -> str:
    if theme != "ai_studio":
        raise ValueError(f"Unsupported theme: {theme}")
    rendered_blocks = render_document(blocks)
    nav = build_nav(blocks)
    generated_at = datetime.now(timezone.utc).isoformat()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(report_title)}</title>
  <style>
    :root {{
      --primary-blue: #003a8c;
      --x-purple: #722ed1;
      --t-blue: #1890ff;
      --bg-gray: #f0f2f5;
      --card-bg: #ffffff;
      --text-main: #262626;
      --text-sec: #595959;
      --danger: #ff4d4f;
      --warning: #faad14;
      --success: #52c41a;
      --border: #d9d9d9;
      --risk-soft: #fff1f0;
      --risk-line: #ffa39e;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
      background-color: var(--bg-gray);
      color: var(--text-main);
      line-height: 1.6;
      display: flex;
    }}
    .sidebar {{
      width: 240px;
      background: #001529;
      color: white;
      position: fixed;
      height: 100vh;
      padding: 20px 0;
      overflow-y: auto;
      z-index: 100;
      top: 0;
      left: 0;
    }}
    .sidebar h2 {{
      font-size: 16px;
      padding: 0 20px;
      margin-bottom: 18px;
      color: var(--t-blue);
      text-transform: uppercase;
      letter-spacing: 1px;
      line-height: 1.4;
    }}
    .sidebar a {{
      display: block;
      color: #ffffffa6;
      text-decoration: none;
      padding: 11px 20px;
      font-size: 14px;
      transition: 0.3s;
      border-left: 3px solid transparent;
    }}
    .sidebar a:hover {{ color: white; background: #1890ff33; }}
    .sidebar a.active {{ color: white; background: var(--t-blue); border-left-color: #fff; }}
    .sidebar a.level-1 {{ font-weight: 700; color: #fff; }}
    .sidebar a.level-3 {{ padding-left: 30px; font-size: 12px; color: #ffffff8f; }}
    .main-content {{
      margin-left: 240px;
      flex: 1;
      padding: 40px;
      max-width: 1480px;
    }}
    .container {{
      background: var(--card-bg);
      padding: 40px;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }}
    .meta-info {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin: 15px 0 28px;
      font-size: 13px;
      color: var(--text-sec);
      background: #f9f9f9;
      padding: 15px;
      border-radius: 4px;
      border: 1px solid var(--border);
    }}
    h1 {{
      font-size: 26px;
      color: var(--primary-blue);
      border-bottom: 2px solid #eee;
      padding-bottom: 20px;
      margin-bottom: 0;
    }}
    h2 {{
      margin-top: 40px;
      padding-bottom: 10px;
      border-bottom: 2px solid #eee;
      color: var(--primary-blue);
      display: flex;
      align-items: center;
    }}
    h2::before {{
      content: "";
      display: inline-block;
      width: 6px;
      height: 24px;
      background: var(--primary-blue);
      margin-right: 12px;
      border-radius: 2px;
    }}
    h2.x-title {{ color: var(--x-purple); }}
    h2.x-title::before {{ background: var(--x-purple); }}
    h2.t-title {{ color: var(--t-blue); }}
    h2.t-title::before {{ background: var(--t-blue); }}
    h3 {{ margin: 25px 0 15px; font-size: 18px; color: var(--text-main); }}
    h4 {{ margin: 18px 0 12px; color: var(--primary-blue); }}
    p, ul, ol {{ font-size: 14px; margin: 12px 0; }}
    ul, ol {{ padding-left: 22px; }}
    li {{ margin-bottom: 8px; }}
    code {{ background: #f4f6f8; padding: 1px 5px; border-radius: 4px; color: var(--primary-blue); }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; padding-left: 0; }}
    .summary-card {{ padding: 20px; border-radius: 8px; border-top: 4px solid; background: #fff; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
    .summary-card h4 {{ margin: 0 0 10px; font-size: 15px; }}
    .summary-card p {{ margin: 0; }}
    .summary-card.x {{ border-top-color: var(--x-purple); background: #f9f0ff; }}
    .summary-card.t {{ border-top-color: var(--t-blue); background: #e6f7ff; }}
    .summary-card.s {{ border-top-color: var(--warning); background: #fffbe6; }}
    .pm-insight {{ background: #e6f7ff; border-left: 5px solid var(--t-blue); padding: 20px; margin: 20px 0; border-radius: 0 4px 4px 0; font-size: 14px; }}
    .pm-insight strong:first-child {{ color: var(--primary-blue); display: block; margin-bottom: 5px; }}
    .pm-insight.x-insight {{ background: #f9f0ff; border-left-color: var(--x-purple); }}
    .pm-insight.t-insight {{ background: #e6f7ff; border-left-color: var(--t-blue); }}
    .table-wrapper {{ overflow-x: auto; margin: 20px 0; border: 1px solid var(--border); border-radius: 4px; background: white; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; min-width: 1180px; }}
    th {{ background: #fafafa; padding: 12px 10px; border: 1px solid var(--border); text-align: left; font-weight: 600; color: var(--text-main); }}
    td {{ padding: 12px 10px; border: 1px solid var(--border); vertical-align: top; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    tr:hover {{ background: #f0f7ff; }}
    .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin: 0 4px 4px 0; }}
    .tag-red {{ background: #fff1f0; color: var(--danger); border: 1px solid #ffa39e; }}
    .tag-blue {{ background: #e6f7ff; color: var(--t-blue); border: 1px solid #91d5ff; }}
    .tag-green {{ background: #f6ffed; color: var(--success); border: 1px solid #b7eb8f; }}
    .tag-orange {{ background: #fff7e6; color: var(--warning); border: 1px solid #ffd591; }}
    .risk-negative {{
      color: var(--danger);
      font-weight: 700;
      background: var(--risk-soft);
      border-color: var(--risk-line);
    }}
    tr.sentiment-negative td {{ background: linear-gradient(90deg, rgba(255,241,240,.92), rgba(255,255,255,.98)); }}
    p.sentiment-negative, li.risk-negative, .pm-insight.sentiment-negative {{
      border-left: 5px solid var(--danger);
      background: var(--risk-soft);
      padding: 12px 14px;
      border-radius: 0 4px 4px 0;
    }}
    .action-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 20px; }}
    .action-card {{ border: 1px solid var(--border); padding: 20px; border-radius: 8px; background: #fff; }}
    .action-card h3 {{ margin: 0 0 15px; border-bottom: 2px solid #eee; padding-bottom: 8px; color: var(--primary-blue); font-size: 16px; }}
    .action-card ul {{ padding-left: 18px; }}
    .action-card li {{ margin-bottom: 10px; }}
    .data-boundary {{
      margin-top: 50px;
      padding-top: 20px;
      border-top: 1px solid #eee;
      font-size: 12px;
      color: #888;
      display: block;
    }}
    .data-boundary h4 {{ margin-top: 0; color: #888; }}
    .generated-note {{ margin-top: 24px; font-size: 12px; color: #999; }}
    @media (max-width: 1200px) {{
      .summary-grid, .action-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 900px) {{
      body {{ display: block; }}
      .sidebar {{ position: relative; width: 100%; height: auto; }}
      .main-content {{ margin-left: 0; padding: 20px; }}
      .container {{ padding: 24px; }}
    }}
  </style>
</head>
<body>
  <nav class="sidebar">
      <h2>VOC 深度洞察</h2>
      {nav}
  </nav>
  <div class="main-content">
      <article class="container">
        {rendered_blocks}
        <div class="meta-info generated-note">生成时间 UTC：{html.escape(generated_at)}；渲染模式：严格无损；红色标识：明确负面 / 风险内容；本 HTML 为 Markdown 正式报告的派生产物。</div>
      </article>
  </div>
  <script>
    window.addEventListener('scroll', () => {{
      let current = '';
      const headings = document.querySelectorAll('.container h1[id], .container h2[id], .container h3[id]');
      const navLinks = document.querySelectorAll('.sidebar a');
      headings.forEach(heading => {{
        if (window.pageYOffset >= heading.offsetTop - 150) {{
          current = heading.getAttribute('id') || '';
        }}
      }});
      navLinks.forEach(link => {{
        link.classList.remove('active');
        if (link.getAttribute('href') === `#${{current}}`) {{
          link.classList.add('active');
        }}
      }});
    }});
  </script>
</body>
</html>
"""


def block_visible_text(block: MarkdownBlock) -> str:
    if block.kind == "heading":
        return markdown_visible_text(re.sub(r"^#{1,6}\s+", "", block.raw_text).strip())
    if block.kind == "table":
        return "\n".join(" ".join(markdown_visible_text(cell) for cell in row) for row in block.table)
    if block.kind == "list":
        return "\n".join(markdown_visible_text(item) for item in list_items(block))
    if block.kind == "hr":
        return ""
    return markdown_visible_text(block.raw_text)


def normalize_visible_text(text: str) -> str:
    return re.sub(r"\s+", "", html.unescape(text))


def markdown_visible_text(text: str) -> str:
    with_breaks = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return strip_markdown_marks(with_breaks)


def source_visible_text(blocks: list[MarkdownBlock]) -> str:
    return normalize_visible_text("\n".join(block_visible_text(block) for block in blocks))


class SourceTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.active_stack: list[str] = []
        self.source_depths: list[int] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        block_id = attr_map.get("data-source-block-id")
        if block_id is not None:
            self.active_stack.append(block_id)
            self.source_depths.append(1)
            self.parts.append("\n")
            if tag == "hr":
                self.active_stack.pop()
                self.source_depths.pop()
        elif self.active_stack and tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self.source_depths[-1] += 1
        if self.active_stack and tag in {"br", "tr", "th", "td", "li", "p", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.active_stack and tag in {"tr", "th", "td", "li", "p", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")
        if self.active_stack:
            self.source_depths[-1] -= 1
        if self.active_stack and self.source_depths and self.source_depths[-1] <= 0:
            self.active_stack.pop()
            self.source_depths.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if dict(attrs).get("data-source-block-id") is not None:
            self.handle_starttag(tag, attrs)
            return
        if self.active_stack and tag in {"br", "tr", "th", "td", "li", "p", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.active_stack:
            self.parts.append(data)


def rendered_source_visible_text(rendered_html: str) -> str:
    extractor = SourceTextExtractor()
    extractor.feed(rendered_html)
    return normalize_visible_text("".join(extractor.parts))


def build_audit(parse_result: ParseResult, rendered_html: str, input_md: Path, output_html: Path) -> dict[str, Any]:
    block_ids = [block.block_id for block in parse_result.blocks]
    rendered_ids = re.findall(r'data-source-block-id="([^"]+)"', rendered_html)
    missing = [block_id for block_id in block_ids if block_id not in rendered_ids]
    duplicate_rendered_ids = sorted({block_id for block_id in rendered_ids if rendered_ids.count(block_id) > 1})
    table_column_mismatches = [d for d in parse_result.diagnostics if d.get("type") == "table_column_mismatch"]
    negative_blocks = [block.block_id for block in parse_result.blocks if is_negative_text(block.raw_text)]
    source_text = source_visible_text(parse_result.blocks)
    rendered_text = rendered_source_visible_text(rendered_html)
    visible_text_matches = source_text == rendered_text
    return {
        "audit_version": "2026-04-10.voc_dashboard_html.v1",
        "input_md": str(input_md),
        "output_html": str(output_html),
        "input_sha256": source_hash(input_md.read_text(encoding="utf-8")),
        "source_block_count": len(block_ids),
        "rendered_block_reference_count": len(rendered_ids),
        "missing_block_ids": missing,
        "duplicate_rendered_block_ids": duplicate_rendered_ids,
        "table_count": sum(1 for block in parse_result.blocks if block.kind == "table"),
        "table_column_mismatches": table_column_mismatches,
        "negative_block_ids": negative_blocks,
        "source_visible_text_sha256": source_hash(source_text),
        "rendered_visible_text_sha256": source_hash(rendered_text),
        "visible_text_matches": visible_text_matches,
        "diagnostics": parse_result.diagnostics,
        "strict_passed": not missing and not duplicate_rendered_ids and not table_column_mismatches and visible_text_matches,
    }


def infer_report_title(blocks: list[MarkdownBlock], fallback: str) -> str:
    for block in blocks:
        if block.kind == "heading" and block.level == 1:
            return re.sub(r"^#\s+", "", block.raw_text).strip()
    return fallback


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_dashboard(
    *,
    input_md: Path,
    output_html: Path,
    manifest_path: Path,
    audit_path: Path,
    strict: bool,
    theme: str = "ai_studio",
) -> dict[str, Any]:
    markdown_text = input_md.read_text(encoding="utf-8")
    parse_result = parse_markdown(markdown_text)
    title = infer_report_title(parse_result.blocks, input_md.stem)
    rendered_html = build_html(title, parse_result.blocks, theme=theme)
    audit = build_audit(parse_result, rendered_html, input_md, output_html)
    if strict and not audit["strict_passed"]:
        write_json(audit_path, audit)
        raise SystemExit(f"Strict lossless audit failed; see {audit_path}")

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(rendered_html, encoding="utf-8")
    write_json(audit_path, audit)
    manifest = {
        "manifest_version": "2026-04-10.voc_dashboard_html.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_md": str(input_md),
        "output_html": str(output_html),
        "audit": str(audit_path),
        "strict": strict,
        "theme": theme,
        "strict_passed": audit["strict_passed"],
        "input_sha256": audit["input_sha256"],
        "output_sha256": source_hash(rendered_html),
    }
    write_json(manifest_path, manifest)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a strict, lossless VOC Markdown dashboard as static HTML.")
    parser.add_argument("--input-md", required=True, help="Formal VOC Markdown report path.")
    parser.add_argument("--output-html", required=True, help="Output HTML dashboard path.")
    parser.add_argument("--manifest", required=True, help="Output artifact manifest JSON path.")
    parser.add_argument("--audit", required=True, help="Output lossless audit JSON path.")
    parser.add_argument("--strict", action="store_true", help="Fail when any source block or table cell is not preserved.")
    parser.add_argument("--theme", default="ai_studio", choices=("ai_studio",), help="HTML visual theme.")
    args = parser.parse_args()

    audit = render_dashboard(
        input_md=Path(args.input_md).expanduser().resolve(),
        output_html=Path(args.output_html).expanduser().resolve(),
        manifest_path=Path(args.manifest).expanduser().resolve(),
        audit_path=Path(args.audit).expanduser().resolve(),
        strict=args.strict,
        theme=args.theme,
    )
    print(json.dumps({"strict_passed": audit["strict_passed"], "source_block_count": audit["source_block_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
