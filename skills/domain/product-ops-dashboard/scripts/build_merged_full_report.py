#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ATTACHMENTS = [
    ("优化前后对比", "before_after_comparison.md"),
    ("直连数据覆盖", "direct_source_coverage.md"),
    ("补数任务单", "backfill_task_order.md"),
    ("补数任务板", "backfill_task_board.md"),
    ("补数跟踪版", "backfill_task_tracker.md"),
    ("X 系列分报告", "x_series_report.md"),
    ("T 系列分报告", "t_series_report.md"),
    ("X 系列文本级 Deep Dive", "x_series_pairwise_text_deep_dive.md"),
    ("X 系列问题闭环专题", "x_series_issue_closure_report.md"),
    ("X 系列 VOC 完整标签附录", "x_series_voc_full_appendix.md"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge robot insight artifacts into a single markdown report.")
    parser.add_argument("--bundle-dir", required=True, help="Bundle output directory")
    parser.add_argument("--output-name", default="full_report_merged.md", help="Merged markdown file name")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def demote_headings(markdown: str, levels: int = 1) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("#"):
            prefix = len(line) - len(line.lstrip("#"))
            lines.append("#" * min(prefix + levels, 6) + line[prefix:])
        else:
            lines.append(line)
    return "\n".join(lines)


def strip_title(markdown: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def merge_bundle(bundle_dir: Path, output_name: str) -> Path:
    main_report_path = bundle_dir / "main_report.md"
    if not main_report_path.exists():
        raise SystemExit(f"main_report.md not found in {bundle_dir}")

    merged_lines = [read_text(main_report_path), "", "## 7. 附件合集", ""]

    for title, filename in ATTACHMENTS:
        path = bundle_dir / filename
        if not path.exists():
            continue
        merged_lines.append(f"### 7.{len([line for line in merged_lines if line.startswith('### 7.')]) + 1} {title}")
        merged_lines.append("")
        merged_lines.append(demote_headings(strip_title(read_text(path)), 1))
        merged_lines.append("")

    output_path = bundle_dir / output_name
    output_path.write_text("\n".join(merged_lines).rstrip() + "\n", encoding="utf-8")

    manifest_path = bundle_dir / "artifact_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_paths = [str(path) for path in manifest.get("artifact_paths", [])]
        if str(output_path) not in artifact_paths:
            artifact_paths.append(str(output_path))
        manifest["artifact_paths"] = artifact_paths
        artifact_index = manifest.get("artifact_index", {})
        other_artifacts = artifact_index.get("other_artifacts", [])
        if str(output_path) not in other_artifacts:
            other_artifacts.append(str(output_path))
        artifact_index["other_artifacts"] = other_artifacts
        manifest["artifact_index"] = artifact_index
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return output_path


def main() -> None:
    args = parse_args()
    bundle_dir = Path(args.bundle_dir).expanduser().resolve()
    output_path = merge_bundle(bundle_dir, args.output_name)
    print(f"merged_report={output_path}")


if __name__ == "__main__":
    main()
