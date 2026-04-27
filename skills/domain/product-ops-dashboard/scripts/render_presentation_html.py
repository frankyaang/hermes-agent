#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class MarkdownBlock:
    block_type: str
    text: str = ""
    items: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class SectionNode:
    level: int
    title: str
    anchor: str
    blocks: list[MarkdownBlock] = field(default_factory=list)
    children: list["SectionNode"] = field(default_factory=list)


HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
SEPARATOR_RE = re.compile(r"^\s*:?-{3,}:?\s*$")


def slugify_heading(text: str, used: dict[str, int]) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.strip().lower()).strip("-") or "section"
    counter = used.get(normalized, 0)
    used[normalized] = counter + 1
    return normalized if counter == 0 else f"{normalized}-{counter + 1}"


def split_markdown_row(line: str) -> list[str]:
    trimmed = line.strip().strip("|")
    return [cell.strip() for cell in trimmed.split("|")]


def is_markdown_table(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    separator_cells = split_markdown_row(lines[1])
    return bool(separator_cells) and all(SEPARATOR_RE.match(cell) for cell in separator_cells)


def flush_block(buffer_type: str | None, buffer_lines: list[str], current_node: SectionNode) -> None:
    if not buffer_type or not buffer_lines:
        return
    if buffer_type == "paragraph":
        text = " ".join(line.strip() for line in buffer_lines if line.strip())
        if text:
            current_node.blocks.append(MarkdownBlock(block_type="paragraph", text=text))
    elif buffer_type == "list":
        items = [line.strip()[2:].strip() for line in buffer_lines if line.strip().startswith("- ")]
        if items:
            current_node.blocks.append(MarkdownBlock(block_type="list", items=items))
    elif buffer_type == "table" and is_markdown_table(buffer_lines):
        table_rows = [split_markdown_row(line) for line in buffer_lines]
        current_node.blocks.append(
            MarkdownBlock(
                block_type="table",
                headers=table_rows[0],
                rows=table_rows[2:],
            )
        )


def parse_markdown_document(markdown_text: str) -> tuple[str, SectionNode]:
    document_title = "正式汇报稿"
    root = SectionNode(level=0, title="root", anchor="root")
    stack: list[SectionNode] = [root]
    current_node = root
    buffer_type: str | None = None
    buffer_lines: list[str] = []
    used_anchors: dict[str, int] = {}

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip("\n")
        heading_match = HEADING_RE.match(line)
        if heading_match:
            flush_block(buffer_type, buffer_lines, current_node)
            buffer_type = None
            buffer_lines = []
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            if level == 1:
                document_title = title or document_title
                continue
            anchor = slugify_heading(title, used_anchors)
            while stack and stack[-1].level >= level:
                stack.pop()
            node = SectionNode(level=level, title=title, anchor=anchor)
            stack[-1].children.append(node)
            stack.append(node)
            current_node = node
            continue

        if not line.strip():
            flush_block(buffer_type, buffer_lines, current_node)
            buffer_type = None
            buffer_lines = []
            continue

        next_type = "paragraph"
        if line.startswith("- "):
            next_type = "list"
        elif line.lstrip().startswith("|"):
            next_type = "table"

        if buffer_type not in {None, next_type}:
            flush_block(buffer_type, buffer_lines, current_node)
            buffer_lines = []
        buffer_type = next_type
        buffer_lines.append(line)

    flush_block(buffer_type, buffer_lines, current_node)
    return document_title, root


def render_inline(text: str) -> str:
    parts = re.split(r"(`[^`]+`)", text)
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) >= 2:
            rendered.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            escaped = html.escape(part)
            escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
            rendered.append(escaped)
    return "".join(rendered)


