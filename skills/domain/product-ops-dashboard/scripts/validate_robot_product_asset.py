#!/usr/bin/env python3
"""Validate product-ops-dashboard asset package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from presentation_report_renderer import validate_presentation_main_report_text


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_PATHS = [
    ROOT / "examples" / "voc_only_request.json",
    ROOT / "examples" / "survey_only_request.json",
    ROOT / "examples" / "portfolio_full_request.json",
]
REQUIRED_ARTIFACT_KEYS = {"main_report", "presentation_main_report", "artifact_manifest"}


def validate_robot_product_bundle(manifest_path: str) -> dict[str, object]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    artifact_index = manifest.get("artifact_index", {})
    missing = sorted(key for key in REQUIRED_ARTIFACT_KEYS if not artifact_index.get(key))
    report_blockers: list[str] = []
    presentation_path = artifact_index.get("presentation_main_report")
    if presentation_path:
        report_path = Path(presentation_path)
        if not report_path.exists():
            report_blockers.append("presentation_main_report file missing")
        else:
            report_text = report_path.read_text(encoding="utf-8")
            missing_headings = validate_presentation_main_report_text(report_text)
            if missing_headings:
                report_blockers.append(
                    "presentation_main_report missing headings: " + ", ".join(missing_headings)
                )
            banned_terms = [
                "evidence_tier",
                "coverage_status",
                "grain",
                "supported",
                "partial",
                "unsupported",
                "[A/",
                "[B/",
                "[C/",
                "[D/",
                "evidence packet",
                "converged",
                "contested",
                "not_ready",
                "external_only",
                "frontline_mode",
                "当前 runtime 汇总周期",
            ]
            hit_terms = [term for term in banned_terms if term in report_text]
            if hit_terms:
                report_blockers.append(
                    "presentation_main_report contains backend terms: " + ", ".join(hit_terms)
                )
    return {
        "passed": not missing and not report_blockers,
        "missing_artifact_keys": missing,
        "report_blockers": report_blockers,
    }


def validate_robot_product_asset(manifest_path: str = "") -> dict[str, object]:
    blockers: list[str] = []
    if not (ROOT / "ASSET_HARNESS.md").exists():
        blockers.append("missing ASSET_HARNESS.md")
    for path in EXAMPLE_PATHS:
        if not path.exists():
            blockers.append(f"missing {path.relative_to(ROOT)}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload.get("category_name"):
            blockers.append(f"missing category_name in {path.name}")

    bundle_validation: dict[str, object] = {}
    if manifest_path:
        bundle_validation = validate_robot_product_bundle(manifest_path)
        if not bundle_validation["passed"]:
            blockers.append("bundle validation failed")
    return {
        "passed": not blockers,
        "blockers": blockers,
        "bundle_validation": bundle_validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate robot product insight asset.")
    parser.add_argument("--manifest-path", default="")
    args = parser.parse_args()
    print(json.dumps(validate_robot_product_asset(args.manifest_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
