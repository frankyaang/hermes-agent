#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    "decision_card.md",
    "metric_bridge.csv",
    "attribution_table.csv",
    "evidence_matrix.json",
    "5w2h_action_plan.md",
    "metric_summary.json",
]


def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def csv_row_count(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def validate_decision_pack(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    blockers: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    for name in REQUIRED_FILES:
        exists = (output_path / name).exists()
        checks.append({"check": f"required_file:{name}", "passed": exists})
        if not exists:
            blockers.append(f"Missing required output file: {name}")

    if csv_row_count(output_path / "metric_bridge.csv") == 0:
        blockers.append("metric_bridge.csv has no data rows")
    if csv_row_count(output_path / "attribution_table.csv") == 0:
        warnings.append("attribution_table.csv has no data rows")

    evidence = load_json(output_path / "evidence_matrix.json", {"claims": []})
    if not evidence.get("claims"):
        blockers.append("evidence_matrix.json has no claims")
    for claim in evidence.get("claims", []):
        if not claim.get("evidence"):
            blockers.append(f"Claim has no evidence: {claim.get('claim_id')}")
        if claim.get("confidence") == "low":
            warnings.append(f"Low confidence claim: {claim.get('claim_id')}")

    summary = load_json(output_path / "metric_summary.json", {})
    delta = summary.get("total", {}).get("delta", {})
    if delta.get("gross_margin", 0) > 0 and delta.get("gross_margin_rate", 0) < 0:
        warnings.append("Gross margin increased while gross margin rate declined; decision should be conditional and include portfolio controls")
    if not summary.get("new_sku", {}).get("units"):
        warnings.append("No target new SKU units detected; check focus_change_keywords or input scope")

    decision_text = (output_path / "decision_card.md").read_text(encoding="utf-8") if (output_path / "decision_card.md").exists() else ""
    if "结论" not in decision_text:
        blockers.append("decision_card.md does not contain a conclusion section")

    report = {
        "status": "blocked" if blockers else "passed_with_warnings" if warnings else "passed",
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
    }
    (output_path / "audit_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a change-value decision pack and write audit_report.json.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = validate_decision_pack(args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