def render_block(block: MarkdownBlock) -> str:
    if block.block_type == "paragraph":
        return f"<p>{render_inline(block.text)}</p>"
    if block.block_type == "list":
        items = []
        for item in block.items:
            css_class = ""
            if item.startswith("证据锚点："):
                css_class = ' class="bullet-evidence"'
            elif item.startswith("这意味着："):
                css_class = ' class="bullet-implication"'
            elif item.startswith("当前边界：") or item.startswith("补数方向："):
                css_class = ' class="bullet-boundary"'
            items.append(f"<li{css_class}>{render_inline(item)}</li>")
        return f"<ul class=\"bullet-list\">{''.join(items)}</ul>"
    if block.block_type == "table":
        header_html = "".join(f"<th>{render_inline(cell)}</th>" for cell in block.headers)
        row_html = []
        for row in block.rows:
            cells = "".join(f"<td>{render_inline(cell)}</td>" for cell in row)
            row_html.append(f"<tr>{cells}</tr>")
        return (
            "<div class=\"table-wrapper\">"
            "<table>"
            f"<thead><tr>{header_html}</tr></thead>"
            f"<tbody>{''.join(row_html)}</tbody>"
            "</table>"
            "</div>"
        )
    return ""


def collect_toc(node: SectionNode) -> list[tuple[int, str, str]]:
    items: list[tuple[int, str, str]] = []
    for child in node.children:
        items.append((child.level, child.title, child.anchor))
        items.extend(collect_toc(child))
    return items


def render_node(node: SectionNode) -> str:
    tag = {2: "section", 3: "section", 4: "article"}.get(node.level, "section")
    css_class = {2: "chapter-card", 3: "subsection-card", 4: "detail-card"}.get(node.level, "content-card")
    heading_tag = {2: "h2", 3: "h3", 4: "h4"}.get(node.level, "h3")
    content = [f"<{tag} id=\"{node.anchor}\" class=\"{css_class}\">"]
    content.append(f"<{heading_tag}>{render_inline(node.title)}</{heading_tag}>")
    for block in node.blocks:
        content.append(render_block(block))
    for child in node.children:
        content.append(render_node(child))
    content.append(f"</{tag}>")
    return "".join(content)


