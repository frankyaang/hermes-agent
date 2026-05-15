#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_evidence_matrix import build_evidence_matrix
from build_metric_bridge import build_metric_bridge
from extract_sources import extract_sources
from validate_decision_pack import validate_decision_pack


def load_change_brief(input_dir: Path) -> dict[str, Any]:
    path = input_dir / "change_brief.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "change_name": "未命名变更",
        "target_region": "中国",
        "focus_change_keywords": ["中配"],
        "decision_constraints": ["仅基于可读取数据生成受限评估"],
    }


def fmt_num(value: float, scale: float = 1.0, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value / scale:,.2f}{suffix}"


def decision_grade(summary: dict[str, Any], audit: dict[str, Any]) -> tuple[str, str]:
    if audit.get("blockers"):
        return "补数后再决策", "存在阻塞项，不能给出强结论。"
    delta = summary.get("total", {}).get("delta", {})
    gm_delta = float(delta.get("gross_margin") or 0)
    revenue_delta = float(delta.get("revenue") or 0)
    gm_rate_delta = float(delta.get("gross_margin_rate") or 0)
    if gm_delta > 0 and revenue_delta > 0 and gm_rate_delta >= 0:
        return "认可", "收入、毛利和毛利率均正向，风险相对可控。"
    if gm_delta > 0 and revenue_delta > 0:
        return "条件认可", "收入和毛利创造增量，但毛利率或组合风险需要经营管控。"
    if revenue_delta > 0 or gm_delta > 0:
        return "试点观察", "存在局部正向信号，但净价值尚不充分。"
    return "不认可", "当前数据未显示正向净财务价值。"


def write_decision_card(output_dir: Path, case_name: str, brief: dict[str, Any], summary: dict[str, Any], audit: dict[str, Any]) -> None:
    total = summary.get("total", {})
    before = total.get("before", {})
    after = total.get("after", {})
    delta = total.get("delta", {})
    new_sku = summary.get("new_sku", {})
    grade, reason = decision_grade(summary, audit)
    lines = [
        f"# {case_name} 变更价值评估结论",
        "",
        "## 结论",
        f"**{grade}**。{reason}",
        "",
        "## 核心依据",
        f"- 用户价值：已从输入资料抽取用户证据，需在最终报告中结合配置差异解释真实场景匹配。",
        f"- 竞争价值：竞品价格为 `{brief.get('competitor_price', '未提供')}`，如只有单点价格，竞争结论需保守。",
        f"- 财务价值：目标区域收入变化 `{fmt_num(delta.get('revenue', 0), 1_000_000, '百万')}`，毛利变化 `{fmt_num(delta.get('gross_margin', 0), 1_000_000, '百万')}`。",
        f"- 组合风险：毛利率变化 `{fmt_num(delta.get('gross_margin_rate', 0) * 100, 1, 'pct')}`，需结合归因表检查非目标 SKU 变化。",
        "",
        "## 关键数字",
        "| 指标 | 变更前 | 变更后 | 差异 |",
        "|---|---:|---:|---:|",
        f"| 销量 | {fmt_num(before.get('units', 0), 1)} | {fmt_num(after.get('units', 0), 1)} | {fmt_num(delta.get('units', 0), 1)} |",
        f"| 收入 | {fmt_num(before.get('revenue', 0), 1_000_000, '百万')} | {fmt_num(after.get('revenue', 0), 1_000_000, '百万')} | {fmt_num(delta.get('revenue', 0), 1_000_000, '百万')} |",
        f"| 毛利 | {fmt_num(before.get('gross_margin', 0), 1_000_000, '百万')} | {fmt_num(after.get('gross_margin', 0), 1_000_000, '百万')} | {fmt_num(delta.get('gross_margin', 0), 1_000_000, '百万')} |",
        f"| 毛利率 | {fmt_num(before.get('gross_margin_rate', 0) * 100, 1, '%')} | {fmt_num(after.get('gross_margin_rate', 0) * 100, 1, '%')} | {fmt_num(delta.get('gross_margin_rate', 0) * 100, 1, 'pct')} |",
        f"| 目标新增对象销量 | - | {fmt_num(new_sku.get('units', 0), 1)} | {fmt_num(new_sku.get('units', 0), 1)} |",
        f"| 目标新增对象毛利 | - | {fmt_num(new_sku.get('gross_margin', 0), 1_000_000, '百万')} | {fmt_num(new_sku.get('gross_margin', 0), 1_000_000, '百万')} |",
        "",
        "## 主要风险",
        "- 毛利额增长不等于无风险，若组合毛利率下降，需要设置价格和渠道毛利红线。",
        "- 目标低价 SKU 若贡献增量，也可能挤压高配或顶配，需要监控 SKU 结构。",
        "- 竞品价格若只有单点信息，需补充销量、促销节奏和渠道打法。",
        "",
        "## 审计状态",
        f"- `{audit.get('status', 'not_run')}`",
    ]
    (output_dir / "decision_card.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_5w2h(output_dir: Path, brief: dict[str, Any], summary: dict[str, Any]) -> None:
    target_region = summary.get("target_region", brief.get("target_region", "目标区域"))
    focus = "、".join(summary.get("focus_change_keywords", brief.get("focus_change_keywords", []))) or "目标变更对象"
    lines = [
        "# 经营级 5W2H 行动计划",
        "",
        "| 要素 | 内容 |",
        "|---|---|",
        f"| What | 管控 `{target_region}` `{focus}` 变更后的价格、SKU 结构、渠道毛利和成本兑现。 |",
        "| Why | 变更价值来自净增量，但若毛利率下降或主力 SKU 被蚕食，净价值会被抵消。 |",
        "| Who | 产品经营、渠道经营、供应链/BOM、财务 BP、售后体验共同负责。 |",
        f"| Where | `{target_region}` 目标渠道、目标 SKU、同系列高/中/顶配组合。 |",
        "| When | 上市/变更后按周监控，首月形成第一次复盘，关键大促前重算价格带。 |",
        "| How | 建立动态定价监控、BOM 二次谈判、SKU 库存比例预警、渠道毛利红线和竞品价格跟踪。 |",
        "| How much | 至少跟踪总毛利额、组合毛利率、目标 SKU 毛利率、高配/顶配份额、渠道毛利率、竞品价差。 |",
    ]
    (output_dir / "5w2h_action_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_evaluation(input_dir: str | Path, output_dir: str | Path, case_name: str) -> dict[str, Any]:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    brief = load_change_brief(input_path)
    (output_path / "change_brief_used.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    extract_sources(input_path, output_path)
    summary = build_metric_bridge(input_path, output_path)
    build_evidence_matrix(output_path)

    preliminary_audit = {"status": "not_run", "blockers": [], "warnings": []}
    write_decision_card(output_path, case_name, brief, summary, preliminary_audit)
    write_5w2h(output_path, brief, summary)
    audit = validate_decision_pack(output_path)
    write_decision_card(output_path, case_name, brief, summary, audit)
    audit = validate_decision_pack(output_path)
    return {"case_name": case_name, "output_dir": str(output_path.resolve()), "audit": audit}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an end-to-end product change value evaluation.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--case-name", required=True)
    args = parser.parse_args()
    result = run_evaluation(args.input_dir, args.output_dir, args.case_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
