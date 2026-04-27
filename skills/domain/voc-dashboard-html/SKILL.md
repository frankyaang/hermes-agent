---
name: voc-dashboard-html
description: Generate strict, lossless static HTML dashboards from formal VOC Markdown reports, preserving every section/table/cell and marking negative or risk content in red without rewriting the report content.
metadata:
  short-description: Lossless VOC Markdown to HTML dashboard
---

# VOC Dashboard HTML

Use this skill when the user provides a formal VOC Markdown report and wants a static HTML dashboard similar to an AI Studio page, while preserving all report data and highlighting negative or risk content.

## Workflow

1. Treat the Markdown report as the only content source of truth.
2. Do not summarize, compress, rename, or drop Markdown content when generating HTML.
3. Use `scripts/render_voc_dashboard_html.py` with `--strict` and the default `ai_studio` theme.
4. Review the generated `lossless_audit.json` before handing off the HTML.
5. If strict mode fails, report the missing or malformed blocks instead of generating a partial dashboard.

## Visual Theme

The default `ai_studio` theme follows the provided reference page style: fixed dark-blue sidebar, light-gray page background, white content container, Ant Design style tables, summary cards, PM insight blocks, action cards, and red risk markers.

Content fidelity is always higher priority than visual matching. Do not drop, merge, rewrite, or compress tables to match a reference page layout; wide Top15 tables must keep all source columns and use horizontal scrolling if needed.

## Negative Marking Rule

The renderer marks clearly negative/risk content in red. Do not treat every `【回落】` as negative, because VOC trend fallbacks can mean positive-topic heat cooling rather than user pain.

Clear negative/risk signals include `负面`, `抱怨`, `故障`, `报错`, `不达标`, `扫不干净`, `拖不干净`, `返工`, `击穿`, `维修`, `退换`, `FRR`, `FFR`, `售后与客服`, and risk phrases such as `真实流失风险`.

## Commands

```bash
python3 scripts/render_voc_dashboard_html.py \
  --input-md /path/to/cross_brand_voc_report.md \
  --output-html /path/to/dashboard.html \
  --manifest /path/to/artifact_manifest.json \
  --audit /path/to/lossless_audit.json \
  --strict \
  --theme ai_studio
```

## Validation Expectations

The audit must show:

- `strict_passed: true`
- `missing_block_ids: []`
- `table_column_mismatches: []`
- `visible_text_matches: true`
- The rendered block count equals the parsed source block count.

If any of these fail, do not present the HTML as final.