def render_report_html(
    markdown_text: str,
    *,
    source_path: str,
    generated_at: str,
    report_title: str | None = None,
) -> str:
    title, root = parse_markdown_document(markdown_text)
    toc_items = collect_toc(root)
    chapter_count = sum(1 for level, _, _ in toc_items if level == 2)
    section_count = sum(1 for level, _, _ in toc_items if level == 3)
    detail_count = sum(1 for level, _, _ in toc_items if level == 4)
    table_count = markdown_text.count("\n| ")
    page_title = report_title or title

    toc_html = "".join(
        f"<a class=\"toc-link level-{level}\" href=\"#{anchor}\">{html.escape(text)}</a>"
        for level, text, anchor in toc_items
    )
    content_html = "".join(render_node(node) for node in root.children)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(page_title)}</title>
  <style>
    :root {{
      --bg-page: #f5f3ee;
      --bg-card: #fffdf8;
      --bg-panel: #f7f4ee;
      --ink-strong: #16202a;
      --ink-main: #334155;
      --ink-soft: #64748b;
      --line: #e7dccf;
      --accent: #0f766e;
      --accent-soft: #dff5f1;
      --accent-warm: #b45309;
      --accent-warm-soft: #fff2df;
      --accent-danger: #b91c1c;
      --accent-danger-soft: #fde8e8;
      --shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
      --radius-xl: 24px;
      --radius-lg: 18px;
      --radius-md: 12px;
      --font-sans: "Plus Jakarta Sans", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
      --font-mono: "JetBrains Mono", "SFMono-Regular", "Menlo", monospace;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: var(--font-sans);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.10), transparent 28%),
        radial-gradient(circle at top right, rgba(180, 83, 9, 0.10), transparent 26%),
        var(--bg-page);
      color: var(--ink-main);
      line-height: 1.72;
    }}
    a {{ color: inherit; text-decoration: none; }}
    code {{
      font-family: var(--font-mono);
      background: rgba(15, 118, 110, 0.08);
      color: var(--accent);
      padding: 0.14rem 0.45rem;
      border-radius: 999px;
      font-size: 0.92em;
    }}
    .page {{
      max-width: 1600px;
      margin: 0 auto;
      padding: 28px;
    }}
    .hero {{
      background:
        linear-gradient(135deg, rgba(22, 32, 42, 0.96), rgba(15, 118, 110, 0.94)),
        linear-gradient(135deg, rgba(180, 83, 9, 0.18), rgba(15, 118, 110, 0.12));
      color: #f8fafc;
      border-radius: 30px;
      padding: 34px 38px;
      box-shadow: var(--shadow);
      margin-bottom: 26px;
      position: relative;
      overflow: hidden;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -70px -70px auto;
      width: 220px;
      height: 220px;
      background: rgba(255,255,255,0.06);
      border-radius: 50%;
    }}
    .hero h1 {{
      margin: 0 0 14px;
      font-size: clamp(28px, 4vw, 42px);
      line-height: 1.12;
      letter-spacing: 0.02em;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 0 0 18px;
      color: rgba(248, 250, 252, 0.88);
      font-size: 14px;
    }}
    .hero-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(255,255,255,0.10);
      border: 1px solid rgba(255,255,255,0.12);
      backdrop-filter: blur(10px);
    }}
    .hero-summary {{
      margin: 0;
      max-width: 980px;
      color: rgba(248, 250, 252, 0.94);
      font-size: 15px;
    }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 14px;
      margin-top: 24px;
      max-width: 900px;
    }}
    .stat-card {{
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: var(--radius-lg);
      padding: 16px 18px;
      backdrop-filter: blur(10px);
    }}
    .stat-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: rgba(248, 250, 252, 0.68);
      margin-bottom: 6px;
    }}
    .stat-value {{
      font-size: 28px;
      font-weight: 800;
      color: #ffffff;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 22px;
      align-items: start;
    }}
    .sidebar {{
      position: sticky;
      top: 22px;
      background: rgba(255, 253, 248, 0.9);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 20px 14px;
      box-shadow: var(--shadow);
      max-height: calc(100vh - 44px);
      overflow: auto;
    }}
    .sidebar-title {{
      padding: 0 10px 14px;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--ink-soft);
      border-bottom: 1px solid var(--line);
      margin-bottom: 10px;
    }}
    .toc {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .toc-link {{
      display: block;
      padding: 10px 12px;
      border-radius: 12px;
      color: var(--ink-main);
      font-size: 14px;
      font-weight: 600;
      transition: 180ms ease;
    }}
    .toc-link.level-3 {{ padding-left: 20px; font-size: 13px; color: var(--ink-soft); }}
    .toc-link.level-4 {{ padding-left: 30px; font-size: 12px; color: var(--ink-soft); }}
    .toc-link:hover,
    .toc-link.active {{
      background: var(--accent-soft);
      color: var(--accent);
    }}
    .content {{
      min-width: 0;
    }}
    .chapter-card {{
      background: var(--bg-card);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
      padding: 30px 32px;
      margin-bottom: 26px;
    }}
    .chapter-card > h2 {{
      margin: 0 0 20px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
      color: var(--ink-strong);
      font-size: 28px;
    }}
    .subsection-card {{
      margin: 24px 0;
      padding: 20px 22px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(247,244,238,0.75));
      border: 1px solid rgba(231,220,207,0.95);
    }}
    .subsection-card > h3 {{
      margin: 0 0 16px;
      font-size: 20px;
      color: var(--ink-strong);
    }}
    .detail-card {{
      margin: 18px 0;
      padding: 16px 18px;
      border-radius: 16px;
      background: var(--bg-panel);
      border: 1px solid rgba(231,220,207,0.9);
    }}
    .detail-card > h4 {{
      margin: 0 0 14px;
      font-size: 17px;
      color: var(--ink-strong);
    }}
    p {{
      margin: 0 0 14px;
      font-size: 15px;
    }}
    .bullet-list {{
      margin: 0 0 14px;
      padding-left: 20px;
    }}
    .bullet-list li {{
      margin-bottom: 8px;
    }}
    .bullet-evidence {{
      color: var(--ink-soft);
      font-size: 13px;
    }}
    .bullet-implication {{
      color: var(--accent-warm);
      font-weight: 700;
    }}
    .bullet-boundary {{
      color: var(--accent-danger);
      font-weight: 700;
    }}
    .table-wrapper {{
      margin: 16px 0 18px;
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #fff;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 680px;
    }}
    thead th {{
      position: sticky;
      top: 0;
      background: #f7f4ee;
      color: var(--ink-strong);
      font-weight: 800;
      font-size: 13px;
      text-align: left;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
    }}
    tbody td {{
      padding: 14px 16px;
      border-top: 1px solid rgba(231,220,207,0.65);
      vertical-align: top;
      font-size: 14px;
    }}
    tbody tr:nth-child(even) td {{
      background: rgba(247, 244, 238, 0.5);
    }}
    @media (max-width: 1120px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: relative;
        top: 0;
        max-height: none;
      }}
    }}
    @media (max-width: 720px) {{
      .page {{
        padding: 14px;
      }}
      .hero {{
        padding: 24px 20px;
        border-radius: 22px;
      }}
      .chapter-card {{
        padding: 22px 18px;
      }}
      .subsection-card,
      .detail-card {{
        padding: 16px 14px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <h1>{html.escape(page_title)}</h1>
      <div class="hero-meta">
        <span class="hero-pill">页面生成：{html.escape(generated_at)}</span>
        <span class="hero-pill">Markdown 来源：{html.escape(source_path)}</span>
      </div>
      <p class="hero-summary">这是一份基于当前最新正式汇报稿生成的静态 HTML 预览页，用于更直观地浏览章节、表格与判断结构，不改动 Markdown 真源内容。</p>
      <div class="stats-grid">
        <div class="stat-card"><div class="stat-label">一级章节</div><div class="stat-value">{chapter_count}</div></div>
        <div class="stat-card"><div class="stat-label">分区块</div><div class="stat-value">{section_count}</div></div>
        <div class="stat-card"><div class="stat-label">子卡片</div><div class="stat-value">{detail_count}</div></div>
        <div class="stat-card"><div class="stat-label">表格行段</div><div class="stat-value">{table_count}</div></div>
      </div>
    </header>
    <div class="layout">
      <aside class="sidebar">
        <div class="sidebar-title">目录导航</div>
        <nav class="toc">{toc_html}</nav>
      </aside>
      <main class="content">{content_html}</main>
    </div>
  </div>
  <script>
    const links = Array.from(document.querySelectorAll('.toc-link'));
    const targets = links
      .map(link => document.getElementById(link.getAttribute('href').slice(1)))
      .filter(Boolean);
    const byId = new Map(links.map(link => [link.getAttribute('href').slice(1), link]));
    const observer = new IntersectionObserver((entries) => {{
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (!visible) return;
      const id = visible.target.id;
      links.forEach(link => link.classList.toggle('active', link === byId.get(id)));
    }}, {{ rootMargin: '-20% 0px -60% 0px', threshold: [0, 1] }});
    targets.forEach(target => observer.observe(target));
  </script>
</body>
</html>
"""


def write_html_from_markdown(report_path: Path, output_path: Path) -> Path:
    markdown_text = report_path.read_text(encoding="utf-8")
    generated_at = datetime.now().isoformat(timespec="seconds")
    html_text = render_report_html(
        markdown_text,
        source_path=str(report_path),
        generated_at=generated_at,
    )
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render presentation_main_report.md to a standalone HTML preview.")
    parser.add_argument("--report", required=True, help="Absolute path to presentation_main_report.md")
    parser.add_argument("--output", required=True, help="Absolute path to output HTML file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path = Path(args.report).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = write_html_from_markdown(report_path, output_path)
    print(f"written_html={written}")


if __name__ == "__main__":
    main()
