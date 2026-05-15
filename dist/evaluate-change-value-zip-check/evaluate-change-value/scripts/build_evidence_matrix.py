#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def confidence_from_sources(*conditions: bool) -> str:
    count = sum(1 for item in conditions if item)
    if count >= 2:
        return "high"
    if count == 1:
        return "medium"
    return "low"


def build_evidence_matrix(output_dir: str | Path) -> list[dict[str, Any]]:
    output_path = Path(output_dir)
    summary = load_json(output_path / "metric_summary.json", {})
    user_evidence = load_json(output_path / "user_evidence.json", {"evidence": []})
    brief = load_json(output_path / "change_brief_used.json", {})
    total = summary.get("total", {})
    delta = total.get("delta", {})
    new_sku = summary.get("new_sku", {})
    competitor_price = brief.get("competitor_price")
    evidence_count = int(user_evidence.get("evidence_count") or len(user_evidence.get("evidence", [])))

    matrix = [
        {
            "claim_id": "user_value",
            "claim": "变更需要命中目标用户场景和痛点，不能只由配置变化推导。",
            "evidence": [
                {"source": "user_evidence.json", "fact": f"extracted_user_evidence_count={evidence_count}"},
                {"source": "change_brief_used.json", "fact": f"change_name={brief.get('change_name', '')}"},
            ],
            "confidence": confidence_from_sources(evidence_count > 0, bool(brief.get("change_name"))),
            "caveat": "" if evidence_count > 0 else "缺少用户研究或 VOC 证据，用户价值只能低置信推断。",
        },
        {
            "claim_id": "financial_value",
            "claim": "变更后的总盘收入和毛利是否创造净增量。",
            "evidence": [
                {"source": "metric_summary.json", "fact": f"delta_revenue={delta.get('revenue')}"},
                {"source": "metric_summary.json", "fact": f"delta_gross_margin={delta.get('gross_margin')}"},
            ],
            "confidence": confidence_from_sources(delta.get("revenue") is not None, delta.get("gross_margin") is not None),
            "caveat": "",
        },
        {
            "claim_id": "new_sku_contribution",
            "claim": "目标变更对象对总盘增量的贡献需要单独量化。",
            "evidence": [
                {"source": "metric_summary.json", "fact": f"new_sku_units={new_sku.get('units')}"},
                {"source": "metric_summary.json", "fact": f"new_sku_gross_margin={new_sku.get('gross_margin')}"},
            ],
            "confidence": confidence_from_sources(bool(new_sku.get("units")), bool(new_sku.get("gross_margin"))),
            "caveat": "" if new_sku.get("units") else "未识别到目标新增 SKU，需检查 focus_change_keywords。",
        },
        {
            "claim_id": "portfolio_risk",
            "claim": "即使毛利额增长，也要检查组合毛利率和主力 SKU 蚕食风险。",
            "evidence": [
                {"source": "metric_summary.json", "fact": f"delta_gross_margin_rate={delta.get('gross_margin_rate')}"},
                {"source": "attribution_table.csv", "fact": "portfolio_related rows flag non-focus SKU/channel movements"},
            ],
            "confidence": confidence_from_sources(delta.get("gross_margin_rate") is not None),
            "caveat": "",
        },
    ]
    if competitor_price is not None:
        matrix.append(
            {
                "claim_id": "competitive_value",
                "claim": "竞品价格用于判断价格带防守或进攻价值。",
                "evidence": [
                    {"source": "change_brief_used.json", "fact": f"competitor_price={competitor_price}"},
                    {"source": "metric_summary.json", "fact": f"new_sku_weighted_msrp={new_sku.get('weighted_msrp')}"},
                ],
                "confidence": confidence_from_sources(True, bool(new_sku.get("weighted_msrp"))),
                "caveat": "若只有竞品单点价格，缺少竞品销量和促销节奏，竞争判断需保守。",
            }
        )

    payload = {"claim_count": len(matrix), "claims": matrix}
    (output_path / "evidence_matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return matrix


def main() -> None:
    parser = argparse.ArgumentParser(description="Build evidence matrix for a change-value decision pack.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    matrix = build_evidence_matrix(args.output_dir)
    print(json.dumps({"claim_count": len(matrix), "output_dir": args.output_dir}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
